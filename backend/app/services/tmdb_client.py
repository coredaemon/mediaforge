from typing import Protocol

import httpx

from ..schemas.tmdb import TmdbDetailsResult, TmdbEpisodeResult, TmdbExternalIds, TmdbSearchResult, TmdbSeasonDetailsResult
from ..utils.tmdb_images import tmdb_image_url

RU_LANGUAGE = "ru-RU"
EN_LANGUAGE = "en-US"
IMAGE_LANGUAGES = "ru,null,en"


class TmdbClientProtocol(Protocol):
    async def search_movie(
        self,
        query: str,
        year: int | None = None,
        language: str = RU_LANGUAGE,
    ) -> list[TmdbSearchResult]:
        ...

    async def search_tv(
        self,
        query: str,
        year: int | None = None,
        language: str = RU_LANGUAGE,
    ) -> list[TmdbSearchResult]:
        ...

    async def get_movie_details(self, tmdb_id: int, language: str = RU_LANGUAGE) -> TmdbDetailsResult:
        ...

    async def get_tv_details(self, tmdb_id: int, language: str = RU_LANGUAGE) -> TmdbDetailsResult:
        ...

    async def get_tv_season_details(
        self,
        tmdb_id: int,
        season_number: int,
        language: str = RU_LANGUAGE,
    ) -> TmdbSeasonDetailsResult:
        ...

    async def find_by_external_id(
        self,
        external_id: str,
        external_source: str,
        language: str = RU_LANGUAGE,
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
        language: str = RU_LANGUAGE,
    ) -> list[TmdbSearchResult]:
        params: dict[str, str | int] = {
            "query": query,
            "language": language,
            "include_adult": "false",
            "region": "RU",
            "api_key": self.api_key,
        }
        if year is not None:
            params["year"] = year
        payload = await self._get("/search/movie", params)
        return [self._movie_result(result) for result in payload.get("results", [])]

    async def search_tv(
        self,
        query: str,
        year: int | None = None,
        language: str = RU_LANGUAGE,
    ) -> list[TmdbSearchResult]:
        params: dict[str, str | int] = {
            "query": query,
            "language": language,
            "include_adult": "false",
            "api_key": self.api_key,
        }
        if year is not None:
            params["first_air_date_year"] = year
        payload = await self._get("/search/tv", params)
        return [self._tv_result(result) for result in payload.get("results", [])]

    async def get_movie_details(self, tmdb_id: int, language: str = RU_LANGUAGE) -> TmdbDetailsResult:
        payload = await self._get(
            f"/movie/{tmdb_id}",
            {
                "language": language,
                "append_to_response": "external_ids,images,translations",
                "include_image_language": IMAGE_LANGUAGES,
                "api_key": self.api_key,
            },
        )
        return self._details_from_movie(payload, language)

    async def get_tv_details(self, tmdb_id: int, language: str = RU_LANGUAGE) -> TmdbDetailsResult:
        payload = await self._get(
            f"/tv/{tmdb_id}",
            {
                "language": language,
                "append_to_response": "external_ids,images,translations",
                "include_image_language": IMAGE_LANGUAGES,
                "api_key": self.api_key,
            },
        )
        return self._details_from_tv(payload, language)

    async def get_tv_season_details(
        self,
        tmdb_id: int,
        season_number: int,
        language: str = RU_LANGUAGE,
    ) -> TmdbSeasonDetailsResult:
        payload = await self._get(
            f"/tv/{tmdb_id}/season/{season_number}",
            {
                "language": language,
                "include_image_language": IMAGE_LANGUAGES,
                "api_key": self.api_key,
            },
        )
        return self._season_details_from_tv(payload, language)

    async def find_by_external_id(
        self,
        external_id: str,
        external_source: str,
        language: str = RU_LANGUAGE,
    ) -> list[TmdbSearchResult]:
        payload = await self._get(
            f"/find/{external_id}",
            {
                "external_source": external_source,
                "language": language,
                "api_key": self.api_key,
            },
        )
        results: list[TmdbSearchResult] = []
        for result in payload.get("movie_results", []):
            results.append(self._movie_result(result))
        for result in payload.get("tv_results", []):
            results.append(self._tv_result(result))
        return results

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

    def _details_from_movie(self, payload: dict, language: str) -> TmdbDetailsResult:
        release_date = payload.get("release_date")
        poster_path, backdrop_path = _pick_images(payload)
        return TmdbDetailsResult(
            tmdb_id=payload["id"],
            media_type="movie",
            title=payload.get("title") or "",
            original_title=payload.get("original_title"),
            overview=payload.get("overview"),
            year=_year_from_date(release_date),
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            external_ids=_external_ids(payload.get("external_ids") or {}),
            metadata_language=language,
        )

    def _details_from_tv(self, payload: dict, language: str) -> TmdbDetailsResult:
        first_air_date = payload.get("first_air_date")
        poster_path, backdrop_path = _pick_images(payload)
        return TmdbDetailsResult(
            tmdb_id=payload["id"],
            media_type="tv",
            title=payload.get("name") or "",
            original_title=payload.get("original_name"),
            overview=payload.get("overview"),
            year=_year_from_date(first_air_date),
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            external_ids=_external_ids(payload.get("external_ids") or {}),
            metadata_language=language,
        )

    def _season_details_from_tv(self, payload: dict, language: str) -> TmdbSeasonDetailsResult:
        season_number = int(payload.get("season_number") or 0)
        episodes = [
            TmdbEpisodeResult(
                tmdb_episode_id=episode.get("id"),
                season_number=int(episode.get("season_number") or season_number),
                episode_number=int(episode.get("episode_number") or 0),
                title=episode.get("name"),
                overview=episode.get("overview"),
                air_date=episode.get("air_date"),
            )
            for episode in payload.get("episodes", [])
        ]
        poster_path = payload.get("poster_path")
        return TmdbSeasonDetailsResult(
            tmdb_season_id=payload.get("id"),
            season_number=season_number,
            title=payload.get("name"),
            overview=payload.get("overview"),
            poster_path=poster_path,
            poster_url=tmdb_image_url(poster_path),
            episodes=episodes,
            metadata_language=language,
        )


