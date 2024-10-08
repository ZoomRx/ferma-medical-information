import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List

import openai
import requests

from helpers.es_utils import get_es_data
from helpers.logger import Logger
from schemas.medical_info_inquiry import InquiryDetails, InquiryType
from config import settings

openai.api_key = settings.env.open_ai_key
citation_order = {}


def fetch_content(url):
    response = requests.get(url)
    return response.content


import logging
from datetime import datetime
import traceback


def generate_report(inquiry_details: InquiryDetails, article_pages, content="all", data="", pi_details="", clinical_data={}):
    try:

        inquiry = inquiry_details.inquiry
        inquiry_type = "All"
        if bool(inquiry_details.inquiry_type):
            inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)

        article_content = "{" + ", ".join([f"'{content}'" for content in article_pages]) + "}"

        if content == "all":
            prompt_file = "prompt_srl.txt"
        elif content == "title":
            prompt_file = "prompt_title.txt"
        elif content == "summary":
            prompt_file = "prompt_summary.txt"
        elif content == "introduction":
            prompt_file = "prompt_intro.txt"
        elif content == "clinical_data":
            prompt_file = "prompt_clinicaldata.txt"
        elif content == "results":
            prompt_file = "prompt_results.txt"
        elif content == "trials":
            prompt_file = "prompt_trials.txt"
        elif content == "study":
            prompt_file = "prompt_study.txt"
        elif content == "references":
            prompt_file = "prompt_reference.txt"

        with open(f"config/{prompt_file}", "r") as file:
            prompt_text = file.read()

        if content == "clinical_data":
            notes = clinical_data.get("notes", "")
            study_results = clinical_data.get("study_results", "")
            safety = clinical_data.get("safety", "")
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content,
                                        trial_json=data, notes=notes, study_results=study_results, safety=safety)
        elif content == "summary":
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content,
                                        study_json=data)
        elif content == "title":
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_pages)
        elif content == "introduction":
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content, title=data,
                                        pi_data=pi_details)
        elif content == "references":
            prompt = prompt_text.format(article=article_content, study_json=data)
        elif content == "study":
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content,
                                        cite_id=data)
        else:
            prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content, title=data)

        conversation = [
            {"role": "system",
             "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data."},
            {"role": "user", "content": f"""{prompt}"""
             }
        ]

        log_message = f"Generate {content} "
        log_data = {'inquiry_details': inquiry_details, 'data': data, 'pi_details': pi_details,
                    'clinical_data': clinical_data, 'prompt': prompt}
        Logger.log(msg=log_message, data=log_data)

        start_time = datetime.now()
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=conversation,
            temperature=0,
            max_tokens=4096
        )
        end_time = datetime.now()
        elapsed_time = end_time - start_time

        print(f"Response Time for SRL content- {content}: {elapsed_time} seconds")
        srl_content = response['choices'][0]['message']['content']

        with open("srl_content.txt", "w") as file:
            file.write(srl_content)

        # End event logging
        log_message = f"Generate {content} completed successfully"
        log_data = {'response': {srl_content}, 'response_time': elapsed_time.total_seconds()}
        Logger.log(msg=log_message, data=log_data)
        return srl_content

    except Exception as e:
        # Log error details
        error_message = f"Error occurred in generate_report for {content}"
        Logger.log("error", msg=error_message, data={'error': str(e)})

        # Re-raise the exception
        raise


def generate_summary(inquiry_details, file_name):
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    additional_notes = inquiry_details.additional_notes

    with open("config/prompt_extract.txt", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role "
                    "involves responding to clinical inquiries from healthcare professionals (HCPs) by providing "
                    "accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"{prompt}"
         }
    ]
    start_time = datetime.now()
    # Generate the report using the OpenAI API
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    end_time = datetime.now()
    elapsed_time = end_time - start_time

    print(f"Response Time for Summary Extraction: {elapsed_time} seconds")
    # Extract the content from the response
    article_summary = response['choices'][0]['message']['content']

    return article_summary


