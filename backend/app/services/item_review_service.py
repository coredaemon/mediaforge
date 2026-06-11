from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaItemStatus, MediaType, ReviewDecision
from ..models.media_item import MediaItem
from ..models.recognition_memory import RecognitionCorrection
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.recognition_memory_repository import RecognitionMemoryRepository
from ..schemas.media_item import MediaItemRead
from ..schemas.review import ReviewDecisionRequest
from .processed_media_service import ProcessedMediaService
from .tmdb_service import (
    MediaItemNotFoundError,
    TMDBService,
    TmdbLookupError,
    TmdbLookupNotFoundError,
)


class ItemReviewService:
    def __init__(self, session: AsyncSession, tmdb_service: TMDBService | None = None) -> None:
        self.session = session
        self.media_items = MediaItemRepository(session)
        self.media_files = MediaFileRepository(session)
        self.memory = RecognitionMemoryRepository(session)
        self.processed_media = ProcessedMediaService(session)
        self.tmdb = tmdb_service or TMDBService(session)

    async def apply_review_decision(self, item_id: int, payload: ReviewDecisionRequest) -> MediaItemRead:
        item = await self.media_items.get_by_id(item_id)
        if item is None:
            raise MediaItemNotFoundError(f"Media item {item_id} was not found.")

        await self._apply_decision_fields(item, payload)
        await self.session.commit()
        await self.session.refresh(item)
        return MediaItemRead.model_validate(item)

    async def _apply_decision_fields(self, item: MediaItem, payload: ReviewDecisionRequest) -> None:
        item.review_decision = payload.decision.value
        item.reviewed_at = datetime.now(UTC)
        item.review_note = payload.note

        if payload.manual_title:
            item.manual_title = payload.manual_title.strip()
        if payload.manual_year is not None:
            item.manual_year = payload.manual_year
        if payload.manual_tmdb_id is not None:
            item.manual_tmdb_id = payload.manual_tmdb_id
        if payload.manual_imdb_id:
            item.manual_imdb_id = payload.manual_imdb_id.strip()
        if payload.manual_tvdb_id is not None:
            item.manual_tvdb_id = payload.manual_tvdb_id
        if payload.manual_media_type:
            item.manual_media_type = payload.manual_media_type

        if payload.decision == ReviewDecision.IGNORED:
            item.status = MediaItemStatus.IGNORED
            item.needs_review = False
        elif payload.decision == ReviewDecision.DEFERRED:
            item.needs_review = True
        elif payload.decision == ReviewDecision.APPROVED:
            if item.status == MediaItemStatus.MATCHED:
                item.needs_review = False
        elif payload.decision == ReviewDecision.MANUAL_OVERRIDE:
            await self._apply_manual_override(item, payload)

        if payload.decision in {ReviewDecision.APPROVED, ReviewDecision.MANUAL_OVERRIDE}:
            video_file = await self.media_files.get_video_for_media_item(item.id)
            await self.processed_media.record_from_item(item, video_file, session_id=item.scan_session_id)
            await self._save_correction(item, payload)

    async def _apply_manual_override(self, item: MediaItem, payload: ReviewDecisionRequest) -> None:
        if payload.manual_tmdb_id or payload.manual_imdb_id or payload.manual_tvdb_id:
            try:
                candidate = await self.tmdb.manual_lookup(
                    item.id,
                    tmdb_id=payload.manual_tmdb_id,
                    imdb_id=payload.manual_imdb_id,
                    tvdb_id=payload.manual_tvdb_id,
                    media_type=payload.manual_media_type or item.manual_media_type,
                    select=True,
                )
                if candidate:
                    return
            except (TmdbLookupNotFoundError, TmdbLookupError):
                pass

        if payload.manual_title:
            item.parsed_title = payload.manual_title
            item.matched_title = payload.manual_title
        if payload.manual_year is not None:
            item.year = payload.manual_year
            item.matched_year = payload.manual_year
        if payload.manual_media_type:
            try:
                parsed = MediaType(payload.manual_media_type.upper())
                if parsed in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
                    item.media_type = parsed
            except ValueError:
                pass
        item.needs_review = False

    async def _save_correction(self, item: MediaItem, payload: ReviewDecisionRequest) -> None:
        if not (payload.manual_title or payload.manual_tmdb_id or payload.manual_imdb_id):
            return
        await self.memory.create_correction(
            RecognitionCorrection(
                media_item_id=item.id,
                original_title=item.original_title,
                previous_title=item.parsed_title,
                corrected_title=payload.manual_title or item.matched_title or item.parsed_title or "",
                corrected_year=payload.manual_year or item.matched_year or item.year,
                corrected_media_type=payload.manual_media_type or item.media_type.value,
                removed_tokens_json=None,
                confidence=1.0,
            )
        )
