from uuid import uuid4
from fastapi import Request
import structlog

from helpers.authentication import decode_token

async def logger_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    ctx = { "transaction_id": str(uuid4()) }
    print(ctx)
    try:
        auth_header = request.headers.get("Authorization", "").split(" ")
        if len(auth_header) == 2:
            user = decode_token(auth_header[1])
            print(user)
            if user:
                ctx['user'] = user
    finally:
        structlog.contextvars.bind_contextvars(**ctx)
        response = await call_next(request)
        return response

