"""A TMDB outage must reach the UI as an actionable message, not a 500."""

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.main import app
from backend.app.services.tmdb_client import (
    TmdbAuthError,
    TmdbRateLimitError,
    TmdbUnavailableError,
)
from backend.tests.fakes import FakeTmdbClient


class _FailingTmdbClient(FakeTmdbClient):
    def __init__(self, error: Exception) -> None:
        super().__init__(movie_results=[], tv_results=[])
        self._error = error

    async def search_movie(self, query, year=None, language="ru-RU"):
        raise self._error

    async def search_tv(self, query, year=None, language="ru-RU"):
        raise self._error


def _session_with_one_movie(client: TestClient, tmp_path) -> int:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.mkv").write_bytes(b"movie")

    session_id = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    ).json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")
    client.post(f"/scan-sessions/{session_id}/parse")
    return session_id


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_fragment"),
    [
        (
            TmdbUnavailableError(
                "Не удалось подключиться к api.themoviedb.org. "
                "Домен может быть заблокирован провайдером, DNS или VPN."
            ),
            502,
            "api.themoviedb.org",
        ),
        (TmdbAuthError("TMDB отклонил ключ API."), 400, "ключ"),
        (TmdbRateLimitError("TMDB временно ограничил количество запросов."), 429, "ограничил"),
    ],
)
def test_match_tmdb_reports_the_reason(
    client: TestClient, tmp_path, error, expected_status, expected_fragment
) -> None:
    app.dependency_overrides[get_tmdb_client] = lambda: _FailingTmdbClient(error)
    try:
        session_id = _session_with_one_movie(client, tmp_path)

        response = client.post(f"/scan-sessions/{session_id}/match-tmdb")

        assert response.status_code == expected_status
        detail = response.json()["detail"]
        assert expected_fragment in detail
    finally:
        app.dependency_overrides.pop(get_tmdb_client, None)


@pytest.mark.asyncio
async def test_manual_lookup_keeps_the_outage_status(db_session, tmp_path) -> None:
    """A broad except used to flatten an outage into a 400 "lookup failed"."""
    from backend.app.models.enums import MediaItemStatus, MediaType
    from backend.app.models.media_item import MediaItem
    from backend.app.models.scan_session import ScanSession
    from backend.app.services.tmdb_service import TMDBService

    scan_session = ScanSession(source_path=str(tmp_path), target_path=str(tmp_path))
    db_session.add(scan_session)
    await db_session.flush()
    item = MediaItem(
        scan_session_id=scan_session.id,
        media_type=MediaType.MOVIE,
        status=MediaItemStatus.NEEDS_REVIEW,
        original_title="The Matrix",
        parsed_title="The Matrix",
    )
    db_session.add(item)
    await db_session.commit()

    outage = TmdbUnavailableError("Не удалось подключиться к api.themoviedb.org.")

    class _Failing(FakeTmdbClient):
        async def get_movie_details(self, tmdb_id, language="ru-RU"):
            raise outage

        async def get_tv_details(self, tmdb_id, language="ru-RU"):
            raise outage

    service = TMDBService(db_session, client=_Failing(movie_results=[], tv_results=[]))

    with pytest.raises(TmdbUnavailableError):
        await service.manual_lookup(item.id, tmdb_id=603, media_type="movie", select=False)


def test_match_tmdb_no_longer_raises_a_bare_server_error(client: TestClient, tmp_path) -> None:
    """Regression: this exact path used to return 500 with a raw traceback."""
    app.dependency_overrides[get_tmdb_client] = lambda: _FailingTmdbClient(
        TmdbUnavailableError("Не удалось подключиться к api.themoviedb.org.")
    )
    try:
        session_id = _session_with_one_movie(client, tmp_path)

        response = client.post(f"/scan-sessions/{session_id}/match-tmdb")

        assert response.status_code != 500
        assert "Traceback" not in response.text
    finally:
        app.dependency_overrides.pop(get_tmdb_client, None)
