from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "postgresql+asyncpg://postgres:passs@localhost:5432/database"

engine = create_async_engine(DATABASE_URL, echo=True)
class Base(DeclarativeBase): pass