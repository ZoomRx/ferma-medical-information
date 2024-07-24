import json
import re
import requests
import time

from sentry_sdk import capture_exception
from typing import Dict, List

if __name__ == "__main__":
    import sys
    sys.path.append(".")

from config.settings import creds, app_config
from config.es_settings import es_constants
from db import es_utils
from helpers.openai_utils import AzureOpenAI
from helpers.teams_utils import system_alerts_webhook
from middlewares.custom_logger import log
from services.modules.aaas import annotations


class ESParentModule():

    def __init__(self, user):
        self.must_boolean_input = ''
        self.should_boolean_input = ''
        self.indices_boost_list = []
        self.date_filter_info_dict = {}
        self.team_config = user.team_config
        self.user = user

        self.log_data = {
            "bool_query": {},
            "search": {"cost": 0},
            "embeddings": {
                "cost": 0
            },
            'transaction': {}
        }

        self.traceback_log = {
            "bool_query": {},
            "search": {},
            "embeddings": {
                "snippets": {},
                "vectorsearch": {}
            }
        }

        self.agent_x_meta_data = {}
        self.agent_x_meta_data_sub_citations = {}

        # Most frequently changed ESConstants will be present this class
        # values for these constants will be taken at real-time from bucket, without any server restart
        self.ES_RESULTS_FETCH_SIZE = es_constants.MODULE_DEFAULT_VALUES["ES_RESULTS_FETCH_SIZE"]
        self.DEFAULT_DATE_FIELD = es_constants.MODULE_DEFAULT_VALUES["DEFAULT_DATE_FIELD"]
        self.REQUEST_TIME_OUT_TIME = es_constants.MODULE_DEFAULT_VALUES["REQUEST_TIME_OUT_TIME"]
        self.MODULE_CONSTANTS = es_constants.MODULE_CONSTANTS

    def get_bool_query(self, prompt, output_parser='', model_name=creds.openai.DEFAULT_MODEL):
        """ Gets the boolean query from GPT """

        self.traceback_log["bool_query"] = {"prompt": prompt}
        bool_query_start_time = time.time()

        log(data={
            'event_details': {
                'action': 'generate-es-bool-query',
                'input': prompt,
            },
            'tag': ["sub_question", "prompt"]
        })

        azure_openai = AzureOpenAI(self.team_config)
        gpt_bool_output, gpt_cost_metrics = azure_openai.generate_answer(
            prompt, model_name
        )

        log(data={
            'event_details': {
                'cost': gpt_cost_metrics['cost'],
                'raw_output': gpt_bool_output,
                'labels': {
                    'openai_api': azure_openai.openai_config.api_base,
                    'num_of_retries': gpt_cost_metrics['num_of_retries']
                }
            }
        })

        if "```json" in gpt_bool_output:
            gpt_bool_output = "\n".join(gpt_bool_output.split("\n")[1:-1])

        try:
            gpt_bool_output = re.sub(r'[\\/]+', ' ', gpt_bool_output)
        except Exception as e:
            # have the gpt_bool_output as it is
            # as error while getting results from ES is handled
            pass

        self.traceback_log["bool_query"].update({
            "response": gpt_bool_output
        })

        try:
            gpt_bool_output = eval(gpt_bool_output)
        except Exception as e:
            try:
                gpt_bool_output = output_parser.parse(gpt_bool_output)
            except Exception as e:
                try:
                    _output = gpt_bool_output.replace("Output: ", "").strip()
                    gpt_bool_output = eval(_output)
                except Exception as e:
                    gpt_bool_output = ""
        finally:

            if isinstance(gpt_bool_output, dict) and "boolean_query" in gpt_bool_output:
                try:
                    gpt_bool_output["boolean_query"] = json.loads(
                        gpt_bool_output["boolean_query"])
                except Exception as e:
                    gpt_bool_output["boolean_query"] = eval(
                        str(gpt_bool_output["boolean_query"]))

            self.traceback_log["bool_query"]["formatted_response"] = gpt_bool_output
            self.log_data["bool_query"].update(
                {"response_time": time.time() - bool_query_start_time})
            self.log_data["bool_query"].update(gpt_cost_metrics)

        # event: generate bool query
        log(data={
            'transaction': {
                'name': app_config.TRANSACTION_NAME_TRACEBACK},
            'event_details': {
                'outcome': 'success',
                'duration': time.time() - bool_query_start_time,
                'output': gpt_bool_output
            }
        }, publish=True)
        return gpt_bool_output

    def get_matched_kg_terms(self, es_result: List[Dict]) -> List:
        """Returns a list of matching phrases from the ES Results"""

        def get_matching_phrases(text: str) -> List:
            """Groups the sequentially matching terms and Returns list of matching phrases"""

            text = re.sub(r"</em>.<em>", " ", text)
            return re.findall(r"<em>(.*?)</em>", text)

        matched_phrases = set()
        for res in es_result:
            highlighted_data = res['highlight']
            for value in highlighted_data.values():
                matches = get_matching_phrases(value) if isinstance(value, str) else [
                    get_matching_phrases(text) for text in value][0]
                matched_phrases.update(matches)
        return list(matched_phrases)

    def format_es_results_as_str(self, es_results: list[Dict]):
        es_data = [
            {**data['_source']}
            for data in es_results['hits']['hits']
        ]
        es_data = ['\n'.join(f'{k}: {v}' for k, v in rec.items()) for rec in es_data]
        return "\n\n".join(es_data)

    def get_random_context(self, data_sources: list, size: int = 5) -> str:
        """
            Returns random records from elastic Elastic query to get random results
        """
        # final_query = deepcopy(es_congress_planner_search_constants.BASE_QUERY_TEMPLATE)
        query = {
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "bool": {
                            "filter": {
                                "terms": {
                                    "data_source": data_sources
                                }
                            }
                        }
                    },
                    "random_score": {
                    },
                    "boost_mode": "replace"
                }
            }
        }
        es_results = self.search_in_es(
            query=query,
            indices_names=[self.team_config.es_index]
        )
        return self.format_es_results_as_str(es_results)

    def search_in_es(self, query, indices_names):
        """Search the input query in ES index"""

        start_time = time.time()
        self.traceback_log["search"].update({
            "indices": indices_names,
            # "query": query,
        })
        response = {}

        try:
            log(data={
                'event_details': {
                    'input': query,
                    'labels': {'indicies': indices_names}
                },
                'tag': ["sub_question", "data"]
            })
            response = es_utils.es_db.con.search(
                index=indices_names,
                body=query,
                request_timeout=self.REQUEST_TIME_OUT_TIME
            )
            # event: execute es query
            log(data={
                'transaction': {
                    'name': app_config.TRANSACTION_NAME_TRACEBACK},
                'event_details': {
                    'outcome': 'success',
                    'duration': time.time() - start_time,
                    'output': response.get("hits", {}).get("hits", [])[:50],
                },
                'tag': ["sub_question", "data"]
            }, publish=True)

        except Exception as e:
            capture_exception(e)
            system_alerts_webhook.capture_exception(e, {
                "Event": "Q&A - ES Query",
                "User Email": self.user.email_id
            })
            self.log_data["transaction"].update(
                {"exception": f"Exception while fetching the response from Elastic search : {str(e)}"}
            )
            log(data={
                'transaction': {
                    'name': app_config.TRANSACTION_NAME_TRACEBACK},
                'error': {
                    'message': f"Exception while fetching the response from Elastic search : {str(e)}"
                }
            }, publish=True)
        finally:
            response_dict = response
            if not response_dict.get("hits", {}).get("hits"):
                response_dict = {'hits': {'hits': []}}
            return response_dict

    def get_synonyms(self, question_terms: list, answer_terms: list):
        """
        For terms in the question finds related terms from the answer
        and returns a string of this format

        "root_word1: synonym1, synonym2
         root_word2: synonym1, synonym2"

        Note: related terms -> synonyms, hierarchies
        """
        annotations_dict = annotations.get_es_synonyms(
            question_terms, answer_terms)
        print(f"Annotations - {annotations_dict}")

        synonyms_prompt = ''
        synonyms_sentence_template = "{root_term}: {synonyms}"
        for root, synonyms in annotations_dict.items():
            if synonyms:
                synonyms_prompt += '\n' + synonyms_sentence_template.format(
                    synonyms=', '.join(synonyms), root_term=root)

        return synonyms_prompt

    def extract_question_terms(self, gpt_bool_output):
        """
        Extracts terms from gpt bool output dictionary to be used to get annotations
        Sample Input:
            gpt_bool_output = {
                "must_have_drugs": "",
                "must_have_diseases": "(Breast Cancer)",
                "must_have_mechanism_of_action": "trastuzumab",
                "must_have_phases": "((Phase 1) OR (Phase 2))",
                "should_have_patient_subgroups": "(Her2 +ve)",
                "should_have_medical_terms": "((Palbociclib) AND (Chemotherapy))",
                "should_have_others": ""
            }
        output: [breast cancer, trastuzumab, her2 +ve, palbociclib, chemotherapy, phase 1, phase 2 ]
        """
        terms_list = []
        for term_type, term_string in gpt_bool_output.items():
            if term_type != "output_fields" and term_string:
                term_string = term_string.replace(
                    'OR', 'AND').replace('(', '').replace(')', '')
                terms_list.extend(
                    [term.strip().lower()
                     for term in term_string.split('AND') if term.strip()]
                )
        return terms_list

    def lowercase_keys_for_dict(self, input_dict):
        return {k.lower(): v for k, v in input_dict.items()}

    def get_annotation_result(self, query, custom_needles_file=None):
        BASE_URL = "https://aaas-web.ferma.ai/annotate"
        HEADERS = {
            "Authorization": "Bearer HL5NLBr2DspGLTDFNkPH8zrsasnPJMWvcB7AjTTg9mc3y"
        }
        payload = {
            "text": query,
            "kb_needles": "chat",  # Either "chat" or "congress"
            "sch_version": "v2",  # Special Character Handler's Version
            # "nct_mentions": True,
        }
        files = {
            'custom_needles_file': custom_needles_file
        }
        response = requests.post(url=BASE_URL, headers=HEADERS, data=payload, files=files)

        annotation_result = json.loads(response.content.decode(
            "utf-8")) if response.status_code >= 200 and response.status_code < 300 else []

        return annotation_result

    def format_annotation_result(self, annotation_result):
        knowledge_assistance = {}
        for result in annotation_result:
            knowledge_assistance.setdefault(result['label'].lower(), []).append(result['name'])
        return knowledge_assistance


