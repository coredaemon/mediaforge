"""TMDB failures must reach the user as an explanation, not a 500 traceback."""

import httpx
import pytest

from backend.app.services.tmdb_client import (
    TmdbApiKeyMissingError,
    TmdbAuthError,
    TmdbClient,
    TmdbError,
    TmdbRateLimitError,
    TmdbUnavailableError,
)


@pytest.fixture
def patch_httpx(monkeypatch):
    """Route TmdbClient's httpx calls through a MockTransport."""

    def _apply(handler):
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(
            "backend.app.services.tmdb_client.httpx.AsyncClient", factory
        )

    return _apply


@pytest.mark.asyncio
async def test_blocked_domain_becomes_a_readable_error(patch_httpx) -> None:
    """The reported bug: a blackholed domain raised a bare httpx.ConnectError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    patch_httpx(handler)

    with pytest.raises(TmdbUnavailableError) as excinfo:
        await TmdbClient(api_key="key").search_movie("Matrix")

    message = str(excinfo.value)
    assert "api.themoviedb.org" in message
    assert "VPN" in message


@pytest.mark.asyncio
async def test_timeout_becomes_a_readable_error(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    patch_httpx(handler)

    with pytest.raises(TmdbUnavailableError):
        await TmdbClient(api_key="key").search_movie("Matrix")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_key_is_reported_as_an_auth_problem(patch_httpx, status: int) -> None:
    patch_httpx(lambda request: httpx.Response(status, json={"status_message": "invalid"}))

    with pytest.raises(TmdbAuthError) as excinfo:
        await TmdbClient(api_key="bad").search_movie("Matrix")

    assert "ключ" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_throttling_is_reported_separately(patch_httpx) -> None:
    patch_httpx(lambda request: httpx.Response(429))

    with pytest.raises(TmdbRateLimitError):
        await TmdbClient(api_key="key").search_movie("Matrix")


@pytest.mark.asyncio
async def test_server_error_is_treated_as_unavailable(patch_httpx) -> None:
    patch_httpx(lambda request: httpx.Response(503))

    with pytest.raises(TmdbUnavailableError) as excinfo:
        await TmdbClient(api_key="key").search_movie("Matrix")

    assert "503" in str(excinfo.value)


@pytest.mark.asyncio
async def test_successful_search_is_unaffected(patch_httpx) -> None:
    """Guard the happy path against the new error handling."""
    payload = {
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-30",
                "popularity": 50.0,
            }
        ]
    }
    patch_httpx(lambda request: httpx.Response(200, json=payload))

    results = await TmdbClient(api_key="key").search_movie("Matrix")

    assert len(results) == 1
    assert results[0].tmdb_id == 603
    assert results[0].title == "The Matrix"


@pytest.mark.asyncio
async def test_missing_key_still_short_circuits_before_any_request(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request may be made without an API key")

    patch_httpx(handler)

    with pytest.raises(TmdbApiKeyMissingError):
        await TmdbClient(api_key="").search_movie("Matrix")


def test_all_tmdb_failures_share_a_base_class() -> None:
    """Callers that only care about "TMDB did not work" can catch one type."""
    for error_type in (
        TmdbApiKeyMissingError,
        TmdbUnavailableError,
        TmdbAuthError,
        TmdbRateLimitError,
    ):
        assert issubclass(error_type, TmdbError)
