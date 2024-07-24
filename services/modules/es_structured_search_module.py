from copy import deepcopy
import numpy as np
import pandas as pd
import re
from string import Template
from typing import Union
import warnings

if __name__ == "__main__":
    import sys
    sys.path.append(".")

from helpers.gcs_utils import text_from_gcs
from config.es_settings import es_congress_planner_search_constants, es_constants
from config.settings import chat_config, prompts_bucket
from middlewares.custom_logger import log
from services.modules.es_parent_module import ESParentModule


warnings.filterwarnings("ignore")


class ESStructuredSearchModule(ESParentModule):
    def __init__(self, meta_data_start_index, user, return_as_df=False):
        super().__init__(user)
        self.meta_data_start_index = meta_data_start_index
        self.team_config = user.team_config
        self.user = user
        self.return_as_df = return_as_df


    def generate_query(self) -> dict:
        """
            Generates and returns the ElasticSearch query for the given question intent
        """

        self.indices_list = []
        for index_boost_dict in self.indices_boost_list:
            for index_name in index_boost_dict:
                self.indices_list.append(index_name)

        final_query = deepcopy(es_congress_planner_search_constants.BASE_QUERY_TEMPLATE)
        filters = self.question_intent.get("filters", {})

        date_filter_dict = {"range": {"date": {}}}
        for key, value in filters.items():
            # HACK: to remove 'room' keyword from location filter
            if key == 'location':
                value = value.replace('room', '')
            if value:
                should_queries = []
                must_queries = []
                should_query = deepcopy(es_congress_planner_search_constants.INNER_QUERY_TEMPLATE)
                must_query = deepcopy(es_congress_planner_search_constants.INNER_QUERY_TEMPLATE)

                filter_base_list = []
                must_query_fields = []
                should_query_fields = []
                for index in self.indices_list:
                    query_field_mappings = es_constants.MODULE_CONSTANTS[index]["query_field_mappings"]
                    if key not in ["other", "start_date", "end_date"]:
                        must_query_fields.extend(query_field_mappings.get(key, [key]))
                        must_query['query_string']['query'] = value
                    elif key == "start_date":
                        value = re.sub(r'[()]', '', value)
                        date_filter_dict['range']["date"]['gte'] = value
                    elif key == "end_date":
                        value = re.sub(r'[()]', '', value)
                        date_filter_dict['range']["date"]['lte'] = value

                    else:
                        should_query_fields.extend(query_field_mappings.get(key, [key]))
                        should_query['query_string']['query'] = value
                if date_filter_dict['range']["date"] != {}:
                    filter_base_list.append(date_filter_dict)

                analyzers_list = es_congress_planner_search_constants.FIELDS_ANALYZERS_MAPPING.get(key)

                if key in es_constants.MODULE_CONSTANTS[index].get(
                    "phrase_search_query_fields", []
                ):
                    must_query['query_string']['type'] = "phrase"
                if key not in ["other", "start_date", "end_date"]:
                    must_query['query_string']['fields'] = must_query_fields
                    must_queries.append(must_query)

                    if analyzers_list:
                        for analyzer in analyzers_list:
                            query_with_analyzer = deepcopy(must_query)
                            query_with_analyzer['query_string']['analyzer'] = analyzer
                            must_queries.append(query_with_analyzer)

                elif key not in ["start_date", "end_date"]:
                    should_query['query_string']['fields'] = should_query_fields
                    should_queries.append(should_query)

                    if analyzers_list:
                        for analyzer in analyzers_list:
                            query_with_analyzer_should = deepcopy(should_query)
                            query_with_analyzer_should['query_string']['analyzer'] = analyzer
                            should_queries.append(query_with_analyzer_should)

                if must_queries == []:
                    must_queries = should_queries
                    should_queries = []

                final_query['query']['bool']['must'].append({
                    "bool": {
                        "should": must_queries
                    }
                })
                final_query['query']['bool']['should'].append({
                    "bool": {
                        "should": should_queries
                    }
                })
                if len(filter_base_list) > 0:
                    final_query['query']['bool']['filter'] = filter_base_list

        data_source_filter = {
            "term": {
                "data_source": self.data_source[0]
            }
        }

        if "priority" in filters:
            final_query['sort'] = [
                {
                    "priority": {
                        "order": "asc"
                    }
                }
            ]
        final_query['query']['bool']['filter'].append(data_source_filter)
        self.traceback_log.update({
            "search": {
                "query": final_query,
                "question_intent": self.question_intent
            }
        })
        return final_query

    def get_es_results(self, es_query: dict, result_fetch_size: int = 10000) -> str:
        """
        Retrieves Conference documents from ElasticSearch and calls the formatting function
        """

        es_query["size"] = result_fetch_size

        es_data = self.search_in_es(
            query=es_query,
            indices_names=self.indices_list
        )

        return es_data

    def fetch_sources_list(self):
        sources_list = []
        output_fields = self.question_intent.get("output_fields", [])

        # if called from export function, the download fields will be added to the sources list
        if self.return_as_df:
            sources_list.extend(es_constants.MODULE_CONSTANTS[self.es_index]["download_fields"])

        else:
            for index in self.indices_list:
                if len(output_fields) > 0:
                    sources_list.extend(es_constants.MODULE_CONSTANTS[index]["default_fields"])
                    sources_list.extend(output_fields)
                else:
                    sources_list.extend(es_constants.MODULE_CONSTANTS[index]["output_fields"])

        return sources_list

    def format_results(self, es_data: dict) -> Union[str, pd.DataFrame]:
        """
            Structures and returns the Elasticsearch results in the markdown format
            with the required fields
        """
        es_data = [
            {**data['_source']}
            for data in es_data['hits']['hits']
        ]
        priority_mapping = {1: 'High', 2: 'Medium'}
        result = ""
        result_df = pd.json_normalize(es_data)
        is_high_priority = int(self.question_intent.get("filters", {}).get("high_priority", 0))
        
        sources_list = self.fetch_sources_list()
        output_fields = self.question_intent.get("output_fields", [])
        sources_list = [field for field in sources_list if field in result_df.columns]
        output_fields = [field for field in output_fields if field in result_df.columns]

        result_df = result_df.replace('', np.nan)
        if len(result_df) > 0:

            # Adding the reference to the agenda document for general list questions
            # When question specifically asks for agenda, the agenda will be displayed
            if is_high_priority and len(output_fields) == 0 and not(self.return_as_df):
                result_df["agenda"] = result_df["url"].apply(lambda x: f"See [Here]({x})")
                sources_list.extend(["agenda"])

            result_df = result_df[sources_list]
            es_field_mappings = es_constants.MODULE_CONSTANTS[self.es_index]["ES_FIELD_MAPPINGS"]
            if "date" in result_df.columns:
                result_df['date'] = pd.to_datetime(result_df['date'])
                result_df['date'] = result_df['date'].dt.strftime('%Y-%m-%d %H:%M')
                result_df["date"] = result_df["date"] + " CDT"
            if "priority" in result_df.columns:
                result_df['priority'] = result_df['priority'].map(priority_mapping)
            if "authors" in result_df.columns:
                result_df['authors'] = result_df['authors'].apply(lambda x: str(x).replace(";", ", "))
            result_df['abstract_title'] = "[" + result_df['abstract_title'] + "](" + result_df['abstract_url'] + ")"
            result_df.drop(["abstract_url"], axis=1, inplace=True)
            result_df.rename(columns=es_field_mappings, inplace=True)
            result_df = result_df.fillna('-')
            result_df = result_df.astype(str).applymap(lambda x: x.replace("\n\n", "\n"))

            # returning the dataframe for download option
            if self.return_as_df:
                return result_df, len(result_df)

            if len(result_df) > 10:
                result = (
                    f"`Download as CSV`"
                    "{.export-as-csv data-question-id={} data-subquestion-id={}}\n\n"
                    f"{result_df.iloc[:10].to_markdown(index=False)}\n\n"
                )
            else:
                result = f"\n{result_df.to_markdown(index=False)}\n\n"
            result = f"\n::: table-view \n{result}:::"
        
        else:
            result = f"\n"
        return result, len(result_df)

    def get_module_results(self, args: tuple) -> str:
        """
            - For the user question, gets the bool query output and generates the ES search query
            - Returns the relevant documents from Elasticsearch index for the given question
        """
        if self.return_as_df:
            self.question_intent, es_query, self.es_index = args
            self.indices_list = [self.user.team_config.es_index]
            es_data = self.get_es_results(es_query)
            result, num_of_records = self.format_results(es_data)
            return result

        question, self.question_type, indices, data_source, card_id = args
        self.indices_boost_list = indices
        self.data_source = data_source

        prompt_file = chat_config.prompt_file(card_id, "structured_es_bool_query")

        bool_query_prompt = text_from_gcs(self.user.subdomain, prompt_file)
        if not bool_query_prompt:
            raise Exception("structured ES bool query prompt missing for the card:", card_id)
        custom_needles_file = None
        custom_needles_file = text_from_gcs(self.user.subdomain, 'custom_needles.csv')
        annotation_result = self.get_annotation_result(question, custom_needles_file)

        # Formatting the Annotation's Result
        kg_assistance = self.format_annotation_result(annotation_result)

        bool_query_prompt = Template(bool_query_prompt)
        bool_query_prompt = bool_query_prompt.substitute(
            question=question,
            kg_assistance=kg_assistance
        )

        # event: conference bool query
        log(data={
            'event_details': {
                'module': 'es-conference',
                'labels': {
                    'prompt_file': prompt_file
                }
            }
        })

        self.question_intent = self.get_bool_query(
            prompt=bool_query_prompt,
            output_parser=''
        )
        if isinstance(self.question_intent, str):
            self.question_intent = {}

        es_query = self.generate_query()

        # event: conference execute query
        log(data={
            'event_details': {
                'module': 'es-conference',
                'action': 'execute-es-query'
            }
        })

        self.es_index = self.indices_list[0]
        es_data = self.get_es_results(es_query)
        result, num_of_records = self.format_results(es_data)

        return {
            "raw_result": self.format_es_results_as_str(es_data),
            "result": result,
            "num_of_records": num_of_records
        }