# Function to convert the array to a text format
def convert_to_text_format(types: List[InquiryType]):
    if isinstance(types, list):
        if not types:
            Logger.log(msg=f"InquiryType is empty")
        result = []
        for inquiry_type in types:
            if isinstance(inquiry_type, InquiryType):
                if inquiry_type.type:
                    categories_str = ', '.join(inquiry_type.categories)
                    result.append(f"{inquiry_type.type} ({categories_str})")
                else:
                    Logger.log(msg = f"InquiryType has empty type: {inquiry_type}")
            else:
                Logger.log("warning", msg=f"Skipping non-InquiryType item: {inquiry_type}")
        return ", ".join(result)
    elif isinstance(types, InquiryType):
        if types.type:
            categories_str = ', '.join(types.categories)
            return f"{types.type} ({categories_str})"
        else:
            Logger.log("warning",msg = f"InquiryType has empty type")
            return ""
    else:
        Logger.log("warning",msg = f"InquiryType is invalid")
        return ""


def generate_content(inquiry_details: InquiryDetails):
    set_citation_order(inquiry_details)
    articles = get_relevant_pages(inquiry_details)

    srl_content = {}
    pi_details = get_prescribed_information(inquiry_details)

    title = generate_report(inquiry_details, pi_details, "title")

    srl_content["title"] = title
    summary, clinical_data, reference_data = generate_clinical_data(inquiry_details, pi_details)

    srl_content["summary"] = summary
    srl_content["introduction"] = generate_introduction(inquiry_details, articles, title, pi_details)
    srl_content["clinical_data"] = clinical_data
    srl_content["references"] = reference_data
    srl_document = "\n\n".join(str(value) for value in srl_content.values())
    return srl_document


def generate_introduction(inquiry_details, articles, title, pi_details):
    intro_data = "\n## Introduction\n"
    intro_data_string = generate_report(inquiry_details, articles, "introduction", title, pi_details)
    intro_data += intro_data_string
    return intro_data


def set_citation_order(inquiry_details: InquiryDetails):
    global citation_order

    # Assign indices to documents
    index = 1
    pi_document_name = os.path.splitext(os.path.basename(inquiry_details.pi_source))[0]
    citation_order[pi_document_name] = index
    index += 1

    for document in inquiry_details.document_source:
        document_name = os.path.splitext(os.path.basename(document))[0]
        citation_order[document_name] = index
        index += 1

    # Add pi_source document with the next available index


