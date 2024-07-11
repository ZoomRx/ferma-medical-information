from sqlalchemy import Column, Integer, ForeignKey, Index, String
from db.base_class import Base


class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(60), nullable=False)
    is_valid = Column(Integer, nullable=False)

