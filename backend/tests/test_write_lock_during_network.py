"""Long network-bound steps must not hold SQLite's single write lock.

TMDB matching and AI normalization loop over every item with a network call per
item (several seconds each), but committed only at the very end. Their first
flush took the write lock and kept it for minutes, so any concurrent step failed
with "database is locked" after the 5 s busy timeout.
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db.base import Base, import_models
from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_item import MediaItem
from backend.app.models.scan_session import ScanSession
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTmdbClient


def _write_lock_is_free(db_path: Path) -> bool:
    connection = sqlite3.connect(db_path, timeout=0.2, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


@pytest.fixture
async def file_db(tmp_path):
    import_models()
    db_path = tmp_path / "lock.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        scan_session = ScanSession(source_path=str(tmp_path), target_path=str(tmp_path))
        session.add(scan_session)
        await session.flush()
        for title in ("The Matrix", "Alien", "Heat"):
            session.add(
                MediaItem(
                    scan_session_id=scan_session.id,
                    media_type=MediaType.MOVIE,
                    status=MediaItemStatus.DISCOVERED,
                    original_title=f"{title}.mkv",
                    parsed_title=title,
                    year=1999,
                )
            )
        await session.commit()
        scan_session_id = scan_session.id
    yield db_path, factory, scan_session_id
    await engine.dispose()


class _GatedTmdb(FakeTmdbClient):
    """Pauses inside the second search so the test can inspect the lock."""

    def __init__(self) -> None:
        super().__init__(movie_results=[], tv_results=[])
        self.calls = 0
        self.paused = asyncio.Event()
        self.resume = asyncio.Event()

    async def search_movie(self, query, year=None, language="ru-RU"):
        self.calls += 1
        if self.calls == 2:
            self.paused.set()
            await self.resume.wait()
        return [TmdbSearchResult(tmdb_id=self.calls, media_type="movie", title=query, year=year)]


@pytest.mark.asyncio
async def test_tmdb_matching_releases_the_write_lock_between_items(file_db) -> None:
    db_path, factory, scan_session_id = file_db
    client = _GatedTmdb()

    async with factory() as session:
        task = asyncio.create_task(TMDBService(session, client=client).match_scan_session(scan_session_id))
        await asyncio.wait_for(client.paused.wait(), timeout=10)

        free = await asyncio.to_thread(_write_lock_is_free, db_path)

        client.resume.set()
        await task

    assert free, "the write lock was held across a TMDB request"


class _GatedNormalizer:
    model = "test-model"

    def __init__(self) -> None:
        self.calls = 0
        self.paused = asyncio.Event()
        self.resume = asyncio.Event()

    async def normalize(self, original_title, rule_title, year, context):
        self.calls += 1
        if self.calls == 2:
            self.paused.set()
            await self.resume.wait()
        return _Result(rule_title or original_title)


class _Result:
    def __init__(self, title: str) -> None:
        self.title = title
        self.warnings: list[str] = []


@pytest.mark.asyncio
async def test_ai_normalization_releases_the_write_lock_between_items(file_db, monkeypatch) -> None:
    db_path, factory, scan_session_id = file_db
    client = _GatedNormalizer()

    async with factory() as session:
        service = RecognitionService(session, local_client=client)
        monkeypatch.setattr(service, "_apply_suggestion", lambda item, title, **kwargs: None)
        task = asyncio.create_task(service.normalize_scan_session(scan_session_id))
        await asyncio.wait_for(client.paused.wait(), timeout=10)

        free = await asyncio.to_thread(_write_lock_is_free, db_path)

        client.resume.set()
        await task

    assert free, "the write lock was held across an AI request"
