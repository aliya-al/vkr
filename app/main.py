import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.routers import routers
from fastapi.staticfiles import StaticFiles

load_dotenv()                                     

IS_PROD = 1

app = FastAPI(
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

app.include_router(routers)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError("SESSION_SECRET_KEY не установлен.")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="session",
    same_site="lax",                                                     
    https_only=False,                                                                  
)