def generate_clinical_data(inquiry_details: InquiryDetails, pi_details):
    # Assuming get_relevant_clinical_study returns a list of tuples (document, trial_json)
    articles, trials = get_relevant_clinical_study(inquiry_details)
    report_type = "clinical_data"
    clinical_data = []
    references = []
    summary = []
    pi_reference = get_reference_pi_data(inquiry_details.pi_source, pi_details)
    safety_string, study_results_string, notes = get_cleaned_content(inquiry_details)

    clinical_data_input = dict(
        safety=safety_string,
        study_results=study_results_string,
        notes=notes
    )
    # Assuming pi_reference is defined somewhere above this line
    if pi_reference:
        references.append(pi_reference)

    if isinstance(trials, (list, tuple)) and all(isinstance(item, tuple) and len(item) == 2 for item in trials):
        # Initialize ThreadPoolExecutor outside the loop to reuse it
        with ThreadPoolExecutor() as executor:
            future_to_article = {}
            # Submit all tasks
            for item in trials:
                future_summary = executor.submit(generate_report, inquiry_details, articles[item[0]], "summary",
                                                 item[1])
                future_to_article[future_summary] = {"type": "summary", "id": item[0]}

                future_clinical = executor.submit(generate_report, inquiry_details, articles[item[0]], report_type,
                                                  item[1], "", clinical_data_input)
                future_to_article[future_clinical] = {"type": "clinical", "id": item[0]}

                future_references = executor.submit(generate_report, inquiry_details, articles[item[0]], "references",
                                                    item[1])
                future_to_article[future_references] = {"type": "references", "id": item[0]}

            # Process results in submission order
            for future in future_to_article:
                document_info = future_to_article[future]
                try:
                    result = future.result()

                    if document_info["type"] == "summary":
                        summary.append(result)
                    elif document_info["type"] == "clinical":
                        clinical_data.append(result)
                    elif document_info["type"] == "references":
                        references.append(result)
                except Exception as exc:
                    Logger.log("error",
                               f'An error occurred while generating report for {document_info["id"]} ({document_info["type"]}): {exc}')
                    raise
    else:
        Logger.log("error",  msg= f'Trials data is not in the expected format {trials}')

    summary_data_string = "\n\n".join(summary)
    summary_data = "\n## Summary\n"
    summary_data += summary_data_string

    clinical_data_string = "\n\n".join(clinical_data)
    clinical_data = "\n## Clinical Data\n"
    clinical_data += clinical_data_string
    reference_data_string = '\n'.join([f'{item}' for i, item in enumerate(references)])
    reference_data = "\n## References\n"
    reference_data += reference_data_string

    return summary_data, clinical_data, reference_data


def generate_report_clinical_data(args):
    inquiry_details, articles, report_type, trial = args
    for document, trial_json in trial:
        article = articles[document]
    return generate_report(inquiry_details, article, report_type, trial_json)


def get_relevant_clinical_trials(inquiry_details, articles):
    trials = generate_report(inquiry_details, articles, "trials")
    trials_list = trials.split(', ')
    return trials_list


def get_relevant_clinical_study(inquiry_details: InquiryDetails):
    trial_study_list = []
    article = {}
    document_names = set([os.path.splitext(doc)[0] for doc in inquiry_details.document_source])
    print(document_names)
    for document in document_names:
        print(document)
        article[document] = get_es_document(document)
        print(article[document])
        cite_id = citation_order.get(document)
        study_json = generate_report(inquiry_details, article[document], "study", cite_id)
        print(study_json)
        trial_study_list.append((document, study_json))
    print(trial_study_list)
    return article, trial_study_list


def get_es_document(document_name):
    query = {
        "size": 50,
        "query": {
            "bool": {
                "must": [
                    {"term": {"document_name": document_name}}]
            }
        },
        "_source": ["content"]
    }
    result = get_es_data(query)
    return result


def get_relevant_pages(inquiry_details: InquiryDetails):
    with open("config/prompt_keyword.txt", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(inquiry=inquiry_details.inquiry, inquiry_type=inquiry_details.inquiry_type,
                                notes=inquiry_details.additional_notes)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role "
                    "involves indetifying the key pharmaceutical terms in the given HCP inquiry details"},
        {"role": "user", "content": f"{prompt}"
         }
    ]
    start_time = datetime.now()
    # Generate the report using the OpenAI API
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    end_time = datetime.now()
    elapsed_time = end_time - start_time

    es_bool_query = response['choices'][0]['message']['content']
    es_bool_query = es_bool_query.replace("```", "")
    es_bool_query = es_bool_query.replace("json", "")
    json_data = json.loads(es_bool_query)
    transformed_json = transform_json(json_data)
    document_source = inquiry_details.document_source
    document_name = [os.path.splitext(os.path.basename(source))[0] for source in document_source]
    if 'must_have' in transformed_json and transformed_json['must_have']:
        must_query = {
            "query_string": {
                "query": transformed_json["must_have"],
                "fields": ["content^50", "page_title", "title"],
                "default_operator": "AND",
                "analyzer": "synonyms"
            }
        }
    else:
        must_query = None

    if 'should_have' in transformed_json and transformed_json['should_have']:
        should_query = {
            "query_string": {
                "query": transformed_json["should_have"],
                "fields": ["content^50", "page_title", "title"],
                "default_operator": "OR",
                "analyzer": "synonyms"
            }
        }
    else:
        should_query = None

        # Build the main query structure
    target_query = {
        "query": {
            "bool": {
                "must": [] if not must_query else [must_query],
                "should": [] if not should_query else [should_query],
                "filter": [
                    {
                        "terms": {
                            "document_name": document_name
                        }
                    }
                ]
            }
        },
        "_source": {
            "includes": ["page_no", "content", "document_name"]
        }
    }
    article_data = get_es_data(target_query)
    result = add_citation_id(article_data)

    log_message = "Generated Bool query"
    log_data = {'inquiry': inquiry_details.inquiry, 'prompt': {prompt}, 'response': {es_bool_query},
                'response_time': {elapsed_time}, 'es_query': target_query}
    Logger.log(msg=log_message, data=log_data)

    return result


