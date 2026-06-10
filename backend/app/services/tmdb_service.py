from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..models.enums import MediaItemStatus, MediaType
from ..models.media_item import MediaItem
from ..models.tmdb_match_candidate import TmdbMatchCandidate
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ..schemas.tmdb import TmdbMatchResult, TmdbSearchResult
from .scan_session_service import ScanSessionNotFoundError
from .tmdb_client import TmdbApiKeyMissingError, TmdbClient, TmdbClientProtocol
from .tmdb_scoring import score_tmdb_candidate

AUTO_SELECT_THRESHOLD = 0.80


class TMDBService:
    def __init__(self, session: AsyncSession, client: TmdbClientProtocol | None = None) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_items = MediaItemRepository(session)
        self.candidates = TmdbMatchCandidateRepository(session)
        self.client = client or TmdbClient(get_settings().tmdb_api_key)

    async def match_scan_session(self, session_id: int, force: bool = False) -> TmdbMatchResult:
        scan_session = await self.scan_sessions.get(session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {session_id} was not found.")

        if isinstance(self.client, TmdbClient) and not self.client.api_key:
            raise TmdbApiKeyMissingError("TMDB_API_KEY is not configured")

        matched_count = 0
        needs_review_count = 0
        unmatched_count = 0
        skipped_count = 0

        for item in await self.media_items.list_matchable_by_scan_session(session_id):
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

        await self.session.commit()
        return TmdbMatchResult(
            scan_session_id=session_id,
            matched_count=matched_count,
            needs_review_count=needs_review_count,
            unmatched_count=unmatched_count,
            skipped_count=skipped_count,
        )

    async def _match_item(self, item: MediaItem) -> MediaItemStatus:
        item.status = MediaItemStatus.MATCHING
        item.tmdb_id = None
        item.tmdb_media_type = None
        item.matched_title = None
        item.matched_year = None
        item.match_confidence = None
        await self.candidates.delete_for_media_item(item.id)
        await self.session.flush()

        results = await self._search_for_item(item)
        if not results:
            item.status = MediaItemStatus.UNMATCHED
            item.needs_review = True
            await self.session.flush()
            return item.status

        scored = sorted(
            ((result, score_tmdb_candidate(item.parsed_title or "", item.year, result)) for result in results),
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
            item.status = MediaItemStatus.MATCHED
            item.needs_review = False
        else:
            item.status = MediaItemStatus.NEEDS_REVIEW
            item.needs_review = True

        await self.session.flush()
        return item.status

    async def _search_for_item(self, item: MediaItem) -> list[TmdbSearchResult]:
        query = item.parsed_title or ""
        if item.media_type == MediaType.MOVIE:
            return await self.client.search_movie(query=query, year=item.year)
        if item.media_type == MediaType.TV_EPISODE:
            return await self.client.search_tv(query=query)
        return []

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
            vote_average=result.vote_average,
            popularity=result.popularity,
            raw_json=result.raw_json,
            score=score,
            is_selected=False,
        )
