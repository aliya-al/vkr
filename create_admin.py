import asyncio
import uuid
import getpass

from sqlalchemy import select

from app.models.user import AdminUser, UserRole
from app.utils.security import hash_password

async def main():
    login = input("Login: ").strip()
    if not login:
        raise SystemExit("Login пустой")

    password = getpass.getpass("Password: ").strip()
    if not password:
        raise SystemExit("Password пустой")

    role = UserRole.admin

    from app.utils.database import async_session_maker


    pwd_hash = hash_password(password)

    async with async_session_maker() as session:
        res = await session.execute(select(AdminUser).where(AdminUser.login == login))
        user = res.scalar_one_or_none()

        if user:
            user.password_hash = pwd_hash
            user.role = role
            user.is_active = True
            action = "updated"
        else:
            user = AdminUser(
                id=uuid.uuid4(),
                login=login,
                password_hash=pwd_hash,
                role=role,
                is_active=True,
            )
            session.add(user)
            action = "created"

        await session.commit()

    print(f"OK: {action} admin '{login}'")


if __name__ == "__main__":
    asyncio.run(main())
