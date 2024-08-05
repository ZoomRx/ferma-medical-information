import os

import pandas as pd
from pandas import DataFrame
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from models.documents import Documents
from services.base import BaseService
from fastapi import HTTPException


class DocumentService(BaseService[Documents, None, None]):
    def get(self, db: Session, document_id: str):
        try:
            QUERY = f"""
            SELECT
                c.document_id,
                d.file_name,
                c.page_title,
                c.page_no,
                c.paragraph_order,
                c.content
            FROM
                documents d
            JOIN clusters c on
                d.id = c.document_id
            WHERE
                d.id = '{document_id}'
            """
            clusters_df = pd.read_sql(
                QUERY, db.bind
            )

            return self.get_processed_output(clusters_df)

        except SQLAlchemyError:
            db.rollback()
            raise

    def get_processed_output(self, documents_df) -> DataFrame:

        page_level_df = documents_df.groupby(["document_id", "page_no"]).agg({
            'file_name': 'first',
            'page_title': 'first',
            'content': lambda x: '\n'.join(x)
        }).reset_index()

        return page_level_df


document_service = DocumentService(Documents)


