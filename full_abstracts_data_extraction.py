import io
import math
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus
import multiprocessing as mp

import openai
import json
import pandas as pd
import chardet
from elasticsearch import Elasticsearch
from openai import AzureOpenAI

from datetime import datetime

openai.api_type = "azure"
openai.api_version = "2024-08-01-preview"
openai_api_key = '5367eef3fa0d4dbc8301fc548fcdc6e6'  # Azure OpenAI API Key
openai.api_base = 'https://ferma-engine-test.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview'

# Folder path where PDFs are located
output_jsonl_file = "full_abstracts_output_file.jsonl"

client = AzureOpenAI(
    api_key = "5367eef3fa0d4dbc8301fc548fcdc6e6",
    api_version="2024-08-01-preview",
    azure_endpoint="https://ferma-engine-test.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"
)

def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
    return chardet.detect(raw_data)['encoding']


def read_full_abstracts(file_path):
    # Detect the encoding of the file
    #detected_encoding = detect_encoding(file_path)
    detected_encoding ="ISO-8859-1"
    # Read the CSV file in binary mode
    with open(file_path, 'rb') as file:
        raw_data = file.read()

    # Decode the raw data using the detected encoding
    decoded_data = raw_data.decode(detected_encoding)

    # Convert the decoded string to bytes again
    encoded_bytes = decoded_data.encode('utf-8')

    # Read the CSV-like data
    #csv_string = io.StringIO(encoded_bytes.decode('utf-8'))
    #full_abstract_df = pd.read_csv(csv_string)
    full_abstract_df = pd.read_csv(file_path, encoding=detected_encoding)

    # Extract full_abstract column
    full_abstracts = full_abstract_df['full_abstract'].tolist()

    return full_abstract_df

# Function to send the extracted text to Azure OpenAI and get a response
def get_openai_response(abstract_text):
    with open("/Users/zoomr/ferma-medical-information/config/full_abstract_extraction.txt",
              "r") as file:
        prompt_text = file.read()
    prompt = prompt_text.format(input=abstract_text)
    start_time = time.time()
    response = client.chat.completions.create(
        model="deployment-name",  # Replace with your actual deployment name
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=4000,
        response_format={"type": "json_object"},
        temperature=0,
        top_p=0
    )
    end_time = time.time() - start_time

    return response.choices[0].message.content.strip(), response.usage.completion_tokens, response.usage.prompt_tokens, response.usage.total_tokens,end_time

def process_abstracts_old(df):
    output_token = 0
    prompt_token = 0
    total_token = 0
    with open(output_jsonl_file, 'w') as jsonl_file:
        for _, row in df.iterrows():
            abstract = row['full_abstract']
            if(str(abstract) != "nan"):
                openai_response, output_token, prompt_token, total_token = get_openai_response(abstract)
            else:
                openai_response = """["{\n  \"Output\": {\n    \"category\": \"-\",\n    \"trial_identifier\": \"-\",\n    \"trial_acronym\": \"-\",\n    \"primary_drug\": \"-\",\n    \"secondary_drug\": \"-\",\n    \"comparator_drug\": \"-\",\n    \"indication\": \"-\",\n    \"disease\": \"-\",\n    \"phase\": \"-\",\n    \"sponsor\": \"-\",\n    \"introduction\": \"-\",\n    \"study_design\": \"-\",\n    \"results_discussion\": \"-\",\n    \"safety_results\": \"-\",\n    \"conclusion\": \"-\"\n  }\n}"]"""
                output_token = 0
                prompt_token = 0
                total_token = 0
            # Process the abstract

            processed_data = {
                "session_id": row['session_id'],
                "congress_id": row['congress_id'],
                "internal_id": row['internal_id'],
                "abstract_id": row['abstract_id'],
                "abstract_link": row['abstract_link'],
                "session_title": row['session_title'],
                "session_type": row['session_type'],
                "abstract_title": row['abstract_title'],
                "clinical_trial": row['clinical_trial'],
                "date" : row['start_date'],
                "disease" : row['disease'],
                "drug" : row['drug'],
                "indication" : row['indication'],
                "primary_drug" : row["primary_drug"],
                "secondary_drug": row["secondary_drug"],
                "comparator_drug": row["comparator_drug"],
                "drug_class" : row["drug_class"],
                "sponsor" : row["sponsor"],
                "catalyst_keywords" : row["catalyst_keywords"],
                "nct_acronym" : row["nct_acronym"],
                "patient_subgroup" : row["patient_subgroup"],
                "classification" : row["classification"],
                "authors" : row['authors'],
                "default_priority": row["default_priority_id"],
                "priority" : row["priority"],
                "authors" : row["authors"],
                "conference_name" : "ASH 2023",
                "time_zone" : "",
                "location" : row["location"],
                "openai_response": {openai_response},  # Placeholder for OpenAI response
                "completion_token": {output_token},
                "prompt_token": {prompt_token},
                "total_tokens": {total_token}
            }
            # Write to JSONL file
            # Convert sets to lists
            processed_data = {k: v if not isinstance(v, set) else list(v) for k, v in processed_data.items()}

            # Write to JSONL file
            jsonl_file.write(json.dumps(processed_data) + "\n")
            print(f"Processed abstract: {row['session_title']}")

