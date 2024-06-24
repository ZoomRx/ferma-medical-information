from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
import sentry_sdk

from routers import users, medical_information

from middlewares.logger import logger_middleware
from helpers.logger import Logger
from config import settings

Logger.initialise()
if settings.env.environment == 'production':
    sentry_sdk.init(
        dsn=settings.sentry.sentry_dsn,
        integrations=[
            StarletteIntegration(
                transaction_style="endpoint"
            ),
            FastApiIntegration(
                transaction_style="endpoint"
            ),
        ],
    )

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(logger_middleware)

app.include_router(
    router=users.router, prefix='/api/users',
    tags=["Users"]
)

app.include_router(
    router=medical_information.router, prefix='/api/medical_information',
    tags=["medical_information"]
)

@app.get("/")
async def root():
    return {"message": "Ferma-Medical Information - Automated SRL"}

