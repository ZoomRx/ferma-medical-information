from urllib.parse import quote_plus
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from config import settings

username = settings.es.username
password = settings.es.password
encoded_password = quote_plus(password.encode().decode('unicode_escape'))
host = settings.es.ext_host
es = f"https://{username}:{encoded_password}@{host}:443"
# Instantiate the Elasticsearch client
es_client = Elasticsearch([es], verify_certs=True)
index_name = "ferma-mi-documents"


def write_es_data(processed_content):
    data = processed_content
    elastic_records = data.to_dict(orient='records')
    success, _ = bulk(
        es_client,
        ({"_index": index_name, "_source": doc}
         for doc in elastic_records)
    )
    return success


def get_es_data(query):
    # target_query = {
    #     "bool": {
    #         "must": [
    #             {
    #                 "query_string": {
    #                     "query": data["must_have_phases"],
    #                     "fields": ["content^50", "page_title", "title"],  # Placeholder fields, replace with actual fields
    #                     "default_operator": "AND"
    #                 }
    #             }
    #         ],
    #         "should": [
    #             {
    #                 "query_string": {
    #                     "query": data["should_have"],
    #                     "fields": ["content^50", "page_title", "title"],  # Placeholder fields, replace with actual fields
    #                     "default_operator": "AND"
    #                 }
    #             }
    #         ]
    #     }
    # }

    # Perform the search
    response = es_client.search(index=index_name, body=query)

    # Extracting the hits from the response
    hits = response['hits']['hits']

    # Converting the hits to a list of dictionaries
    result = [hit['_source'] for hit in hits]
    print(result)

    return result
