import json
import shutil
from typing import List, Optional, Tuple
from azure.core.polling._poller import PollingReturnType_co
from pandas import DataFrame
from unstructured.documents.elements import Element

from config import settings
from typing import Any, Dict
import pandas as pd
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential


class AzureDocIntelligence():
    def __init__(self):
        self.document_intelligence_client = DocumentIntelligenceClient(
            endpoint=settings.azure.azure_document_intelligence_endpoint,
            credential=AzureKeyCredential(settings.azure.azure_document_intelligence_api_key)
        )

    def get_raw_output(self, *, local_inp_file_path: str) -> Tuple[PollingReturnType_co, Dict]:
        with open(local_inp_file_path, "rb") as f:
            poller = self.document_intelligence_client.begin_analyze_document(
                model_id=settings.azure.azure_document_intelligence_model,
                analyze_request=f,
                content_type="application/octet-stream"
            )
        doc_intell_response_obj = poller.result()
        doc_intell_response_dict = doc_intell_response_obj.as_dict()
        return doc_intell_response_obj, doc_intell_response_dict

    def get_processed_output(self, *, raw_output_obj: PollingReturnType_co) -> DataFrame:
        chunck_positions = {}
        for paragraph in raw_output_obj.paragraphs:
            if paragraph.spans:
                chunck_positions[paragraph.spans[0].offset] = {
                    "end_position": paragraph.spans[0].offset + paragraph.spans[0].length,
                    "role": paragraph.role,
                    "page_no": paragraph.bounding_regions[0].page_number
                }
        if raw_output_obj.tables:
            for index, table in enumerate(raw_output_obj.tables):
                if table.spans:
                    span = table.spans[0]
                    chunck_positions[span.offset] = {
                        "end_position": span.offset + span.length,
                        "role": 'table',
                        "page_no": table.bounding_regions[0].page_number,
                        "table_index": index
                    }
        if raw_output_obj.figures:
            for index, figure in enumerate(raw_output_obj.figures):
                if figure.spans:
                    span = figure.spans[0]
                    if span.offset != span.offset + span.length:
                        chunck_positions[span.offset] = {
                            "end_position": span.offset + span.length,
                            "role": 'figure',
                            "page_no": figure.bounding_regions[0].page_number,
                            "figure_index": index
                        }

        next_chunck_position = -1
        current_page = 1
        chunck_order = 1
        page_title = None
        page_df = pd.DataFrame(columns=["page_no", "page_title"])
        paragraph_df = pd.DataFrame(columns=["page_no", "paragraph_order", "type", "content"])

        for start_position, metadata in chunck_positions.items():
            if metadata["page_no"] != current_page:
                page_row = {
                    "page_no": current_page,
                    "page_title": page_title
                }
                page_df = pd.concat([page_df, pd.DataFrame([page_row])], ignore_index=True)

                current_page += 1
                page_title = None
                chunck_order = 1

            if start_position > next_chunck_position:
                if metadata["role"] == "table":
                    content = self.json_to_markdown(table=raw_output_obj.tables[metadata["table_index"]])
                    next_chunck_position = metadata["end_position"]
                elif metadata["role"] == "figure":
                    content = raw_output_obj.content[start_position:metadata["end_position"]]
                    next_chunck_position = metadata["end_position"]
                else:
                    content = raw_output_obj.content[start_position:metadata["end_position"]]
                    if metadata["role"] == "title" and page_title is None:
                        page_title = content

                paragraph_row = {
                    "page_no": current_page,
                    "paragraph_order": chunck_order,
                    "type": metadata["role"] if metadata["role"] else "paragraph",
                    "content": content
                }
                paragraph_df = pd.concat([paragraph_df, pd.DataFrame([paragraph_row])], ignore_index=True)
                chunck_order += 1

        page_row = {
            "page_no": current_page,
            "page_title": page_title
        }
        page_df = pd.concat([page_df, pd.DataFrame([page_row])], ignore_index=True)
        cluster_df = pd.merge(paragraph_df, page_df, on='page_no')
        return cluster_df

    @staticmethod
    def json_to_markdown(*, table: Dict[str, Any]) -> str:
        markdown_text = ""
        headers = [""] * table["columnCount"]
        headers_present = 0

        for cell in table['cells']:
            content = cell['content'].replace('\n', '')
            content = content.replace(':selected:', '')
            content = content.replace(':unselected:', '')
            if cell.get('kind', "") == 'columnHeader' and cell['rowIndex'] == 0:
                headers[cell['columnIndex']] = content
                headers_present = 1

        table_matrix = [[""] * table["columnCount"] for _ in range(table["rowCount"])]

        for cell in table['cells']:
            content = cell['content'].replace('\n', '')
            content = content.replace(':selected:', '')
            content = content.replace(':unselected:', '')
            if not (cell.get('kind', "") == 'columnHeader' and cell['rowIndex'] == 0):
                table_matrix[cell['rowIndex'] - headers_present][cell['columnIndex']] = content

        for i in range(table["rowCount"] - headers_present):
            markdown_text += "|"
            for j in range(table["columnCount"]):
                markdown_text += table_matrix[i][j] + "|"
            markdown_text += "\n"

        pattern = "|" * (table["columnCount"] + 1) + "\n"
        markdown_text = markdown_text.replace(pattern, "")
        markdown_text = "|" + "|".join(['-'] * table['columnCount']) + "|\n" + markdown_text
        markdown_text = "|" + "|".join(headers) + "|\n" + markdown_text
        markdown_text = f"{table['caption']['content']}\n{markdown_text}" if table.get('caption') else markdown_text
        return markdown_text
