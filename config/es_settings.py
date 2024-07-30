import json

from google.cloud import storage
from pydantic import Field
from typing import List, Dict
from config.settings import app_config, FitBaseSettings, JSONSettings


class ESSettings(JSONSettings):
    MODULE_DEFAULT_VALUES: dict = Field(alias="es_module_default_values")
    MODULE_CONSTANTS: dict = Field(alias="es_module_constants")


class ESStructuredSearchConstants(FitBaseSettings):
    KG_ANALYZERS: List = ['intra_label_hierarchies', 'inter_label_hierarchies', 'synonyms']

    BASE_QUERY_TEMPLATE: Dict = {
        "query": {
            "bool": {
                "must": [],
                "should": [],
                "filter": []
            }
        }
    }

    INNER_QUERY_TEMPLATE: Dict = {
        "query_string": {
            "query": "",
            "fields": [],
            "default_operator": "AND",
            "tie_breaker": 1
        }
    }

class CongressPlannerSearchConstants(ESStructuredSearchConstants):

    @property
    def FIELDS_ANALYZERS_MAPPING(self):
        return {
            "abstract_title": ["synonyms"],
            "session_title": ["synonyms"],
            "session_type": ["synonyms"],
            "indication": ["synonyms", "intra_label_hierarchies"],
            "patient_sub_group": ["synonyms", "intra_label_hierarchies"],
            "therapy_area": self.KG_ANALYZERS,
            "firm": ["synonyms", "intra_label_hierarchies"],
            "drug": self.KG_ANALYZERS,
            "drug_class": self.KG_ANALYZERS
        }


bucket_client = storage.Client()
synonyms_bucket = bucket_client.get_bucket(f"fc-{app_config.ENV_NAME}-synonyms")

es_modules_mappings_filename: str = "es_modules_mappings.json"
es_constants = ESSettings.from_gcs_file(
    bucket_name=byod_secrets_bucket,
    file_name=es_modules_mappings_filename
)
es_congress_planner_search_constants = CongressPlannerSearchConstants()
