from typing import Annotated

from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from requests import Session
from db.session import get_db
from helpers.authentication import authenticate_user
from helpers.logger import Logger

# Define the Pydantic model for the JSON payload
class LoginSchema(BaseModel):
    username: str
    password: str

# Create the router instance
router = APIRouter()

@router.post("/login")
def login(
        login_data: LoginSchema,
        db: Session = Depends(get_db)
):
    username = login_data.username
    password = login_data.password
    Logger.log(level="info", msg=f"{username} Logging in..", data={'user':username})
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

        return response
    else:
        Logger.log(level="error", msg="Incorrect username or password",data={'username':username})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
