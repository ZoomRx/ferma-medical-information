
from copy import deepcopy
from string import Template
import time
from urllib.parse import quote
import warnings

import cohere

from sentry_sdk import capture_exception

if __name__ == "__main__":
    import sys
    sys.path.append(".")

from helpers.gcs_utils import text_from_gcs
from helpers.vector_utils import get_embedding
from config.es_settings import es_constants as constants
from config.settings import creds, app_config, chat_config, prompts_bucket
from db.es_utils import elastic_query_builder
from helpers.openai_utils import ChatGPT
from helpers.teams_utils import system_alerts_webhook
from middlewares.custom_logger import log
from services.modules.es_parent_module import ESParentModule


warnings.filterwarnings("ignore")


class ESVectorSearchModule(ESParentModule):

    def __init__(self, meta_data_start_index, user):
        super().__init__(user)

        self.meta_data_start_index = meta_data_start_index
        self.team_config = user.team_config

        # ES query sources_list to be updated based on the data structure
        self.sources_list = []
        self.gpt_model = creds.openai.DEFAULT_MODEL
    def generate_base_query(
        self,
        fallback=False,
        is_highlight_query=False
    ):
        """Generates the base query to search using the boolean query"""

        if fallback:
            must_boolean_input = self.must_boolean_input.replace(
                " AND ", " OR ")
            should_boolean_input = self.should_boolean_input.replace(
                " AND ", " OR ")
        else:
            must_boolean_input = self.must_boolean_input
            should_boolean_input = self.should_boolean_input

        FIELDS_SET = set()
        fields_list_type = 'UNSTRUCTURED_SEARCH_FIELDS_LIST'

        if is_highlight_query:
            fields_list_type = 'UNSTRUCTURED_HIGHLIGHT_FIELDS_LIST'

        for index_boost_dict in self.indices_boost_list:
            for index_name in index_boost_dict:
                FIELDS_SET.update(
                    self.MODULE_CONSTANTS[index_name].get(f'{fields_list_type}', "*"))
                self.embeddings_field_name = self.MODULE_CONSTANTS[index_name]["embeddings_field_name"]

        FIELDS_LIST = list(FIELDS_SET)  # ["id", "title", "content"]

        base_query = {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "data_source": self.data_source
                            }
                        }],
                    "must": [
                        {
                            "query_string": {
                                "query": f"{must_boolean_input}",
                                "fields": FIELDS_LIST
                            }
                        }],
                    "should": [{
                        "query_string": {
                            "query": f"{should_boolean_input}",
                            "fields": FIELDS_LIST
                        }
                    }]
                }
            }
        }

        if not is_highlight_query:
            base_query['query']['bool']['must'][0]['query_string']['default_operator'] = 'AND'
            base_query['query']['bool']['should'][0]['query_string']['default_operator'] = 'OR'

        return base_query

    def get_synonyms_hierarchies_query(
        self,
        base_query_type
    ):
        """
        - Generates the base query based on the base_query_type
        - Adds synonyms and hierarchies analyzers to the generated base query
        """

        is_highlight_query = False
        fallback = False

        if base_query_type == 'base':
            pass
        elif base_query_type == 'highlight_base':
            is_highlight_query = True
        elif base_query_type == 'fallback_base':
            fallback = True
        elif base_query_type == 'highlight_fallback_base':
            is_highlight_query = True
            fallback = True

        formed_base_query = self.generate_base_query(
            fallback=fallback,
            is_highlight_query=is_highlight_query
        )

        return elastic_query_builder.get_query_with_synonyms_hierarchies(
            formed_base_query,
            is_highlight_query=is_highlight_query
        )

    def get_es_results(self, question_embeddings, must_boolean_input, should_boolean_input, output_fields):
        """
        - Queries the appropriate ES indices using the queries formed and returns the ES results
        """
        try:
            log(data={
                'event_details': {
                    'module': 'es-vector-search',
                    'action': 'execute-es-vector-search-query'
                },
                'tag': ["sub_question", "data"]
            })

            indices_list = []

            for index_boost_dict in self.indices_boost_list:
                for index_name in index_boost_dict:
                    indices_list.append(index_name)

            self.must_boolean_input = must_boolean_input
            self.should_boolean_input = should_boolean_input
            synonyms_hierarchies_query = self.get_synonyms_hierarchies_query(
                base_query_type='base'
            )

            for index in indices_list:
                self.sources_list.extend(self.MODULE_CONSTANTS[index]['unstructured_output_fields'])

            self.sources_list.extend(output_fields)

            # Hybrid search query to apply vector search on the documents obtained from the key-word search query
            vector_query = {
                "size": self.ES_RESULTS_FETCH_SIZE,
                "_source": self.sources_list,
                "indices_boost": self.indices_boost_list,
                "query": synonyms_hierarchies_query['query'],
                "knn": {
                    "field": self.embeddings_field_name,
                    "query_vector": question_embeddings,
                    "k": 10,
                    "num_candidates": 50,
                    "boost": 0.1,
                    "filter":[
                        {
                            "terms":{
                                "data_source": self.data_source
                            }
                        }
                    ]
                },
                "highlight": {
                    "fields": {
                        "*": {
                            "pre_tags": "<em>",
                            "post_tags": "</em>"
                        }
                    }
                }
            }

            start_time = time.time()
            es_data = self.search_in_es(
                query=vector_query,
                indices_names=indices_list
            )

            log(data={
                'transaction': {
                    'name': app_config.TRANSACTION_NAME_TRACEBACK},
                'event_details': {
                    'input': vector_query,
                    'outcome': 'success',
                    'duration': time.time() - start_time,
                    'labels': {'indices': indices_list},
                    'output': es_data,
                    'raw_output': es_data
                }
            }, publish=True)
        except Exception as e:
            capture_exception(e)
            system_alerts_webhook.capture_exception(e, {
                "Event": "Q&A - ES Vector Query",
                "User Email": self.user.email_id
            })
            es_data = ""

            log(data={
                'transaction': {
                    'name': app_config.TRANSACTION_NAME_TRACEBACK},
                'event_details': {
                    'outcome': 'failure',
                },
                'error': {
                    'message': f"Exception while fetching the response from Vector Search in Elastic search : {str(e)}"
                }
            }, publish=True)

        return es_data

    def update_citation(self, match, matches, citations, doc_index, title):
        """
        - Function to modify the sub-citations present in the context 
            based on the index of the document in ES results
        - doc_index: Index of the document n the ES results
        - Using (title)_(updated_citation) to represent external URLs in the sources
        """
        matched_text = match.group(
            0)  # pattern matching the citation format [index](url)
        url = matched_text[matched_text.find('(')+1:matched_text.rfind(')')]
        updated_index = f"{doc_index}.{citations[matches.index(matched_text)]}"
        updated_citation = f"[{updated_index}]({url})"
        self.agent_x_meta_data_sub_citations.update(
            {float(updated_index): {"title": title + "_" + updated_index, "link": url}})
        return updated_citation

    def frame_prompt(self, question):
        """Frame the bool query request prompt with examples and questions"""
        output_parser = ''

        prompt_file = chat_config.prompt_file(self.card_id, "es_bool_query")
        bool_query_prompt = text_from_gcs(self.user.subdomain, prompt_file)
        if not bool_query_prompt:
            raise Exception("Unstructured ES bool query prompt missing for the card:", self.card_id)
        bool_query_prompt = Template(bool_query_prompt)

        bool_query_prompt = bool_query_prompt.substitute(
            search_query=question
        )

        # event: es-vector-search bool query logs
        log(data={
            'event_details': {
                'module': 'es-vector-search',
                'labels': {
                    'prompt_file': f"{self.user.subdomain}/{prompt_file}",
                }
            }
        })
        return bool_query_prompt, output_parser

    def get_gpt_bool_output(self, question):
        """
        - Generates GPT Boolean query output foe the input question
        """
        prompt, output_parser = self.frame_prompt(question)
        gpt_bool_output = self.get_bool_query(prompt, output_parser)

        # including phase related information to be present in the should query
        should_haves = ["should_have", "must_have_phases"]
        if isinstance(gpt_bool_output, dict):
            updated_must_have_bool_values_list = []
            updated_should_have_bool_values_list = []
            for bool_type, bool_value in gpt_bool_output.items():
                if bool_type != "output_fields" and bool_value:
                    updated_bool_value = bool_value.replace(' AND ', ' OR ')
                    gpt_bool_output[bool_type] = updated_bool_value
                    if bool_type not in should_haves:
                        updated_must_have_bool_values_list.append(
                            updated_bool_value)
                    else:
                        updated_should_have_bool_values_list.append(
                            updated_bool_value)

            gpt_bool_output['must_have'] = '(' + ' OR '.join(
                updated_must_have_bool_values_list) + ')'
            gpt_bool_output['should_have'] = '(' + ' OR '.join(
                updated_should_have_bool_values_list) + ')'

            if gpt_bool_output['should_have'] == '()':
                gpt_bool_output['should_have'] = ""
        else:
            gpt_bool_output = {}
            gpt_bool_output['must_have'] = ""
            gpt_bool_output['should_have'] = ""
            gpt_bool_output["output_fields"] = []


        return (gpt_bool_output)

    def format_es_result(self, es_data, output_fields):
        """
        - Function to format the ES results using data specific techniques
        - To be updated when working on new data accordingly based on the data structure
        """
        results_list = []
        doc_index = self.meta_data_start_index
        for result in es_data:
            index_config = constants.MODULE_CONSTANTS[result['_index']]
            metadata = ""
            abstract_url = result["_source"].get("abstract_url", "")
            url = result["_source"].get("url", "")
            abstract_title = result["_source"].get("abstract_title", "")
            title = result["_source"].get("title", "")
            page_num = result["_source"].get("page_num", "")

            url = "/".join(url.split("/")[:-2]) + "/" + quote("/".join(url.split("/")[-2:]), safe='/?#=')
            content = ""
            is_key_present = True

            # to check if data is present in any of the output fields identified
            # if data for all the fields is "" in a document, it is not added in the context
            if output_fields:
                is_key_present = any(result["_source"].get(element, "") != "" for element in output_fields)
            
            if not(is_key_present):
                continue

            ES_FIELD_MAPPINGS = index_config['UNSTRUCTURED_ES_FIELD_MAPPINGS']
            for field, mapping_value in ES_FIELD_MAPPINGS.items():
                if mapping_value and field!="content":
                    field_value = str(result.get('_source', {}).get(field, ''))
                    if field == "url":
                        field_value = url
                    if field_value: 
                        metadata += mapping_value + ': ' + \
                        field_value + '\n'
                else:
                    field_value = str(result.get('_source', {}).get(field, ''))
                    if field == "content" and field_value:
                        content += mapping_value + ': ' + "\n" + \
                            field_value + '\n'
            doc_index += 1
            if content != "":
                results_list.append({
                    "title": title + f"_page_no_{page_num}",
                    "url": url,
                    "metadata": metadata,
                    "content": content
                })

        return results_list

    def rerank_results(self, question, results_list):
        # Use cohere rerank
        co = cohere.Client(creds.cohere.api_key)
        reranked_response = co.rerank(
            query=question,
            documents=[x['content'] for x in results_list],
            model=creds.cohere.rerank_model,
            top_n=10
        )

        reranked_results = []
        reranked_indices = []
        for r in reranked_response.results:
            print(r.index, end=", ")
            reranked_indices.append(r.index)
            reranked_results.append(results_list[r.index])

        log(data={
            'event_details': {
                'labels': {
                    'reranked indices': reranked_indices
                }
            }
        })
        return reranked_results

    def trim_agent_x_context(self, final_string):
        """
        - Trims the final context formed from the ES results to be withing the permitted context_length
        """
        MAX_CONTEXT_SIZE = constants.MODULE_DEFAULT_VALUES["BYOD_ES_TOTAL_TOKEN_LIMIT"]

        chatgpt = ChatGPT(self.team_config)
        if chatgpt.num_tokens_from_messages(final_string, self.gpt_model) > MAX_CONTEXT_SIZE:
            # Shortening the result length in case too long for agent_x
            final_next_line = chatgpt.get_truncated_token_string(
                final_string, self.gpt_model, max_token_limit=MAX_CONTEXT_SIZE
            ).rfind('\n\n')
            if final_next_line != -1:
                final_string = final_string[:final_next_line + 1]
            final_string = final_string + '\n'

        return (final_string)

    def get_module_results(self, args):
        """
        Function to get the results from the ES query,
        formatting them to form a string that can be passed as context to agent_x
        """

        question, self.question_type, indices, data_source, card_id = args

        self.card_id = card_id
        self.data_source = data_source
        self.indices_boost_list = indices
        es_results = []
        start_time = time.time()
        question_embeddings, cost = get_embedding(self.team_config, question)
        question_embeddings = list(question_embeddings)

        log(data={
            'transaction': {
                'name': app_config.TRANSACTION_NAME_TRACEBACK
            },
            'event_details': {
                'module': 'es-vector-search',
                'action': 'get-question-embeddings',
                'input': question,
                'duration': time.time() - start_time,
                'cost': cost,
                'labels': {"embeddings_generation_model": "text-embedding-ada-002"},
                'output': question_embeddings
            },
            'tag': ["sub_question", "data"]
        }, publish=True)

        gpt_bool_output = self.get_gpt_bool_output(question)

        must_boolean_input = gpt_bool_output['must_have']

        # For empty must_have cases, we can copy the value from should_have
        if not must_boolean_input or must_boolean_input == '()':
            must_boolean_input = gpt_bool_output.get("should_have", "")
            gpt_bool_output["should_have"] = ""

        output_fields = gpt_bool_output.get("output_fields", [])
        es_results = self.get_es_results(
            question_embeddings,
            must_boolean_input=must_boolean_input,
            should_boolean_input=gpt_bool_output['should_have'],
            output_fields=output_fields
        )

        final_string = ""
        log(data={
            'event_details': {
                'module': 'es-vector-search',
                'action': 'format-es-results'
            },
            'tag': ["sub_question", "data"]
        })

        start_time = time.time()
        es_data = list(es_results.get("hits", {}).get("hits", []))

        # Function call to format the results according to the data format
        results_list = self.format_es_result(es_data, output_fields)

        if len(results_list) == 0:
            results_list = self.format_es_result(es_data, [])

        question_terms = self.extract_question_terms(gpt_bool_output)
        matched_kg_terms = self.get_matched_kg_terms(deepcopy(es_data))
        synonyms_data = self.get_synonyms(question_terms, matched_kg_terms)

        results_list = [{"title": result["title"], "url": result["url"], "content": result["metadata"] + result["content"]} for result in results_list]

        # adding related terms from the context to the question to improve rerankig accuracy
        question = question + "\nRELATED TERMS:\n" + synonyms_data
        reranked_results = results_list
        if results_list:
            reranked_results = self.rerank_results(question, results_list)

        for result in reranked_results:
            self.agent_x_meta_data.update({
                self.meta_data_start_index: {
                    "title": result["title"], "link": result["url"]}
            })
            result_string = f"""Index: {int(self.meta_data_start_index)}\n"""
            final_string += result_string + result["content"] + "\n\n\n"

            self.meta_data_start_index += 1

        final_string = self.trim_agent_x_context(final_string)

        log(
            data={
                'transaction': {
                    'name': app_config.TRANSACTION_NAME_TRACEBACK
                },
                'event_details': {
                    'input': es_data,
                    'duration': time.time() - start_time,
                    'output': final_string
                },
                'tag': ["sub_question", "data"]
            },
            publish=True
        )

        return {"final_string": final_string, "synonyms_data": synonyms_data}


if __name__ == '__main__':
    from db.mysql_utils import get_db
    from config.tenant_settings import TenantSettings
    from routers.schemas.users import UserSchema

    subdomain = "astrazeneca-demo"
    tenant_config = TenantSettings(subdomain)
    user = UserSchema(**{
        'id': "Uuy9GmRxULNLipeVem90OoD0GTF3",
        'team_id': 1,
        'email_id': "sunny.jain@zoomrx.com",
        'subdomain': subdomain,
        "tenant_db": tenant_config.get_mysql_db_info(),
        "team_config": tenant_config.get_team_config(1)
    })

    input_question = "What opportunities exist to improve Calquence sales rep performance?"
    es_vector_search_module = ESVectorSearchModule(1, user)
    question_type = "Summary"
    print(
        es_vector_search_module.get_module_results([
            input_question,
            question_type,
            [{"byod_astrazeneca_demo_team_1_embeddings": 5}],
            ["PET Reports"],
            1
        ])
    )
