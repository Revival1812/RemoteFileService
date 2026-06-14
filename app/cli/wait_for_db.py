import asyncio

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine


async def main() -> None:
    for _ in range(60):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                return
        except SQLAlchemyError:
            await asyncio.sleep(1)
    raise SystemExit("database is not ready")


if __name__ == "__main__":
    asyncio.run(main())

