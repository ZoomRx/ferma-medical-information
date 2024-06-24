from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from db.session import get_db
from models.users import Users
from services.base import BaseService
from fastapi import HTTPException


class UserService(BaseService[Users, None, None]):
    def get(self, db: Session, email: str):
        try:
            print(db)
            db_obj = db.query(Users).filter_by(email=email).first()

            if db_obj is None:
                raise HTTPException(status_code=404, detail="User not found")

            return db_obj
        except SQLAlchemyError:
            db.rollback()
            raise


user_service = UserService(Users)
