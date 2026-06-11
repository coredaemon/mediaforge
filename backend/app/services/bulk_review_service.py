from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaItemStatus, ReviewDecision
from ..models.media_item import MediaItem
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..schemas.review import BulkApproveRequest, BulkReviewDecisionRequest, BulkReviewResult, ReviewDecisionRequest
from .item_review_service import ItemReviewService
from .processed_media_service import ProcessedMediaService
from .scan_session_service import ScanSessionNotFoundError, ScanSessionService


class BulkReviewError(ValueError):
    """Raised when bulk review input is invalid."""


class BulkReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionService(session)
        self.media_items = MediaItemRepository(session)
        self.media_files = MediaFileRepository(session)
        self.processed_media = ProcessedMediaService(session)

    async def approve_all(self, session_id: int, payload: BulkApproveRequest) -> BulkReviewResult:
        await self.scan_sessions.get_scan_session(session_id)

        items = await self.media_items.list_by_scan_session(session_id)
        if payload.scope == "selected":
            selected_ids = set(payload.item_ids or [])
            items = [item for item in items if item.id in selected_ids]

        approved_count = 0
        skipped_count = 0
        ignored_count = 0
        deferred_count = 0

        for item in items:
            if item.review_decision == ReviewDecision.IGNORED:
                ignored_count += 1
                continue
            if item.review_decision == ReviewDecision.DEFERRED:
                deferred_count += 1
                continue

            if payload.scope == "matched":
                if item.status != MediaItemStatus.MATCHED:
                    skipped_count += 1
                    continue
                if item.tmdb_id is None or item.needs_review:
                    skipped_count += 1
                    continue
            elif item.status != MediaItemStatus.MATCHED:
                skipped_count += 1
                continue

            if item.review_decision == ReviewDecision.APPROVED:
                skipped_count += 1
                continue

            await self._approve_item(item, note="Bulk approved")
            approved_count += 1

        await self.session.commit()
        return BulkReviewResult(
            approved_count=approved_count,
            skipped_count=skipped_count,
            ignored_count=ignored_count,
            deferred_count=deferred_count,
        )

    async def bulk_decision(self, session_id: int, payload: BulkReviewDecisionRequest) -> BulkReviewResult:
        await self.scan_sessions.get_scan_session(session_id)

        decision = ReviewDecision(payload.decision)
        if decision == ReviewDecision.MANUAL_OVERRIDE:
            raise BulkReviewError("manual_override is not allowed via bulk endpoint")

        approved_count = 0
        skipped_count = 0
        ignored_count = 0
        deferred_count = 0

        for item_id in payload.item_ids:
            item = await self.media_items.get_by_id(item_id)
            if item is None or item.scan_session_id != session_id:
                skipped_count += 1
                continue

            await ItemReviewService(self.session)._apply_decision_fields(
                item,
                ReviewDecisionRequest(decision=decision, note=payload.note),
            )

            if decision == ReviewDecision.APPROVED:
                approved_count += 1
            elif decision == ReviewDecision.IGNORED:
                ignored_count += 1
            elif decision == ReviewDecision.DEFERRED:
                deferred_count += 1

        await self.session.commit()
        return BulkReviewResult(
            approved_count=approved_count,
            skipped_count=skipped_count,
            ignored_count=ignored_count,
            deferred_count=deferred_count,
        )

    async def _approve_item(self, item: MediaItem, note: str) -> None:
        item.review_decision = ReviewDecision.APPROVED.value
        item.reviewed_at = datetime.now(UTC)
        item.review_note = note
        if item.status == MediaItemStatus.MATCHED:
            item.needs_review = False
        video_file = await self.media_files.get_video_for_media_item(item.id)
        await self.processed_media.record_from_item(item, video_file, session_id=item.scan_session_id)
