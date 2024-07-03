import requests
import json
import openai
from config import settings

openai.api_key = settings.env.open_ai_key

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
        "url"
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
        "size": 100
    })

    response = requests.request("GET", url, headers=headers, data=payload)

    data = json.loads(response.text)

    # Accessing the 'hits' array within the 'hits' dictionary
    hits_data = data['hits']['hits']
    return hits_data

def get_relevant_pubmed_articles(inquiry, pubmed_article):
    prompt = f"""You are a Medical Information Specialist working for a pharmaceutical company. 
    From the below article represented as json, identify the articles relevant to the inquiry - {inquiry} from the abstract and title in the json provided and return json output of relevant articles in the below format as a json string without any prefix:
    [{{
      "id": "32557601",
      "title": "Ribociclib Drug-Drug Interactions: Clinical Evaluations and Physiologically-Based Pharmacokinetic Modeling to Guide Drug Labeling.",
      "url": "https://pubmed.ncbi.nlm.nih.gov/32557601"
    }},
     {{
      "id": "35263519",
      "title": "Ribociclib Drug-Drug Interactions",
      "url": "https://pubmed.ncbi.nlm.nih.gov/35263519"
    }}]
    --input-json--
    {pubmed_article}

    *IMPORTANT MANDATE-
    The output should be ONLY the json retrieved.
    DO NOT include any text in the output response"""

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
    print("--------------------------------------------------------------------")
    print(pubmed_articles_identified)
    cleaned_content = pubmed_articles_identified.strip()  # Remove leading/trailing whitespace

    try:
        articles_json = json.loads(cleaned_content)
        print(articles_json)
        return articles_json
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON: {e}")

def get_relevant_keyword(inquiry):

    prompt=f"""You are a Medical Information Specialist working for a pharmaceutical company. 
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
    print(keyword)
    return keyword


def fetch_articles_based_on_inquiry(inquiry):
    keyword = get_relevant_keyword(inquiry.inquiry)
    #keyword = "ribociclib"
    pubmed_articles_json = get_pubmed_articles(keyword)
    articles = get_relevant_pubmed_articles(inquiry, pubmed_articles_json )
    return articles
