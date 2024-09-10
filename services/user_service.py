import traceback

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from helpers.logger import Logger
from models.users import Users
from services.base import BaseService
from fastapi import HTTPException


class UserService(BaseService[Users, None, None]):
    def get(self, db: Session, email: str):
        try:
            db_obj = db.query(Users).filter_by(email=email).first()

            if db_obj is None:
                Logger.log("error", f"User not found: {email}")
                raise HTTPException(status_code=404, detail="User not found")

            return db_obj
        except SQLAlchemyError as e:
            db.rollback()
            Logger.log("critical", f"SQL Error during User login", data={'error': str(e)})
            Logger.log("sql_error_details", data={
                'Error type': {type(e).__name__},
                'Error message': {str(e)},
                'Traceback': {traceback.format_exc()}})
            raise e


user_service = UserService(Users)
