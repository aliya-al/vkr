import asyncio
from sqlalchemy import select

from app.models.category import Category
from app.utils.database import async_session_maker


async def main():
    async with async_session_maker() as session:
        res = await session.execute(
            select(Category.id, Category.name)
            .where(Category.image_path.is_(None))
            .order_by(Category.name)
        )
        rows = res.all()

    print("Categories with NULL image_path:", len(rows))
    for cid, name in rows:
        print(cid, "-", name)


if __name__ == "__main__":
    asyncio.run(main())
