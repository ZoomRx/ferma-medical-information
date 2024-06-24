from io import BytesIO
from google.cloud import storage
from google.oauth2 import service_account
from config import settings
from helpers.logger import Logger
import tempfile


GCP_CREDENTIALS = service_account.Credentials.from_service_account_file(
    filename=settings.gcs.gcp_service_account_filepath)
storage_client = storage.Client.from_service_account_json(settings.gcs.gcp_service_account_filepath)


def upload_file_to_gcs(source_file: BytesIO, destination_blob_name: str, bucket_name: str):
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        source_file.seek(0)
        blob.upload_from_file(source_file, content_type='csv')

        url = f"https://storage.cloud.google.com/{bucket_name}/{destination_blob_name}"

        return url
    except Exception as e:
        Logger.log(level='error', msg="Error while uploading file to GCS", data={'error': str(e), 'destination_blob_name': destination_blob_name})
        raise


def get_file_from_gcs(file_link: str, bucket_name: str):
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_link)

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_filename = temp_file.name
            blob.download_to_filename(temp_filename)

        return temp_filename
    except Exception as e:
        Logger.log(level='error', msg="Error while getting pre_signed url from GCS",
                   data={'error': str(e), 'file_link': file_link})
        raise
