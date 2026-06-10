from typing import Protocol

import httpx

from ..schemas.tmdb import TmdbSearchResult


class TmdbClientProtocol(Protocol):
    async def search_movie(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        ...

    async def search_tv(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        ...


class TmdbApiKeyMissingError(RuntimeError):
    """Raised when TMDB matching is requested without a local API key."""


class TmdbClient:
    base_url = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, timeout_seconds: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search_movie(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        params: dict[str, str | int] = {"query": query, "language": language, "api_key": self.api_key}
        if year is not None:
            params["year"] = year
        payload = await self._get("/search/movie", params)
        return [self._movie_result(result) for result in payload.get("results", [])]

    async def search_tv(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        params: dict[str, str | int] = {"query": query, "language": language, "api_key": self.api_key}
        if year is not None:
            params["first_air_date_year"] = year
        payload = await self._get("/search/tv", params)
        return [self._tv_result(result) for result in payload.get("results", [])]

    async def _get(self, path: str, params: dict[str, str | int]) -> dict:
        if not self.api_key:
            raise TmdbApiKeyMissingError("TMDB_API_KEY is not configured")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    def _movie_result(self, payload: dict) -> TmdbSearchResult:
        release_date = payload.get("release_date") or None
        return TmdbSearchResult(
            tmdb_id=payload["id"],
            media_type="movie",
            title=payload.get("title") or payload.get("name") or "",
            original_title=payload.get("original_title"),
            overview=payload.get("overview"),
            release_date=release_date,
            year=_year_from_date(release_date),
            poster_path=payload.get("poster_path"),
            backdrop_path=payload.get("backdrop_path"),
            vote_average=payload.get("vote_average"),
            popularity=payload.get("popularity"),
            raw_json=payload,
        )

    def _tv_result(self, payload: dict) -> TmdbSearchResult:
        first_air_date = payload.get("first_air_date") or None
        return TmdbSearchResult(
            tmdb_id=payload["id"],
            media_type="tv",
            title=payload.get("name") or payload.get("title") or "",
            original_title=payload.get("original_name"),
            overview=payload.get("overview"),
            first_air_date=first_air_date,
            year=_year_from_date(first_air_date),
            poster_path=payload.get("poster_path"),
            backdrop_path=payload.get("backdrop_path"),
            vote_average=payload.get("vote_average"),
            popularity=payload.get("popularity"),
            raw_json=payload,
        )


def _year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
