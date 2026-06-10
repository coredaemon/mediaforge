from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaType
from backend.app.models.media_item import MediaItem
from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTmdbClient


async def test_tmdb_service_uses_settings_key_when_env_key_is_empty(
    db_session: AsyncSession,
    tmp_path,
) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "settings-key"})
    await db_session.commit()

    scan_session = await ScanSessionService(db_session).create_scan_session(
        str(tmp_path / "in"), str(tmp_path / "out")
    )
    await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            parsed_title="Test Movie",
            needs_review=False,
        )
    )
    await db_session.commit()

    fake_client = FakeTmdbClient(movie_results=[
        TmdbSearchResult(tmdb_id=1, media_type="movie", title="Test Movie", year=2000, popularity=90)
    ])

    result = await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    assert result.matched_count == 1


async def test_tmdb_service_raises_when_no_key_anywhere(
    db_session: AsyncSession,
    tmp_path,
) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(
        str(tmp_path / "in"), str(tmp_path / "out")
    )
    await db_session.commit()

    from backend.app.services.tmdb_client import TmdbApiKeyMissingError
    import pytest

    with pytest.raises(TmdbApiKeyMissingError):
        await TMDBService(db_session).match_scan_session(scan_session.id)