def process_abstracts(df):
    num_threads = 5
    '''with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for _, row in df.iterrows():
            future = executor.submit(process_abstract, row)
            futures.append(future)

        # Collect results
        results = []
        for future in futures:
            results.append(future.result())

    # Write results to JSONL file
    with open(output_jsonl_file, 'w') as jsonl_file:
        for result in results:
            jsonl_file.write(result + '\n')'''

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        for _, row in df.iterrows():
            future = executor.submit(process_abstract, row)

            # Write partial results to file
            with open(output_jsonl_file, 'a') as jsonl_file:
                jsonl_file.write(json.dumps(future.result()) + '\n')

    # Close the file
    output_jsonl_file.close()

    print("Processing completed.")

def process_abstract(row):
    output_token = 0
    prompt_token = 0
    total_token = 0

    abstract = row['full_abstract']

    if str(abstract) != "nan":
        openai_response, output_token, prompt_token, total_token, response_time = get_openai_response(abstract)
    else:
        openai_response = """["{\n  \"Output\": {\n    \"category\": \"-\",\n    \"trial_identifier\": \"-\",\n    \"trial_acronym\": \"-\",\n    \"primary_drug\": \"-\",\n    \"secondary_drug\": \"-\",\n    \"comparator_drug\": \"-\",\n    \"indication\": \"-\",\n    \"disease\": \"-\",\n    \"phase\": \"-\",\n    \"sponsor\": \"-\",\n    \"introduction\": \"-\",\n    \"study_design\": \"-\",\n    \"results_discussion\": \"-\",\n    \"safety_results\": \"-\",\n    \"conclusion\": \"-\"\n  }\n}"]"""
        output_token = 0
        prompt_token = 0
        total_token = 0
        response_time = 0

    processed_data = {
        "session_id": row['session_id'],
        "congress_id": row['congress_id'],
        "internal_id": row['internal_id'],
        "abstract_id": row['abstract_id'],
        "abstract_link": row['abstract_link'],
        "session_title": row['session_title'],
        "session_type": row['session_type'],
        "abstract_title": row['abstract_title'],
        "clinical_trial": row['clinical_trial'],
        "date": row['start_date'],
        "disease": row['disease'],
        "drug": row['drug'],
        "indication": row['indication'],
        "primary_drug": row["primary_drug"],
        "secondary_drug": row["secondary_drug"],
        "comparator_drug": row["comparator_drug"],
        "drug_class": row["drug_class"],
        "sponsor": row["sponsor"],
        "catalyst_keywords": row["catalyst_keywords"],
        "nct_acronym": row["nct_acronym"],
        "patient_subgroup": row["patient_subgroup"],
        "classification": row["classification"],
        "authors": row['authors'],
        "default_priority": row["default_priority_id"],
        "priority": row["priority"],
        "authors": row["authors"],
        "conference_name": "ASH 2023",
        "time_zone": "",
        "location": row["location"],
        "openai_response": f"{openai_response}",  # Placeholder for OpenAI response
        "completion_token": f"{output_token}",
        "prompt_token": f"{prompt_token}",
        "total_tokens": f"{total_token}",
        "response_time": f"{response_time}"
    }

    processed_data = {k: v if not isinstance(v, set) else list(v) for k, v in processed_data.items()}
    print(f"Processed abstract: {row['session_title']}")
    return json.dumps(processed_data)


# Assuming df is your DataFrame and output_jsonl_file is your desired output file path
def generate_full_abstract_summary(file_path):
    # Step 1: Read full abstract text from the csv
    full_abstract_df = read_full_abstracts(file_path)
     #Step 2: Process the full abstract to generate summaries
    process_abstracts(full_abstract_df)
    # Step 3: Load the JSONL file and convert to a DataFrame
    generate_full_abstract_summary_output(output_jsonl_file, "summary_output_latest.csv")

def generate_full_abstract_summary_output(input_jsonl_file, output_csv_file):
    # Step 1: Load the JSONL file and convert to a DataFrame
    data_list = []
    final_dict : dict
    with open(input_jsonl_file, 'r') as jsonl_file:
        for line in jsonl_file:
            data = json.loads(line)
            parsed_json = json.loads(json.dumps(data['openai_response']))  # Note: Changed from openai_response to openai_response[0]
            output_data = json.loads(parsed_json[0])
            generated_data = output_data['Output']
            planner_data = json.loads(line)
            abstract_id = planner_data.get('abstract_id')
            if math.isnan(abstract_id):
                content = "-"
            else:
                content = f"Introduction:{generated_data['introduction']}\nstudy design: {generated_data['study_design']} \nResults discussion: {generated_data['results_discussion']}\nsafety results: {generated_data['safety_results']}\nconclusion: {generated_data['conclusion']}"

            generated_data['content'] = content
            del(generated_data['introduction'])
            del(generated_data['study_design'])
            del(generated_data['results_discussion'])
            del(generated_data['conclusion'])
            del(planner_data['openai_response'])
            #combined_dict = {**planner_data, **generated_data}
            print(generated_data)
            combined_dict = get_required_fields(generated_data, planner_data)
            data_list.append(json.loads(json.dumps(combined_dict)))

    # Convert list of JSON objects to DataFrame
    df = pd.DataFrame(data_list)
    #es_utils.write_es_data(df.fillna("").head(1))
    # Step 4: Save the DataFrame to CSV
    df.to_csv(output_csv_file, index=False)

    print(f"Processing complete. DataFrame saved to {output_csv_file}")

