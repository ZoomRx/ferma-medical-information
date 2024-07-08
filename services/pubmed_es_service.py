from typing import Optional, List

import requests
import json
import openai
from pydantic import BaseModel

from config import settings

openai.api_key = settings.env.open_ai_key

class Item(BaseModel):
    id: str
    title: str
    abstract: str
    url: str
    author: str
    id: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    affiliation: Optional[list[str]] = None
    article_date: Optional[str] = None
    publication_type: Optional[list[str]] = None
    journal_title: Optional[str] = None
    keywords: Optional[list[str]] = None


def get_pubmed_articles(query):
    url = "https://congress-elastic-dev.zoomrx.ai/ferma_chat_pubmed_prod_v1/_search"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Basic ZWxhc3RpYzo4ZWE3YW55elF4NSQkTFFWQ3E3JDkkemhD'
    }
    payload = json.dumps({
        "_source": [
            "id",
            "title",
            "abstract",
            "url",
            "author",
            "affiliation",
            "article_date",
            "publication_type",
            "journal_title",
            "keywords"
        ],
        "query": {
            "bool": {
                "should": [
                    {
                        "match": {
                            "abstract": f"{query}"
                        }
                    },
                    {
                        "match": {
                            "title": f"{query}"
                        }
                    }
                ]
            }
        },
        "size": 200
    })

    response = requests.request("GET", url, headers=headers, data=payload)
    data = response.json()
    hits_data = data['hits']['hits']
    items = [Item(**hit["_source"]) for hit in hits_data]
    filtered_items = [{"id": hit["_source"]["id"], "title": hit["_source"].get("title"), "abstract": hit["_source"].get("abstract"),"keywords": hit["_source"].get("keywords")} for hit in hits_data]

    return items, filtered_items


def get_relevant_pubmed_articles(inquiry, pubmed_article):
    prompt = f"""You are a Medical Information Specialist working for a pharmaceutical company. 
    From the below article represented as json, identify the articles relevant for the given inquiry - {inquiry}.
    The relevant articles MUST be identified using the content of title, abstract, keywords from the given input json.
    Return json output of relevant articles ONLY in the below format as a json string without any prefix.

    
     --output json--
    {{id:["35263519","32557601"]}}
    
    --input json--
    {pubmed_article}

    *IMPORTANT MANDATE-
    - The output should be ONLY the json retrieved.
    - DO NOT include any text in the output response.
    - DO NOT include any prefix like (json) in the output response"""

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves identifying the relevant citations for clinical inquiries from healthcare professionals (HCPs)"},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    pubmed_articles_identified = response['choices'][0]['message']['content']
    cleaned_content = pubmed_articles_identified.strip()  # Remove leading/trailing whitespace
    print(cleaned_content)
    return cleaned_content

def get_output_articles(cleaned_content, pubmed_article):
    try:
        articles_ids = json.loads(cleaned_content)
        updated_data = []
        ids = articles_ids['id']
        for article_id in ids:
            found_item = find_item_by_id(pubmed_article, article_id)
            if found_item:
                # Replace the original item with the found ItemList instance
                updated_item = found_item.dict()
                updated_item["abstract"] = get_summary(updated_item["abstract"])
                if updated_item["keywords"] is None:
                    updated_item["keywords"] = []
                if updated_item["article_date"] is None:
                    updated_item["article_date"] = "-"
                updated_data.append(updated_item)
            else:
                print(f"No item found with ID {id}")

        # Convert the updated list back to JSON
        updated_json = json.dumps(updated_data, indent=4)
        print(updated_json)
        return json.loads(updated_json)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON: {e}")


def get_relevant_keyword(inquiry):
    prompt = f"""You are a Medical Information Specialist working for a pharmaceutical company. 
    From the inquiry- {inquiry}, identify the drug and return ONLY the drug name."""

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves identifying the drug involved in clinical inquiries from healthcare professionals (HCPs)"},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    keyword = response['choices'][0]['message']['content']
    return keyword

def find_item_by_id(item_lists: List[Item], target_id: str) -> Optional[Item]:
    """Find an item by its ID."""
    for item in item_lists:
        if item.id == target_id:
            return item
    return None

def get_summary(abstract):
    prompt = f"SUMMARIZE the following Pubmed article abstract: {abstract} into a brief description that is EXACTLY within 500 characters long."
    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves summarizing the abstract of the Pubmed Article"},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    summary = response['choices'][0]['message']['content']
    print(abstract +"----------"+summary)
    return summary
def fetch_articles_based_on_inquiry(inquiry):
    keyword = get_relevant_keyword(inquiry.inquiry)
    # keyword = "ribociclib"
    pubmed_articles_json, filtered_pubmed_articles_json = get_pubmed_articles(keyword)
    articles = get_relevant_pubmed_articles(inquiry, filtered_pubmed_articles_json)
    extracted_articles = get_output_articles(articles, pubmed_articles_json )
    return extracted_articles
