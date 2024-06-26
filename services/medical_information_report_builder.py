# Import necessary libraries
import json
from datetime import time, datetime

import openai
import requests

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
def generate_report(inquiry_details, article_summaries, content="all"):
    title = inquiry_details.document_title
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    summary = inquiry_details.summary_section
    additional_notes = inquiry_details.additional_notes

    article_content = "{" + ", ".join([f"'{content}'" for content in article_summaries]) + "}"

    if content == "all":
        prompt_file = "prompt_srl.txt"
    elif content == "summary":
        prompt_file = "prompt_summary.txt"
    elif content == "overview":
        prompt_file = "prompt_overview.txt"
    elif content == "clinical_data":
        prompt_file = "prompt_clinicaldata.txt"
    elif content == "results":
        prompt_file = "prompt_results.txt"

    with open(f"config/{prompt_file}", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(title=title, inquiry=inquiry, inquiry_type=inquiry_type, summary=summary,
                                additional_notes=additional_notes, article_content=article_content)

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
    # Extract the content from the response
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

    azure = AzureDocIntelligence()
    doc_intell_response_obj, doc_intell_response_dict = azure.get_raw_output(
        local_inp_file_path=f"storage/data/{file_name}")

    processed_content = azure.get_processed_output(raw_output_obj=doc_intell_response_obj)
    processed_content.to_json("processed.json", orient="records", indent=4)

    with open("processed.json") as file:
        content_json = file.read()

    # Load the JSON string from the file
    article = json.dumps(content_json)

    with open("config/prompt_extract.txt", "r") as file:
        prompt_text = file.read()

    prompt = prompt_text.format(inquiry=inquiry, inquiry_type=inquiry_type, article=article)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role "
                    "involves responding to clinical inquiries from healthcare professionals (HCPs) by providing "
                    "accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"{prompt}"
         }
    ]
    print(conversation)
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

    with open("summary_content.txt", "w") as file:
        file.write(article_summary)

    return article_summary


# Function to convert the array to a text format
def convert_to_text_format(types):
    text = ""
    for inquiry_type in types:
        text += f"{inquiry_type.type} ({', '.join(inquiry_type.categories)}), "
    return text.rstrip(", ")  # Remove trailing comma and space


def generate_content(inquiry_details: InquiryDetails):
    summaries = []

    for filename in inquiry_details.document_source:
        article_summary = generate_summary(inquiry_details, filename)
        summaries.append(article_summary)

    srl_content = generate_report(inquiry_details, summaries)

    # srl_content = generate_report(inquiry_details, summaries, "summary")

    # srl_content = extract_srl_overview(inquiry_details, summaries)

    # srl_content = extract_clinical_data(inquiry_details, summaries)

    # srl_content = extract_clinical_results(inquiry_details, summaries)

    return srl_content