if __name__ == "__main__":
    from config.settings import chat_config, prompts_bucket
    from config.tenant_settings import TenantSettings
    from db.mysql_utils import get_db
    from routers.schemas.users import UserSchema

    tenant_config = TenantSettings("byod-abbvie-test.zoomrx.ai")
    user = {
        'id': 'eM55ffpkz3SrIwdBH1NBpnReH4N2',
        'team_id': 1,
        'email_id': 'sunny.jain@zoomrx.com',
        'subdomain': 'abbvie_demo',
        'team_config': {
            "es_index": 'ferma_byod_abbvie_demo_embeddings',
            "enable_agent_zero": 0,
            "top_questions": [
                'How is Roche differentiating OCREVUS from the latest in-class competitor BRIUMVI?',
                'What abstracts were presented on tolebrutinib at ECTRIMS 2023?',
                'What abstracts is Novartis presenting at ECTRIMS 2023?'
            ]
        }
    }

    user['tenant_db'] = get_db(tenant_config.get_mysql_db_info())
    es_module = ESParentModule(UserSchema(**user))

    bool_query_prompt = prompts_bucket.get_blob(
        chat_config.BOOL_QUERY_PROMPT_FILE
    ).download_as_bytes().decode('utf-8')

    FEW_SHOT_EXAMPLES_BOOL_QUERY_PROMPT = prompts_bucket.get_blob(
        f"{user['subdomain']}/team_{user['team_id']}/{chat_config.ES_BOOL_QUERY_PROMPT_FEW_SHOT_EXAMPLES}"
    ).download_as_bytes().decode('utf-8')

    prompt = bool_query_prompt.format(
        search_query="What opportunities exist to improve Skyrizi sales rep performance?",
        few_shot_examples=FEW_SHOT_EXAMPLES_BOOL_QUERY_PROMPT
    )

    es_module.get_bool_query(prompt)
