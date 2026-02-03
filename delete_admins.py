import asyncio
import argparse

from sqlalchemy import select, update, delete, func

from app.models.user import AdminUser
from app.utils.database import async_session_maker


async def main():
    parser = argparse.ArgumentParser(description="Disable or delete admin users.")
    parser.add_argument(
        "--hard",
        action="store_true",
        help="Hard delete (DELETE FROM admin_users). Default: soft disable (is_active=false).",
    )
    parser.add_argument(
        "--keep-login",
        action="append",
        default=[],
        help="Login(s) to keep (can be repeated). Example: --keep-login admin --keep-login root",
    )
    args = parser.parse_args()

    keep = set([x.strip() for x in args.keep_login if x and x.strip()])

    async with async_session_maker() as session:
        # Сколько попадёт под действие
        count_q = select(func.count()).select_from(AdminUser)
        if keep:
            count_q = count_q.where(~AdminUser.login.in_(keep))
        total_to_affect = (await session.execute(count_q)).scalar_one()

        mode = "HARD DELETE" if args.hard else "SOFT DISABLE"
        print(f"Mode: {mode}")
        print(f"Will affect: {total_to_affect} admin_user(s)")
        if keep:
            print(f"Will keep logins: {', '.join(sorted(keep))}")

        confirm = input("Type YES to continue: ").strip()
        if confirm != "YES":
            print("Cancelled.")
            return

        if args.hard:
            stmt = delete(AdminUser)
            if keep:
                stmt = stmt.where(~AdminUser.login.in_(keep))
        else:
            stmt = update(AdminUser).values(is_active=False)
            if keep:
                stmt = stmt.where(~AdminUser.login.in_(keep))

        result = await session.execute(stmt)
        await session.commit()

        print(f"Done. rowcount={result.rowcount}, expected={total_to_affect}")


if __name__ == "__main__":
    asyncio.run(main())
