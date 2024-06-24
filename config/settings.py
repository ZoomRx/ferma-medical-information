import json
from pydantic import Field
from typing import List, Dict, Any, Type, TypeVar, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

T = TypeVar('T', bound='JSONSettings')


class CommonSettings(BaseSettings):
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class JSONSettings(CommonSettings):
    model_config = SettingsConfigDict(extra='allow')

    @classmethod
    def from_file_path(cls: Type[T], *, file_path: str) -> T:
        with open(file_path, 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        return cls(**json_data)

    @classmethod
    def from_dict(cls: Type[T], *, json_data: Dict[str, Any]) -> T:
        return cls(**json_data)


class GCSSettings(JSONSettings):
    gcp_service_account_filepath: str = Field(..., alias='GCP_SERVICE_ACCOUNT_FILEPATH')
    gcs_bucket_name: str = Field(..., alias='GCS_BUCKET_NAME')
    gcs_project_id: Optional[str] = None
    source_files_location: str = "sources/{}/{}.{}"
    raw_output_json_location: str = "contents_raw_output/{}/{}.json"
    processed_output_json_location: str = "contents/{}/{}.json"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.load_gcs_project_id()

    def load_gcs_project_id(self):
        filepath = self.gcp_service_account_filepath
        if filepath:
            try:
                json_settings = JSONSettings.from_file_path(file_path=filepath)
                self.gcs_project_id = json_settings.project_id
            except Exception as e:
                raise ValueError(f"Failed to load project_id from {filepath}: {e}")


class PubSubSettings(JSONSettings):
    logger_topic: str = Field(..., alias='LOGGER_TOPIC')


class AzureSettings(JSONSettings):
    azure_document_intelligence_api_key: str = Field(..., alias='AZURE_DOCUMENT_INTELLIGENCE_API_KEY')
    azure_document_intelligence_endpoint: str = Field(..., alias='AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT')
    azure_document_intelligence_model: str = Field(..., alias='AZURE_DOCUMENT_INTELLIGENCE_MODEL')
    allowed_file_extensions: List[str] = Field(
        default_factory=lambda: ["jpg", "jpeg", "jpe", "jif", "jfi", "jfif", "pdf", "png", "tif", "tiff"])
    convertible_file_extensions: List[str] = Field(default_factory=lambda: ["pptx", "docx"])


class EnvSettings(JSONSettings):
    environment: str = Field(..., alias="ENVIRONMENT")
    temp_dir: str = "storage/data"
    jwt_token: str = Field(..., alias='JWT_SECRET_KEY')
    is_debug: str = Field(..., alias='IS_DEBUG')

class DBSettings(JSONSettings):
    username: str = Field(..., alias='DB_USERNAME')
    password: str = Field(..., alias='DB_PASSWORD')
    host: str = Field(..., alias='DB_HOST')
    name: str = Field(..., alias='DB_NAME')

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.username}:{self.password}@{self.host}/{self.name}"


class SentrySettings(JSONSettings):
    sentry_dsn: str = Field(..., alias='SENTRY_DSN')


env: EnvSettings = EnvSettings()
gcs: GCSSettings = GCSSettings()
pubsub: PubSubSettings = PubSubSettings()
azure: AzureSettings = AzureSettings()
# unstructured: UnstructuredSettings = UnstructuredSettings()
db: DBSettings = DBSettings()
sentry: SentrySettings = SentrySettings()
