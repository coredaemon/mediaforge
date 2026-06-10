from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import Base


async def test_database_tables_are_created(db_session: AsyncSession) -> None:
    connection = await db_session.connection()
    table_names = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())

    assert set(Base.metadata.tables) <= set(table_names)
