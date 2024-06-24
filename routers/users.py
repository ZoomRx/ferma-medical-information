from typing import Annotated

from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from requests import Session
from db.session import get_db
from helpers.authentication import authenticate_user

router = APIRouter()


@router.post("/login")
def login(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        db: Session = Depends(get_db)
):
    username = form_data.username
    password = form_data.password
    response = authenticate_user(db, username, password)

    if response:
        # Any custom error message raised from authenticate_user
        if (
                response
                and ("isErrorMessage" in response)
                and response["isErrorMessage"]
        ):
            return JSONResponse(
                status_code=response["status_code"],
                content=response["content"]
            )

        # return response as user_service.py details
        return response
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
