import asyncio
from sqlalchemy import Enum
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from enum import Enum

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.base_class import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete(CRUD).

        **Parameters**

        * `model`: A SQLAlchemy model class
        * `schema`: A Pydantic model (schema) class
        """
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        try:
            obj_in_data = jsonable_encoder(obj_in)
            db_obj = self.model(**obj_in_data)  # type: ignore
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError:
            db.rollback()
            raise
    
    def update_attr(self, db_obj: ModelType, obj_in: UpdateSchemaType):
        obj_data = jsonable_encoder(db_obj)
        for field, value in obj_in.model_dump(exclude_unset=True).items():
            if isinstance(value, Enum):
                value = value.value
            setattr(db_obj, field, value)
        return db_obj  

    def update(
            self,
            db: Session,
            *,
            db_obj: ModelType,
            obj_in: UpdateSchemaType
    ) -> ModelType:
        try:
            obj_data = jsonable_encoder(db_obj)
            for field, value in obj_in.model_dump(exclude_unset=True).items():
                if isinstance(value, Enum):
                    value = value.value
                setattr(db_obj, field, value)

            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError:
            db.rollback()
            raise
    
    def delete(self, db: Session, db_obj: ModelType):
        if db_obj:
                db.delete(db_obj)
                db.commit()
                return db_obj
        return False
    
    def remove(self, db: Session, *, id: int) -> Any | None:
        try:
            db_obj = db.query(self.model).get(id)
            if db_obj:
                db.delete(db_obj)
                db.commit()
            return db_obj
        except SQLAlchemyError:
            db.rollback()
            raise