def _external_ids(payload: dict) -> TmdbExternalIds:
    tvdb_id = payload.get("tvdb_id")
    return TmdbExternalIds(
        imdb_id=payload.get("imdb_id"),
        tvdb_id=int(tvdb_id) if tvdb_id not in (None, "") else None,
        wikidata_id=payload.get("wikidata_id"),
    )


def _pick_images(payload: dict) -> tuple[str | None, str | None]:
    images = payload.get("images") or {}
    posters = images.get("posters") or []
    backdrops = images.get("backdrops") or []
    poster_path = _pick_localized_image(posters, "poster_path") or payload.get("poster_path")
    backdrop_path = _pick_localized_image(backdrops, "file_path") or payload.get("backdrop_path")
    return poster_path, backdrop_path


def _pick_localized_image(images: list[dict], key: str) -> str | None:
    for language in ("ru", None, "en"):
        for image in images:
            iso = image.get("iso_639_1")
            if iso == language or (language is None and iso in (None, "")):
                value = image.get(key)
                if value:
                    return value
    if images:
        return images[0].get(key)
    return None


async def fetch_localized_details(
    client: TmdbClientProtocol,
    *,
    tmdb_id: int,
    media_type: str,
) -> TmdbDetailsResult:
    if media_type == "movie":
        details = await client.get_movie_details(tmdb_id, RU_LANGUAGE)
        if not _has_localized_text(details):
            fallback = await client.get_movie_details(tmdb_id, EN_LANGUAGE)
            return _merge_details(details, fallback)
        return details

    details = await client.get_tv_details(tmdb_id, RU_LANGUAGE)
    if not _has_localized_text(details):
        fallback = await client.get_tv_details(tmdb_id, EN_LANGUAGE)
        return _merge_details(details, fallback)
    return details


