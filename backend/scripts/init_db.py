import asyncio

from backend.app.db.base import Base, import_models
from backend.app.db.session import engine


async def init_db() -> None:
    import_models()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
