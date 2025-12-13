import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.routers import routers

load_dotenv() # загружает переменные из локального

APP_ENV = os.getenv("APP_ENV", "dev").lower()
IS_PROD = APP_ENV == "prod"

app = FastAPI(
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

app.include_router(routers)

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError("SESSION_SECRET_KEY не установлен.")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="session",
    same_site="lax",            # защита от части CSRF на уровне браузера
    https_only=False,           # в проде True (если сайт на https). https_only=IS_PROD
)