async def fetch_localized_tv_season_details(
    client: TmdbClientProtocol,
    *,
    tmdb_id: int,
    season_number: int,
) -> TmdbSeasonDetailsResult:
    details = await client.get_tv_season_details(tmdb_id, season_number, RU_LANGUAGE)
    if details.episodes and any((episode.title or "").strip() or (episode.overview or "").strip() for episode in details.episodes):
        return details
    fallback = await client.get_tv_season_details(tmdb_id, season_number, EN_LANGUAGE)
    episodes_by_number = {episode.episode_number: episode for episode in fallback.episodes}
    merged = []
    for episode in details.episodes or fallback.episodes:
        fallback_episode = episodes_by_number.get(episode.episode_number)
        merged.append(
            TmdbEpisodeResult(
                tmdb_episode_id=episode.tmdb_episode_id or (fallback_episode.tmdb_episode_id if fallback_episode else None),
                season_number=episode.season_number,
                episode_number=episode.episode_number,
                title=episode.title or (fallback_episode.title if fallback_episode else None),
                overview=episode.overview or (fallback_episode.overview if fallback_episode else None),
                air_date=episode.air_date or (fallback_episode.air_date if fallback_episode else None),
            )
        )
    details.episodes = merged
    details.metadata_language = fallback.metadata_language
    return details


def _has_localized_text(details: TmdbDetailsResult) -> bool:
    return bool((details.title or "").strip() and (details.overview or "").strip())


def _merge_details(primary: TmdbDetailsResult, fallback: TmdbDetailsResult) -> TmdbDetailsResult:
    return TmdbDetailsResult(
        tmdb_id=primary.tmdb_id,
        media_type=primary.media_type,
        title=primary.title or fallback.title,
        original_title=primary.original_title or fallback.original_title,
        overview=primary.overview or fallback.overview,
        year=primary.year or fallback.year,
        poster_path=primary.poster_path or fallback.poster_path,
        backdrop_path=primary.backdrop_path or fallback.backdrop_path,
        external_ids=primary.external_ids
        if any((primary.external_ids.imdb_id, primary.external_ids.tvdb_id, primary.external_ids.wikidata_id))
        else fallback.external_ids,
        metadata_language=primary.metadata_language if _has_localized_text(primary) else fallback.metadata_language,
        overview_is_fallback=not bool((primary.overview or "").strip()) and bool((fallback.overview or "").strip()),
    )


def apply_details_to_candidate(candidate, details: TmdbDetailsResult) -> None:
    if not candidate.overview and details.overview:
        candidate.overview = details.overview
    if not candidate.original_title and details.original_title:
        candidate.original_title = details.original_title
    candidate.year = details.year or candidate.year
    candidate.poster_path = details.poster_path or candidate.poster_path
    candidate.backdrop_path = details.backdrop_path or candidate.backdrop_path
    candidate.poster_url = tmdb_image_url(candidate.poster_path)
    candidate.backdrop_url = tmdb_image_url(candidate.backdrop_path, "w780")
    candidate.imdb_id = details.external_ids.imdb_id
    candidate.tvdb_id = details.external_ids.tvdb_id
    candidate.wikidata_id = details.external_ids.wikidata_id
    candidate.metadata_language = details.metadata_language
    candidate.overview_is_fallback = details.overview_is_fallback


def apply_details_to_item(item, details: TmdbDetailsResult) -> None:
    item.localized_title = details.title or item.matched_title or item.localized_title
    item.localized_overview = details.overview or item.localized_overview
    item.tmdb_original_title = details.original_title or item.tmdb_original_title
    item.poster_path = details.poster_path
    item.backdrop_path = details.backdrop_path
    item.poster_url = tmdb_image_url(details.poster_path)
    item.backdrop_url = tmdb_image_url(details.backdrop_path, "w780")
    item.imdb_id = details.external_ids.imdb_id
    item.tvdb_id = details.external_ids.tvdb_id
    item.wikidata_id = details.external_ids.wikidata_id
    item.metadata_language = details.metadata_language


def _year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
