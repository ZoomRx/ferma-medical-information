import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import time, datetime

import openai
import requests
from sqlalchemy import null

from helpers.es_utils import get_es_data
from schemas.medical_info_inquiry import InquiryDetails
from config import settings

openai.api_key = settings.env.open_ai_key
citation_order = {}


def fetch_content(url):
    response = requests.get(url)
    return response.content


def generate_report(inquiry_details, article_pages, content="all", data="", pi_details="",clinical_data={}):
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)

    article_content = "{" + ", ".join([f"'{content}'" for content in article_pages]) + "}"

    if content == "all":
        prompt_file = "prompt_srl.txt"
    if content == "title":
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
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content,
                                    trial_json=data, notes=clinical_data["notes"], study_results=clinical_data["study_results"] , safety = clinical_data["safety"])
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
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content, cite_id=data)
    else:
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content, title=data)

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

    print(f"Response Time for SRL content: {elapsed_time} seconds")
    srl_content = response['choices'][0]['message']['content']

    with open("srl_content.txt", "w") as file:
        file.write(srl_content)

    return srl_content


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

    print(f"Response Time for Extraction: {elapsed_time} seconds")
    # Extract the content from the response
    article_summary = response['choices'][0]['message']['content']

    return article_summary


# Function to convert the array to a text format
def convert_to_text_format(types):
    text = ""
    for inquiry_type in types:
        text += f"{inquiry_type.type} ({', '.join(inquiry_type.categories)}), "
    return text.rstrip(", ")  # Remove trailing comma and space


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


def set_citation_order(inquiry_details):
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


def generate_clinical_data(inquiry_details, pi_details):
    # Assuming get_relevant_clinical_study returns a list of tuples (document, trial_json)
    articles, trials = get_relevant_clinical_study(inquiry_details)
    report_type = "clinical_data"
    clinical_data = []
    references = []
    summary = []
    pi_reference = get_reference_pi_data(inquiry_details.pi_source, pi_details)
    safety_string, study_results_string, notes = get_cleaned_content(inquiry_details)

    clinical_data_input = {
        "safety": safety_string,
        "study_results": study_results_string,
        "notes": notes
    }
    # Assuming pi_reference is defined somewhere above this line
    if pi_reference:
        references.append(pi_reference)

    if isinstance(trials, (list, tuple)) and all(isinstance(item, tuple) and len(item) == 2 for item in trials):
        # Initialize ThreadPoolExecutor outside the loop to reuse it
        with ThreadPoolExecutor() as executor:
            future_to_article = {}
            future_to_article_clinical = {}
            future_to_article_summary = {}
            for item in trials:
                future_summary = executor.submit(generate_report, inquiry_details, articles[item[0]], "summary",
                                                 item[1])
                future_to_article_summary[future_summary] = item[0]
                future_clinical = executor.submit(generate_report, inquiry_details, articles[item[0]], report_type,
                                                  item[1], clinical_data_input)
                future_to_article_clinical[future_clinical] = item[0]
                future = executor.submit(generate_report, inquiry_details, articles[item[0]], "references", item[1])
                future_to_article[future] = item[0]

            for future_summary in future_to_article_summary:
                document_summary = future_to_article_summary[future_summary]
                try:
                    summary.append(future_summary.result())
                except Exception as exc:
                    print(f'An error occurred while generating Summary report for {document_summary}: {exc}')

            for future_clinical in future_to_article_clinical:
                document = future_to_article_clinical[future_clinical]
                try:
                    clinical_data.append(future_clinical.result())
                except Exception as exc:
                    print(f'An error occurred while generating Clinical report for {document}: {exc}')

            for future in future_to_article:
                document_ref = future_to_article[future]
                try:
                    references.append(future.result())
                except Exception as exc:
                    print(f'An error occurred while generating Reference report for {document_ref}: {exc}')
    else:
        print("Trials data is not in the expected format.")

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


def get_relevant_clinical_study(inquiry_details):
    trial_study_list = []
    article = {}
    document_name = [os.path.splitext(os.path.basename(source))[0] for source in inquiry_details.document_source]
    for document in document_name:
        article[document] = get_es_document(document)
        cite_id = citation_order.get(document)
        study_json = generate_report(inquiry_details, article[document], "study", cite_id)
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


def get_relevant_pages(inquiry_details):
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

    article_data = get_es_data(json.dumps(target_query))
    result = add_citation_id(article_data)
    return result


def get_reference_pi_data(pi_document_name, pi_details):
    with open("config/prompt_pi_reference.txt", "r") as file:
        prompt_text = file.read()
    cite_id = citation_order.get(pi_document_name)
    prompt = prompt_text.format(article=pi_details, cite_id=cite_id)

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

    pi_reference = response['choices'][0]['message']['content']
    print(pi_reference)
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


def add_citation_id(data):
    print(citation_order)
    for item in data:
        cite_id = citation_order.get(item['document_name'])
        if cite_id:
            item.update({'cite_id': cite_id})
        else:
            print(f"No cite_id found for document {item['document_name']}. Leaving unchanged.")
    return data

def get_cleaned_content(inquiry_details: InquiryDetails):
    clinical_json = {
        "Safety": {
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
            "Study Limitations": null,
            "Author Conclusions": null
        },
        "Study Results": {
            "Characteristics of study population": ["Age range", "Gender distribution"],
            "Primary efficacy endpoints": null,
            "Secondary efficacy endpoints": null,
            "Statistical significance": null,
            "Confidence interval": null
        }
    }
    notes = inquiry_details.additional_notes
    if inquiry_details.additional_notes:
        notes = check_exclusion(inquiry_details.additional_notes)
        if(notes != inquiry_details.additional_notes):
            with open(f"config/prompt_exclusion.txt", "r") as file:
                prompt_text = file.read()

            prompt = prompt_text.format(inquiry=inquiry_details.inquiry, notes = inquiry_details.additional_notes, clinical_json=clinical_json)

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
            clinical_json = response['choices'][0]['message']['content']
            print(clinical_json)
    safety, study_results = get_required_content(clinical_json), notes
    print(notes)
    return safety, study_results, notes


def get_required_content(clinical_content_json):
    try:
        data = json.loads(clinical_content_json)

        safety_string = get_content_keys(data, "Safety")
        study_results_string = get_content_keys(data, "Study Results")
        return safety_string, study_results_string

    except json.JSONDecodeError:
        return None, None

def get_content_keys(data, content_key):
    results = data.get(content_key, {})

    def convert_value(value):
        if isinstance(value, list):
            return f"({', '.join(map(str, value)) if value else ''})"
        elif value is None:
            return 'N/A'
        else:
            return str(value)

    results_data = []
    for key, value in results.items():
        converted_value = convert_value(value)
        if converted_value != 'N/A':
            results_data.append(f"{key}: {converted_value}")
        else:
            results_data.append(f"{key}")

    results_string = f"{content_key} including {', '.join(results_data).strip()}"
    return results_string

def check_exclusion(notes):
    prompt = f"Please identify if the notes have any exclusion specified in it. Notes:{notes}. If yes, remove the exclusion criteria and return the remaining content in response. If no, return the given notes as response. DONOT add any additional text or comment to response"
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
    cleaned_notes = response['choices'][0]['message']['content']
    return cleaned_notes