mapping = {"high": 1, "medium": 2, "low": 3}

def convert_to_number(level):
    return mapping.get(level.lower(), None)


def get_required_fields(generated_data, planner_data):
    # Initialize combined_dict if needed
    input_date = datetime.strptime(planner_data['date'], '%d/%m/%y %H:%M')
    formatted_date = input_date.strftime('%Y-%m-%d %H:%M:%S')
    print(formatted_date)
    year = input_date.strftime('%Y')

    combined_dict = {} #Sponsor
    combined_dict['_id'] = str(uuid.uuid4())
    combined_dict['session_id'] = planner_data['session_id']
    combined_dict['abstract_id'] = planner_data['abstract_id']
    combined_dict['url'] = planner_data['abstract_link']
    combined_dict['session_title'] = planner_data['session_title']
    combined_dict['session_type'] = planner_data['session_type']
    combined_dict['abstract_title'] = planner_data['abstract_title']
    combined_dict['category'] = generated_data['category']
    combined_dict['primary_drug'] = generated_data['primary_drug']
    combined_dict['secondary_drug'] = generated_data['secondary_drug']
    combined_dict['comparator_drug'] = generated_data['comparator_drug']
    combined_dict['indication'] = generated_data['indication']
    combined_dict['disease'] = generated_data['disease']
    combined_dict['patient_sub_group'] = planner_data['patient_subgroup']
    combined_dict['firm'] = planner_data['sponsor']
    combined_dict['drug_class'] = planner_data['drug_class']
    combined_dict['nct_and_acronym'] = planner_data['nct_acronym']
    combined_dict['phase'] = generated_data['phase']
    combined_dict['classification'] = planner_data['classification']
    combined_dict['date'] = formatted_date
    combined_dict['summary'] = generated_data['content']
    combined_dict['authors'] = planner_data['authors']
    combined_dict['priority'] = convert_to_number(planner_data['priority'])
    combined_dict['year'] = year
    combined_dict['conference_name'] = planner_data['conference_name']
    combined_dict['time_zone'] = "PDT"
    combined_dict['location'] = planner_data['location']

    # Add required fields here
    combined_dict['data_source'] = "3,4"
    common_keys = ['primary_drug', 'secondary_drug', 'comparator_drug', 'indication', 'disease']
    # Check if planner_data exists and has the same keys
    if generated_data and all(
            has_hyphen(generated_data.get(k, '')) or k in planner_data for k in generated_data.keys()):
        for key in common_keys:
            if planner_data[key] != generated_data.get(key, ''):
                if '-' in generated_data[key]:
                    combined_dict[key] = generated_data[key].replace('-', '')
                elif planner_data[key]:  # Only append if planner_data[key] is not empty
                    combined_dict[key] += ';' + str(planner_data[key])
    # Check if generated_data has any key with hyphen
    if generated_data and any(has_hyphen(generated_data.get(k, '')) for k in generated_data.keys()):
        # Replace hyphens with empty strings
        for key in generated_data.keys():
            if has_hyphen(generated_data.get(key, '')):
                combined_dict[key] = ''

    return combined_dict




def es_write(data):
    ES_USERNAME = "elastic"
    ES_PASSWORD = "c^ZADGTr74GxvthtPZ&%4#LG8"
    ES_EXT_HOST = "chat-elastic-dev.zoomrx.ai"
    ES_PORT = 9200

    username = ES_USERNAME
    password = ES_PASSWORD
    encoded_password = quote_plus(password.encode().decode('unicode_escape'))
    host = ES_EXT_HOST
    es = f"https://{username}:{encoded_password}@{host}:443"
    # Instantiate the Elasticsearch client
    es_client = Elasticsearch([es], verify_certs=True)
    index_name = 'ferma_byod_congress_demo'  # Replace with your desired index name
    doc_type = '_doc'  # Or leave blank for automatic type detection

    try:
        response = es_client.index(index=index_name, body=data)
        print(f"Indexed successfully. Response: {response}")
    except Exception as e:
        print(f"Error indexing data: {str(e)}")


def has_hyphen(s):
    return s == '-'

file_path = "ASH_2023_FullData.csv"
generate_full_abstract_summary(file_path)
