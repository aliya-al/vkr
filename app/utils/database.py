from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL, IS_PROD

engine = create_async_engine(
    DATABASE_URL,
    echo=not IS_PROD, # без логов БД  проде
)
class Base(DeclarativeBase): pass

async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_async_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session