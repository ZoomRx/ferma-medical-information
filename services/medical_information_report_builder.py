# Import necessary libraries
import concurrent
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import time, datetime

import openai
import requests

from helpers.es_utils import get_es_data
from schemas.medical_info_inquiry import InquiryDetails
from services.azure_doc_intelligence import AzureDocIntelligence
from config import settings

# Set OpenAI API key
openai.api_key = settings.env.open_ai_key


# Helper function to fetch and parse content from URLs
def fetch_content(url):
    response = requests.get(url)
    return response.content


# Function to create a SRL document
def generate_report(inquiry_details, article_pages, content="all", data=""):
    title = inquiry_details.document_title
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    summary = inquiry_details.summary_section
    additional_notes = inquiry_details.additional_notes

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

    print(prompt_file)
    with open(f"config/{prompt_file}", "r") as file:
        prompt_text = file.read()

    # prompt = prompt_text.format(title=title, inquiry=inquiry, inquiry_type=inquiry_type, summary=summary,
    # additional_notes=additional_notes, article_content=article_content)
    if content == "clinical_data":
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content, trial_id=data)
    elif content == "title":
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content)
    else:
        prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article_content,title=data)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"""{prompt}"""
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

    print(f"Response Time for SRL content: {elapsed_time} seconds")
    srl_content = response['choices'][0]['message']['content']

    with open("srl_content.txt", "w") as file:
        file.write(srl_content)

    return srl_content


# Run the function to create the document
def generate_summary(inquiry_details, file_name):
    # title = inquiry_details.document_title
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        # Convert the inquiry to a text format
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    # summary = inquiry_details.summary_section
    # additional_notes = inquiry_details.additional_notes

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
    articles = get_relevant_pages(inquiry_details)
    srl_content = {}  # Initialize the dictionary if it hasn't been initialized yet

    title = generate_report(inquiry_details, articles, "title")
    srl_content["title"] = title
    srl_content["introduction"] = generate_report(inquiry_details, articles, "introduction", title)
    srl_content["summary"] = generate_report(inquiry_details, articles, "summary", title)

    clinical_data = fetch_clinical_data(inquiry_details, articles)
    srl_content["clinical_data"] = clinical_data
    srl_document = "\n\n".join(str(value) for value in srl_content.values())
    return srl_document


def fetch_clinical_data(inquiry_details, articles):
    trials = get_relevant_clinical_trials(inquiry_details, articles)
    report_type = "clinical_data"
    clinical_data = []
    with ProcessPoolExecutor() as executor:
        # Prepare arguments for each task
        args_list = [(inquiry_details, articles, report_type, trial) for trial in trials]

        # Submit all report generation tasks to the executor
        future_to_args = {executor.submit(generate_report_wrapper, args): args for args in args_list}

        for future in concurrent.futures.as_completed(future_to_args):
            args = future_to_args[future]
            try:
                content = future.result()
            except Exception as exc:
                print(f'An error occurred: {exc}')
            else:
                clinical_data.append(content)

    clinical_data_string = "\n".join(clinical_data)

    return clinical_data_string


def generate_report_wrapper(args):
    inquiry_details, articles, report_type, trial = args
    return generate_report(inquiry_details, articles, report_type, trial)


def get_relevant_clinical_trials(inquiry_details, articles):
    trials = generate_report(inquiry_details, articles, "trials")
    trials_list = trials.split(', ')
    return trials_list


def get_relevant_pages(inquiry_details):
    with open("config/prompt_keyword.txt", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(inquiry=inquiry_details.inquiry, title=inquiry_details.document_title,
                                summary=inquiry_details.summary_section, notes=inquiry_details.additional_notes)

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
    print(es_bool_query)
    es_bool_query = es_bool_query.replace("```", "")
    es_bool_query = es_bool_query.replace("json", "")
    json_data = json.loads(es_bool_query)
    print(json_data)
    transformed_json = transform_json(json_data)
    document_source = inquiry_details.document_source
    target_query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "query_string": {
                            "query": transformed_json["must_have"],
                            "fields": ["content^50", "page_title", "title"],
                            "default_operator": "AND",
                            "analyzer": "synonyms"
                        }
                    }
                ],
                "should": [
                    {
                        "query_string": {
                            "query": transformed_json["should_have"],
                            "fields": ["content^50", "page_title", "title"],
                            "default_operator": "OR",
                            "analyzer": "synonyms"
                        }
                    }
                ],
                "filter": [
                    {
                        "terms": {
                            "document_name": document_source
                        }
                    }
                ]
            }
        }
    }
    target_query["_source"] = {
        "includes": ["page_no", "content"]
    }
    print(target_query)
    result = get_es_data(target_query)
    return result


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
