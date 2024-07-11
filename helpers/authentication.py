from datetime import datetime, timedelta
from pytz import UTC
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from config import settings
from db.session import get_db
from helpers.logger import Logger
from sentry_sdk import capture_exception
from services.user_service import user_service

JWT_ENCODE_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(UTC) + expires_delta
        to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.env.jwt_token,
        algorithm=JWT_ENCODE_ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str):
    if not settings.env.IS_DEBUG:
        return "abcd@zrx.com"
    payload = jwt.decode(
        token, settings.env.jwt_token,
        algorithms=[JWT_ENCODE_ALGORITHM]
    )
    userMail: str = payload.get("sub")
    if userMail is None:
        return False
    else:
        return userMail


def verify_token(token: str = Depends(oauth2_scheme)):
    if not settings.IS_DEBUG:
        return "abcd@zrx.com"

    try:
        payload = jwt.decode(
            token, settings.env.jwt_token,
            algorithms=[JWT_ENCODE_ALGORITHM]
        )
        userMail: str = payload.get("sub")
        if userMail is None:
            return False
        else:
            return userMail
    except JWTError as e:
        capture_exception(e)
        Logger.log('error', f"Threw error while verifying token", {"error": e, "token": token})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired"
        )


def authenticate_user(db, username, password):
    # Authentication steps:
    # 1. create a JWT token
    # 2. return token and required user_service.py details
    if not settings.env.is_debug:
        return {
            "access_token": "abcd",
            "user_details": {
                "mail": f"{username}@zrx.com",
                "username": username,
            },
            "token_type": "bearer"
        }

    user = validate_user(db, username, password)
    if (
            user
            and ("isErrorMessage" in user)
            and user["isErrorMessage"]
    ):
        return user
    if not user:
        return False
    access_token_expires = timedelta(
        minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": user['mail'], "username": user['username']},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "user_details": user,
        "token_type": "bearer"
    }


def validate_user(db, username, password):
    try:
        is_authenticated = False
        print(username)
        # email = f"{username}@zoomrx.com"
        email = username
        try:
            user = user_service.get(db, email=email)
            if user.is_valid== 1 and user.password_hash == password:
                is_authenticated = True
        except Exception as e:
            print(e)
            raise
        return {
            "mail": email,
            "username": username
        }
    except Exception as e:
        capture_exception(e)
        print(e)
        Logger.log('error', f"Threw error while authenticating user", {"username": username, "error": e})
        return {
            "isErrorMessage": True,
            "status_code": 400,
            "content": {
                "message": "Something went wrong. Please try again later."
            }
        }
