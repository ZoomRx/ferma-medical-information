from uuid import uuid4
from fastapi import Request
import structlog

from helpers.authentication import decode_token
from helpers.logger import Logger


async def logger_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    ctx = {
        "transaction_id": str(uuid4()),
        "request_path": request.url.path,
        "query_params": dict(request.query_params)
    }
    try:
        if request.body:
            try:
                ctx["request_body"] = await request.body()
            except Exception as e:
                structlog.contextvars.bind_contextvars(**ctx)
                Logger.log('error', f"Failed to parse request body", {"error": str(e)})
        auth_header = request.headers.get("Authorization", "").split(" ")
        if len(auth_header) == 2:
            user = decode_token(auth_header[1])
            if user:
                ctx['user'] = user
    finally:
        structlog.contextvars.bind_contextvars(**ctx)
        response = await call_next(request)
        return response