def get_reference_pi_data(pi_document_name, pi_details):
    with open("config/prompt_pi_reference.txt", "r") as file:
        prompt_text = file.read()
    cite_id = citation_order.get(pi_document_name)
    prompt = prompt_text.format(article=pi_details, cite_id=cite_id)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role "
                    "involves identifying the key pharmaceutical terms in the given HCP inquiry details"},
        {"role": "user", "content": f"{prompt}"
         }
    ]
    start_time = datetime.now()
    # Generate the report using the OpenAI API
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    end_time = datetime.now()
    elapsed_time = end_time - start_time

    pi_reference = response['choices'][0]['message']['content']

    log_message = f"Generate Reference for PI data "
    log_data = {'pi_document': pi_document_name, 'prompt': prompt, 'response': {pi_reference},
                'response_time': elapsed_time.total_seconds()}
    Logger.log(msg=log_message, data=log_data)
    return pi_reference


def transform_json(original):
    transformed = {}
    for key, value in original.items():
        if value == "":
            continue
        elif key.startswith("must_have"):
            if "must_have" in transformed:
                transformed["must_have"] = f"{transformed.get('must_have', '')} OR ({value})"
            else:
                transformed["must_have"] = value
        elif key == "should_have":
            transformed[key] = value
    return transformed


def get_prescribed_information(inquiry_details: InquiryDetails):
    document_source = inquiry_details.pi_source
    document_name, extension = os.path.splitext(document_source)
    target_query = {"size": 1, "query": {
        "bool": {
            "must": [
                {"term": {"document_name": document_name}},
                {"term": {"page_no": 1}}
            ]
        }
    }, "_source": {
        "includes": ["content", "document_name"]
    }}

    pi_data = get_es_data(target_query)
    result = add_citation_id(pi_data)
    return result, document_name


def add_citation_id(data: dict):
    for item in data:
        cite_id = citation_order.get(item.get('document_name'))
        if cite_id:
            item.update({'cite_id': cite_id})
        else:
            print(f"No cite_id found for document {item['document_name']}. Leaving unchanged.")
    return data


