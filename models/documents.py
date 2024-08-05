from sqlalchemy import Column, Integer, String, Text
from db.base_class import Base

class Documents(Base):
    __tablename__ = 'clusters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(255), unique=True)
    page_title = Column(String(500))
    page_no = Column(Integer)
    paragraph_order = Column(Integer)
    content = Column(Text)
    type = Column(String(30))
