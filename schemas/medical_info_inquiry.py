from typing import List
from pydantic import BaseModel


class InquiryType(BaseModel):
    type: str
    categories: List[str]

class InquiryDetails(BaseModel):
    inquiry: str
    document_title: str
    summary_section: str
    additional_notes: str
    document_source: List[str]
    inquiry_type: List[InquiryType]

class DocumentContent(BaseModel):
    content: str
