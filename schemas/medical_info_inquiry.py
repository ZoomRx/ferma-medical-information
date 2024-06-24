from typing import List
from pydantic import BaseModel


class InquiryType(BaseModel):
    type: str
    categories: List[str]

    def __post_init__(self):
        # Custom initialization logic here
        print(f"InquiryType created with type={self.type} and categories={self.categories}")


class InquiryDetails(BaseModel):
    inquiry: str
    document_title: str
    summary_section: str
    additional_notes: str
    document_source: List[str]
    inquiry_type: List[InquiryType]

