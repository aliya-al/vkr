import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

IS_PROD = os.getenv("IS_PROD", "0") == "1"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не установлен.")
if not SESSION_SECRET_KEY:
    raise RuntimeError("SESSION_SECRET_KEY не установлен.")
