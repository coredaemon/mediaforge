from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..models.enums import MediaItemStatus, MediaType, ReviewDecision
from ..models.media_item import MediaItem
from ..models.tmdb_match_candidate import TmdbMatchCandidate
from ..repositories.app_settings_repository import AppSettingsRepository
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ..schemas.tmdb import TmdbDetailsResult, TmdbMatchResult, TmdbSearchResult
from ..utils.tmdb_images import tmdb_image_url
from .processed_media_service import ProcessedMediaService
from .scan_session_service import ScanSessionNotFoundError
from .tmdb_client import (
    EN_LANGUAGE,
    RU_LANGUAGE,
    TmdbApiKeyMissingError,
    TmdbClient,
    TmdbClientProtocol,
    apply_details_to_candidate,
    apply_details_to_item,
    fetch_localized_details,
)
from .tmdb_scoring import score_tmdb_candidate

AUTO_SELECT_THRESHOLD = 0.80


class TMDBService:
    def __init__(self, session: AsyncSession, client: TmdbClientProtocol | None = None) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_items = MediaItemRepository(session)
        self.media_files = MediaFileRepository(session)
        self.candidates = TmdbMatchCandidateRepository(session)
        self.processed_media = ProcessedMediaService(session)
        self.client = client or TmdbClient(get_settings().tmdb_api_key)

    async def match_scan_session(self, session_id: int, force: bool = False) -> TmdbMatchResult:
        scan_session = await self.scan_sessions.get(session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {session_id} was not found.")

        if isinstance(self.client, TmdbClient) and not self.client.api_key:
            app_settings = await AppSettingsRepository(self.session).get_or_create()
            if app_settings.tmdb_api_key:
                self.client = TmdbClient(app_settings.tmdb_api_key)
            else:
                raise TmdbApiKeyMissingError("TMDB_API_KEY is not configured")

        matched_count = 0
        needs_review_count = 0
        unmatched_count = 0
        skipped_count = 0

        for item in await self.media_items.list_matchable_by_scan_session(session_id):
            if item.reused_from_memory and item.tmdb_id and not force:
                skipped_count += 1
                continue
            if item.status == MediaItemStatus.MATCHED and not force:
                skipped_count += 1
                continue

            outcome = await self._match_item(item)
            if outcome == MediaItemStatus.MATCHED:
                matched_count += 1
            elif outcome == MediaItemStatus.UNMATCHED:
                unmatched_count += 1
            elif outcome == MediaItemStatus.NEEDS_REVIEW:
                needs_review_count += 1

            video_file = await self.media_files.get_video_for_media_item(item.id)
            if outcome == MediaItemStatus.MATCHED:
                await self.processed_media.record_from_item(item, video_file, session_id=session_id)

        await self.session.commit()
        return TmdbMatchResult(
            scan_session_id=session_id,
            matched_count=matched_count,
            needs_review_count=needs_review_count,
            unmatched_count=unmatched_count,
            skipped_count=skipped_count,
        )

    async def manual_search(
        self,
        item_id: int,
        query: str,
        year: int | None,
        media_type: str,
        language: str = RU_LANGUAGE,
    ) -> list[TmdbMatchCandidate]:
        item = await self.media_items.get_by_id(item_id)
        if item is None:
            raise MediaItemNotFoundError(f"Media item {item_id} was not found.")
        await self._ensure_client()

        normalized_type = _normalize_search_media_type(media_type)
        if normalized_type == "movie":
            results = await self._search_movie_with_fallback(query, year)
        elif normalized_type == "tv":
            results = await self._search_tv_with_fallback(query, year)
        else:
            raise TmdbLookupError(f"Unsupported media type for search: {media_type}")

        saved: list[TmdbMatchCandidate] = []
        for result in results:
            score = score_tmdb_candidate(result.title, result.year or year, result)
            candidate = await self.candidates.create(self._candidate_from_result(item.id, result, score))
            await self._enrich_candidate(candidate)
            saved.append(candidate)
        await self.session.commit()
        for candidate in saved:
            await self.session.refresh(candidate)
        return saved

    async def manual_lookup(
        self,
        item_id: int,
        *,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        tvdb_id: int | None = None,
        media_type: str | None = None,
        select: bool = False,
    ) -> TmdbMatchCandidate:
        item = await self.media_items.get_by_id(item_id)
        if item is None:
            raise MediaItemNotFoundError(f"Media item {item_id} was not found.")
        await self._ensure_client()

        warning: str | None = None
        resolved_type: str | None = None
        resolved_id: int | None = None

        if tmdb_id is not None:
            resolved_id = tmdb_id
            resolved_type = _normalize_search_media_type(media_type or "movie")
            try:
                details = await fetch_localized_details(self.client, tmdb_id=tmdb_id, media_type=resolved_type)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise TmdbLookupNotFoundError(f"TMDB ID {tmdb_id} not found.") from exc
                raise TmdbLookupError(f"TMDB lookup failed: {exc}") from exc
            except Exception as exc:
                raise TmdbLookupError(f"TMDB lookup failed: {exc}") from exc
            result = _search_result_from_details(details)
        elif imdb_id:
            results = await self.client.find_by_external_id(imdb_id.strip(), "imdb_id")
            if not results:
                raise TmdbLookupNotFoundError(f"IMDb ID {imdb_id} not found in TMDB.")
            picked = _pick_find_result(results, media_type)
            resolved_id = picked.tmdb_id
            resolved_type = picked.media_type
            details = await fetch_localized_details(self.client, tmdb_id=resolved_id, media_type=resolved_type)
            result = _search_result_from_details(details)
            if media_type and _normalize_search_media_type(media_type) != resolved_type:
                warning = f"Found {resolved_type}, but requested {media_type}."
        elif tvdb_id is not None:
            results = await self.client.find_by_external_id(str(tvdb_id), "tvdb_id")
            if not results:
                raise TmdbLookupNotFoundError(f"TVDB ID {tvdb_id} not found in TMDB.")
            picked = _pick_find_result(results, media_type or "tv")
            resolved_id = picked.tmdb_id
            resolved_type = picked.media_type
            details = await fetch_localized_details(self.client, tmdb_id=resolved_id, media_type=resolved_type)
            result = _search_result_from_details(details)
            if media_type and _normalize_search_media_type(media_type) != resolved_type:
                warning = f"Found {resolved_type}, but requested {media_type}."
        else:
            raise TmdbLookupError("Provide tmdb_id, imdb_id, or tvdb_id.")

        score = 1.0
        candidate = await self.candidates.create(self._candidate_from_result(item.id, result, score))
        apply_details_to_candidate(candidate, details)
        await self.session.flush()

        if select:
            await self.candidates.clear_selected_for_media_item(item.id)
            candidate.is_selected = True
            apply_details_to_item(item, details)
            item.tmdb_id = candidate.tmdb_id
            item.tmdb_media_type = candidate.media_type
            item.matched_title = candidate.title
            item.matched_year = candidate.year
            item.match_confidence = candidate.score
            item.status = MediaItemStatus.MATCHED
            item.needs_review = False
            item.review_decision = ReviewDecision.MANUAL_OVERRIDE
            item.reviewed_at = datetime.now(UTC)
            item.manual_tmdb_id = resolved_id
            item.manual_imdb_id = imdb_id
            item.manual_tvdb_id = tvdb_id
            item.manual_media_type = resolved_type
            video_file = await self.media_files.get_video_for_media_item(item.id)
            await self.processed_media.record_from_item(item, video_file, session_id=item.scan_session_id)

        await self.session.commit()
        await self.session.refresh(candidate)
        if warning:
            candidate.raw_json = {**(candidate.raw_json or {}), "lookup_warning": warning}
        return candidate

    async def _ensure_client(self) -> None:
        if isinstance(self.client, TmdbClient) and not self.client.api_key:
            app_settings = await AppSettingsRepository(self.session).get_or_create()
            if app_settings.tmdb_api_key:
                self.client = TmdbClient(app_settings.tmdb_api_key)
            else:
                raise TmdbApiKeyMissingError("TMDB_API_KEY is not configured")

    async def select_candidate(self, item_id: int, candidate_id: int) -> TmdbMatchCandidate:
        item = await self.media_items.get_by_id(item_id)
        if item is None:
            raise MediaItemNotFoundError(f"Media item {item_id} was not found.")

        candidate = await self.candidates.get_by_id(candidate_id)
        if candidate is None:
            raise TmdbCandidateNotFoundError(f"TMDB candidate {candidate_id} was not found.")
        if candidate.media_item_id != item.id:
            raise TmdbCandidateOwnershipError(
                f"TMDB candidate {candidate_id} does not belong to media item {item_id}."
            )

        await self.candidates.clear_selected_for_media_item(item.id)
        candidate.is_selected = True
        await self._enrich_candidate(candidate)
        try:
            details = await fetch_localized_details(
                self.client,
                tmdb_id=candidate.tmdb_id,
                media_type=candidate.media_type,
            )
            apply_details_to_candidate(candidate, details)
            apply_details_to_item(item, details)
        except Exception:
            item.poster_url = candidate.poster_url or tmdb_image_url(candidate.poster_path)
            item.backdrop_url = candidate.backdrop_url or tmdb_image_url(candidate.backdrop_path, "w780")
            item.imdb_id = candidate.imdb_id
            item.tvdb_id = candidate.tvdb_id
            item.wikidata_id = candidate.wikidata_id
            item.metadata_language = candidate.metadata_language or RU_LANGUAGE
        item.tmdb_id = candidate.tmdb_id
        item.tmdb_media_type = candidate.media_type
        item.matched_title = candidate.title
        item.matched_year = candidate.year
        item.match_confidence = candidate.score
        item.status = MediaItemStatus.MATCHED
        item.needs_review = False
        item.review_decision = ReviewDecision.MANUAL_OVERRIDE
        item.reviewed_at = item.reviewed_at or datetime.now(UTC)

        video_file = await self.media_files.get_video_for_media_item(item.id)
        await self.processed_media.record_from_item(item, video_file, session_id=item.scan_session_id)
        await self.session.commit()
        await self.session.refresh(candidate)
        return candidate

    async def _match_item(self, item: MediaItem) -> MediaItemStatus:
        item.status = MediaItemStatus.MATCHING
        item.tmdb_id = None
        item.tmdb_media_type = None
        item.matched_title = None
        item.matched_year = None
        item.match_confidence = None
        await self.candidates.delete_for_media_item(item.id)
        await self.session.flush()

        results, score_title, score_year = await self._search_for_item(item)
        if not results or not score_title:
            item.status = MediaItemStatus.UNMATCHED
            item.needs_review = True
            await self.session.flush()
            return item.status

        scored = sorted(
            (
                (
                    result,
                    score_tmdb_candidate(
                        result.title,
                        result.year or score_year,
                        result,
                    ),
                )
                for result in results
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        saved_candidates = [
            await self.candidates.create(self._candidate_from_result(item.id, result, score))
            for result, score in scored
        ]
        best_candidate = saved_candidates[0]

        if best_candidate.score >= AUTO_SELECT_THRESHOLD:
            best_candidate.is_selected = True
            item.tmdb_id = best_candidate.tmdb_id
            item.tmdb_media_type = best_candidate.media_type
            item.matched_title = best_candidate.title
            item.matched_year = best_candidate.year
            item.match_confidence = best_candidate.score
            item.localized_title = best_candidate.title
            item.localized_overview = best_candidate.overview
            item.tmdb_original_title = best_candidate.original_title
            item.poster_path = best_candidate.poster_path
            item.backdrop_path = best_candidate.backdrop_path
            item.poster_url = best_candidate.poster_url
            item.backdrop_url = best_candidate.backdrop_url
            item.imdb_id = best_candidate.imdb_id
            item.tvdb_id = best_candidate.tvdb_id
            item.wikidata_id = best_candidate.wikidata_id
            item.metadata_language = best_candidate.metadata_language
            item.status = MediaItemStatus.MATCHED
            item.needs_review = False
        else:
            item.status = MediaItemStatus.NEEDS_REVIEW
            item.needs_review = True

        for candidate in saved_candidates[:3]:
            await self._enrich_candidate(candidate)
        if best_candidate.score >= AUTO_SELECT_THRESHOLD:
            item.imdb_id = best_candidate.imdb_id
            item.tvdb_id = best_candidate.tvdb_id
            item.wikidata_id = best_candidate.wikidata_id
            item.poster_url = best_candidate.poster_url
            item.backdrop_url = best_candidate.backdrop_url
            item.metadata_language = best_candidate.metadata_language
            if best_candidate.overview:
                item.localized_overview = best_candidate.overview

        await self.session.flush()
        return item.status

    async def _enrich_candidate(self, candidate: TmdbMatchCandidate) -> None:
        try:
            details = await fetch_localized_details(
                self.client,
                tmdb_id=candidate.tmdb_id,
                media_type=candidate.media_type,
            )
            apply_details_to_candidate(candidate, details)
            await self.session.flush()
        except Exception:
            candidate.poster_url = tmdb_image_url(candidate.poster_path)
            candidate.backdrop_url = tmdb_image_url(candidate.backdrop_path, "w780")
            candidate.metadata_language = candidate.metadata_language or RU_LANGUAGE

    async def _search_for_item(self, item: MediaItem) -> tuple[list[TmdbSearchResult], str | None, int | None]:
        media_type = _priority_media_type(item)
        if media_type not in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
            return [], None, None

        for query in _priority_queries(item):
            year = _priority_year(item)
            if media_type == MediaType.MOVIE:
                results = await self._search_movie_with_fallback(query, year)
            else:
                results = await self._search_tv_with_fallback(query, year)
            if results:
                return results, query, year
        return [], None, None

    async def _search_movie_with_fallback(self, query: str, year: int | None) -> list[TmdbSearchResult]:
        results = await self.client.search_movie(query=query, year=year, language=RU_LANGUAGE)
        if results:
            return results
        return await self.client.search_movie(query=query, year=year, language=EN_LANGUAGE)

    async def _search_tv_with_fallback(self, query: str, year: int | None) -> list[TmdbSearchResult]:
        results = await self.client.search_tv(query=query, year=year, language=RU_LANGUAGE)
        if results:
            return results
        return await self.client.search_tv(query=query, year=year, language=EN_LANGUAGE)

    def _candidate_from_result(self, media_item_id: int, result: TmdbSearchResult, score: float) -> TmdbMatchCandidate:
        return TmdbMatchCandidate(
            media_item_id=media_item_id,
            tmdb_id=result.tmdb_id,
            media_type=result.media_type,
            title=result.title,
            original_title=result.original_title,
            overview=result.overview,
            release_date=result.release_date,
            first_air_date=result.first_air_date,
            year=result.year,
            poster_path=result.poster_path,
            backdrop_path=result.backdrop_path,
            poster_url=tmdb_image_url(result.poster_path),
            backdrop_url=tmdb_image_url(result.backdrop_path, "w780"),
            metadata_language=RU_LANGUAGE,
            vote_average=result.vote_average,
            popularity=result.popularity,
            raw_json=result.raw_json,
            score=score,
            is_selected=False,
        )


class MediaItemNotFoundError(LookupError):
    """Raised when a media item id does not exist."""


class TmdbCandidateNotFoundError(LookupError):
    """Raised when a TMDB candidate id does not exist."""


class TmdbCandidateOwnershipError(ValueError):
    """Raised when a TMDB candidate belongs to another media item."""


class TmdbLookupError(ValueError):
    """Raised when a manual TMDB lookup request is invalid or fails."""


class TmdbLookupNotFoundError(LookupError):
    """Raised when TMDB cannot resolve the provided external id."""


def _priority_queries(item: MediaItem) -> list[str]:
    values: list[str | None] = [
        *(item.tmdb_queries or []),
        item.gemini_clean_title,
        item.ai_clean_title,
        item.parsed_title,
        item.original_title,
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        key = normalized.lower()
        if normalized and key not in seen:
            queries.append(normalized)
            seen.add(key)
    return queries[:5]


def _priority_year(item: MediaItem) -> int | None:
    return item.gemini_year or item.ai_year or item.year


def _normalize_search_media_type(media_type: str) -> str:
    normalized = (media_type or "movie").strip().lower()
    if normalized in {"movie", "movies", "film"}:
        return "movie"
    if normalized in {"tv", "tv_show", "tv_show", "series", "show", "tv_episode", "episode"}:
        return "tv"
    return normalized


def _pick_find_result(results: list[TmdbSearchResult], media_type: str | None) -> TmdbSearchResult:
    if media_type:
        wanted = _normalize_search_media_type(media_type)
        for result in results:
            if result.media_type == wanted:
                return result
    return results[0]


def _search_result_from_details(details: TmdbDetailsResult) -> TmdbSearchResult:
    return TmdbSearchResult(
        tmdb_id=details.tmdb_id,
        media_type=details.media_type,
        title=details.title,
        original_title=details.original_title,
        overview=details.overview,
        year=details.year,
        poster_path=details.poster_path,
        backdrop_path=details.backdrop_path,
    )


def _priority_media_type(item: MediaItem) -> MediaType:
    for value in (item.gemini_media_type, item.ai_media_type, item.media_type):
        if isinstance(value, MediaType) and value in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
            return value
        if isinstance(value, str):
            try:
                parsed = MediaType(value)
                if parsed in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
                    return parsed
            except ValueError:
                if value.upper() in {"MOVIE", "TV_EPISODE", "TV_SHOW"}:
                    return MediaType(value.upper())
    return MediaType.UNKNOWN
