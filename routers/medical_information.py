from datetime import datetime
from typing import List
import requests
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile, Depends
from fastapi.responses import JSONResponse
from pandas import DataFrame
from requests import Session

from db.session import get_doc_db
from helpers import es_utils
from helpers.logger import Logger
from pathlib import Path

from middlewares.logger import logger_middleware
from schemas.medical_info_inquiry import Inquiry, InquiryDetails, InquiryType
from services import document_service
from services.azure_doc_intelligence import AzureDocIntelligence
from services.document_service import document_service
from services.medical_information_report_builder import generate_content, generate_report
from services.pubmed_service import fetch_articles_based_on_inquiry
import aiofiles
import asyncio
import os
import traceback
import time

router = APIRouter()
app = FastAPI()
app.middleware("http")(logger_middleware)

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...),
                       db: Session = Depends(get_doc_db)):
    file_uploaded = [file.filename for file in files]
    Logger.log(msg=f"Upload_files", data={'files':file_uploaded})
    file_names = []
    # tasks = [process_file(file, db) for file in files]
    tasks = [process_file_AzureAI(file) for file in files]
    if tasks is None:
        raise HTTPException(status_code=500, detail="Internal Server Error")
    results = await asyncio.gather(*tasks)
    valid_results = [result for result in results if result is not None]
    file_names = valid_results

    return {
        "message": "Files successfully uploaded",
        "fileNames": file_names
    }


# Document conversion using Azure AI
async def process_file(file: UploadFile, db):
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        new_filename = f"{file.filename.split('.')[0]}_{timestamp}.pdf"
        file_path = Path("./storage/data/") / new_filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, mode='wb') as out_file:
            contents = await file.read()  # Read the file contents
            await out_file.write(contents)  # Write the contents to the new file

        url = "https://ferma-ai-doc-intelligence.zoomrx.ai/extract"
        headers = {'access-token': 'J1YTmJ5YbrLWfSjUQSTC'}
        data = {"tags": "{\"project_name\": \"ferma-mi\"}", "is_text_only": False}
        files = {"file": (new_filename, contents)}

        response = requests.post(url, headers=headers, data=data, files=files)

        if response.status_code == 200:
            print(response.json()['document_id'])
        elif response.status_code == 500:
            print(response.json()['detail'])  # error detail
        else:
            print(f"{response.status_code}\n\n{response.text}")

        # Check the response
        if response.status_code == 200:
            print("Success:", response.json())
        else:
            print("Error:", response.status_code, response.text)
            raise HTTPException(status_code=response.status_code, detail=response.text)

        try:
            response_json = response.json()
            document_id = response_json['document_id']
            documents: DataFrame = document_service.get(db, document_id=document_id)
        except KeyError as e:
            print(f"KeyError: {e}")
            raise HTTPException(status_code=400, detail="Invalid response format")

        es_record_count = es_utils.write_es_data(documents)
        saved_file_size = os.path.getsize(file_path)
        if saved_file_size != len(contents):
            raise IOError("Mismatch in file size after saving")

        return new_filename
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/create_srl")
async def create_srl(inquiry_details: InquiryDetails):
    try:
        Logger.log(msg=f"CreateSRL API Request", data=inquiry_details.to_json())
        document_content = generate_content(inquiry_details)
        return {"content": document_content}
    except Exception as e:
        Logger.log(level="error", msg=f"Create_SRL Error", data={'error': str(e)})
        Logger.log("Create srl error details", data={
            'Error type': {type(e).__name__},
            'Error message': {str(e)},
            'Traceback': {traceback.format_exc()}})
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/find_cite")
async def find_cite(inquiry: Inquiry):
    Logger.log(msg=f"Find Site Request", data=inquiry.__dict__)
    try:
        start_time = time.time()
        # Simulate fetching articles based on inquiry
        articles = await fetch_articles_based_on_inquiry(inquiry)
        Logger.log(msg=f"Successfully retrieved {len(articles)} articles.")
        end_time = time.time()
        response_time = end_time - start_time
        Logger.log(msg=f"Find cite Response time: {response_time:.2f} seconds")

        return articles
    except Exception as e:
        Logger.log(level="error", msg=f"Find_site: Error", data={'error': str(e)})
        Logger.log("Find site error details", data={
            'Error type': {type(e).__name__},
            'Error message': {str(e)},
            'Traceback': {traceback.format_exc()}})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/download_cite")
async def download_pdf_endpoint(links: list[str]):
    filenames = []
    for link in links:
        try:
            filename = "nihms-1732896_20240628132111.pdf"
            filenames.append(filename)
        except Exception as e:
            Logger.log(level="error", msg=f"Download_pdf: An error occurred while processing.", data={'error': str(e)})
            return JSONResponse(status_code=400, content={"error": str(e)})
    return {
        "fileNames": filenames
    }


async def process_file_AzureAI(file: UploadFile):
    try:
        content_type = file.content_type
        Logger.log(level="info",  msg=f"Process file: file name - {file.filename}, content_type: {content_type}")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        new_filename = f"{file.filename.split('.')[0]}_{timestamp}"
        filename = f"{new_filename}.pdf"
        file_path = Path("./storage/data/") / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        contents = await file.read()

        async with aiofiles.open(file_path, "wb") as buffer:
            await buffer.write(contents)
        azure = AzureDocIntelligence()
        doc_intell_response_obj, doc_intell_response_dict = azure.get_raw_output(
            local_inp_file_path=file_path)
        processed_content = azure.get_processed_output(raw_output_obj=doc_intell_response_obj, file_name=new_filename)
        es_record_count = es_utils.write_es_data(processed_content)
        saved_file_size = os.path.getsize(file_path)
        if saved_file_size != len(contents):
            raise IOError("Mismatch in file size after saving")
        return filename
    except Exception as e:
        Logger.log(level="error", msg=f"Azure file_Processing: An error occurred while processing.", data={'error': str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")

def serialize_complex_object(obj):
    if isinstance(obj, InquiryType):
        return obj.__dict__
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    else:
        return str(obj)