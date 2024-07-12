# routes/upload_routes.py
import os
import time

from fastapi import APIRouter
from starlette.responses import JSONResponse

from helpers.logger import Logger
from schemas.medical_info_inquiry import InquiryDetails, Inquiry
from services.medical_information_report_builder import generate_report, generate_content
from services.pubmed_service import fetch_articles_based_on_inquiry

router = APIRouter()


from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import List
import aiofiles
from pathlib import Path
from datetime import datetime

app = FastAPI()

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    file_names = []
    for file in files:
        try:
            content_type = file.content_type

            # Generate a new filename with a timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            new_filename = f"{file.filename.split('.')[0]}_{timestamp}.pdf"

            file_path = Path("./storage/data/") / new_filename

            # Ensure the directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Read the file contents
            contents = await file.read()

            # Write the contents to a file in binary mode
            async with aiofiles.open(file_path, "wb") as buffer:
                await buffer.write(contents)

            saved_file_size = os.path.getsize(file_path)
            if saved_file_size!= len(contents):
                raise IOError("Mismatch in file size after saving")

            file_names.append(new_filename)
        except Exception as e:
            print(f"An error occurred: {e}")
            continue  # Optionally, handle the error more gracefully
        finally:
            await file.close()

    return {
        "message": "Files successfully uploaded",
        "fileNames": file_names
    }


@router.post("/create_srl")
async def create_srl(inquiry_details: InquiryDetails):
    Logger.log(f"Received request to create_srl for inquiry: {inquiry_details.inquiry}")
    # Placeholder for generating the SRL document
    # In a real implementation, this would involve processing the inquiry details and files
    document_content = generate_content(inquiry_details)

    return {"content": document_content}

@router.post("/find_cite")
async def find_cite(inquiry: Inquiry):
    Logger.log(msg = f"Received request to find citations for inquiry: {inquiry.inquiry}")
    try:
        start_time = time.time()
        # Simulate fetching articles based on inquiry
        articles = await fetch_articles_based_on_inquiry(inquiry)

        # Log successful retrieval of articles
        Logger.log(msg = f"Successfully retrieved {len(articles)} articles.")
        # Capture the end time
        end_time = time.time()
        # Calculate and log the response time
        response_time = end_time - start_time
        Logger.log(msg = f"Find cite Response time: {response_time:.2f} seconds")

        return articles
    except Exception as e:
        # Log any exceptions that occur during processing
        Logger.log(level="error",msg=f"An error occurred while processing the request: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/download_cite")
async def download_pdf_endpoint(links: list[str]):
    filenames = []
    for link in links:
        try:
            filename = "nihms-1732896_20240628132111.pdf"
            filenames.append(filename)
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
    return {
        "fileNames": filenames
    }