def get_cleaned_content(inquiry_details: InquiryDetails):
    default_clinical_json = {
        "Safety Results": [
            "Common adverse events",
            "Serious adverse events",
            "Statistical significance",
            "Confidence interval"
        ],
        "Efficacy Results": [
            "Primary outcomes",
            "Secondary outcomes",
            "Patient-reported outcomes"
        ],
        "Study Results": [
            "Characteristics of study population"
            "Primary efficacy endpoints",
            "Secondary efficacy endpoints",
            "Statistical significance",
            "Confidence interval"]
    }
    additional_notes = inquiry_details.additional_notes
    clinical_json = default_clinical_json
    updated_notes = additional_notes
    if additional_notes:
        notes = get_exclusion(additional_notes)
        notes_json = json.loads(notes)
        updated_notes = notes_json['updated_notes']
        if (notes_json['exclude'] != ""):
            with open(f"config/prompt_exclusion.txt", "r") as file:
                prompt_text = file.read()

            prompt = prompt_text.format(inquiry=inquiry_details.inquiry, notes=inquiry_details.additional_notes,
                                        clinical_json=clinical_json)

            conversation = [
                {"role": "system",
                 "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data."},
                {"role": "user", "content": f"""{prompt}"""
                 }
            ]

            start_time = datetime.now()
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=conversation,
                temperature=0,
                max_tokens=4096
            )
            try:
                end_time = datetime.now()
                elapsed_time = end_time - start_time
                response_content = response['choices'][0]['message']['content']
                clinical_json = json.loads(response_content)

                log_message = f"Generate inclusion and exclusion filters"
                log_data = {'prompt': prompt, 'response': {clinical_json},
                            'response_time': elapsed_time.total_seconds()}
                Logger.log(msg=log_message, data=log_data)
            except json.JSONDecodeError as e:
                Logger.log("error", f"JsonDecode Error for generated Clinical json",
                           data={'error': str(e), 'json': str(response_content)})
                clinical_json = default_clinical_json
            except ValueError as e:
                print(f"Error: {str(e)}")
                Logger.log("error", f"Value Error for generated json", data={'error': str(e)})
                clinical_json = default_clinical_json
            except Exception as e:
                print(f"An unexpected error occurred: {str(e)}")
                Logger.log("error", f"An unexpected error occurred", data={'error': str(e)})
                clinical_json = default_clinical_json

    safety, study_results = get_required_content(clinical_json)
    return safety, study_results, updated_notes


def get_required_content(clinical_content_json):
    try:
        # Check if the input is a valid JSON object
        if not isinstance(clinical_content_json, dict):
            raise ValueError("Invalid JSON format")

        # Initialize variables for each type of result
        safety_results = ""
        efficacy_results = ""
        study_results = ""

        # Check and process each type of result
        if "Safety Results" in clinical_content_json and clinical_content_json["Safety Results"]:
            safety_results = ", ".join([f"{item} including" for item in clinical_content_json["Safety Results"]])

        if "Efficacy Results" in clinical_content_json and clinical_content_json["Efficacy Results"]:
            efficacy_results = ", ".join([f"{item} including" for item in clinical_content_json["Efficacy Results"]])

        if "Study Results" in clinical_content_json and clinical_content_json["Study Results"]:
            study_results = ", ".join([f"{item} including" for item in clinical_content_json["Study Results"]])

        # Form the safety string only if either safety_results or efficacy_results is not empty
        if safety_results and efficacy_results:
            safety = f"""Safety focusing on {safety_results} and {efficacy_results}"""
        elif safety_results:
            safety = f"""Safety focusing on {safety_results}"""
        elif safety_results:
            safety = f"""Safety focusing on {efficacy_results}"""
        else:
            safety = "Safety"

        if study_results:
            pass
        else:
            study_results = "Study Results"

        # Return the required content
        return safety, study_results

    except json.JSONDecodeError as e:
        Logger.log("error", f"JsonDecode Error while generating filter for Clinical data: {str(e)}")
        return None, None

    except ValueError as e:
        Logger.log("error", f"Error while generating filter for Clinical data: {str(e)}")
        return None, None


def get_exclusion(notes):
    with open(f"config/prompt_update_notes.txt", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(notes=notes)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]

    start_time = datetime.now()
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    end_time = datetime.now()
    elapsed_time = end_time - start_time

    cleaned_notes = response['choices'][0]['message']['content']
    log_message = f"Generate Additional Notes without Exclusion "
    log_data = {'additional_notes': notes, 'prompt': prompt, 'response': {cleaned_notes},
                'response_time': elapsed_time.total_seconds()}
    Logger.log(msg=log_message, data=log_data)
    return cleaned_notes
