from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from config import settings

POOL_RECYCLE = 21600

engine = create_engine(
    settings.db.database_url,
    pool_recycle=POOL_RECYCLE,
    poolclass=NullPool
)

doc_db_engine = create_engine(
    settings.db.doc_database_url,
    pool_recycle=POOL_RECYCLE,
    poolclass=NullPool
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionDocLocal = sessionmaker(autocommit=False, autoflush=False, bind=doc_db_engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_doc_db() -> Generator:
    db = SessionDocLocal()
    try:
        yield db
    finally:
        db.close()
