import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType, ReviewDecision
from backend.app.models.media_item import MediaItem
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.schemas.review import BulkApproveRequest, BulkReviewDecisionRequest
from backend.app.services.bulk_review_service import BulkReviewService
from backend.app.services.scan_session_service import ScanSessionService


async def _create_session_with_items(db_session: AsyncSession, tmp_path) -> tuple[int, list[MediaItem]]:
    scan_session = await ScanSessionService(db_session).create_scan_session(
        str(tmp_path / "in"),
        str(tmp_path / "out"),
    )
    repo = MediaItemRepository(db_session)
    items = [
        await repo.create(
            MediaItem(
                scan_session_id=scan_session.id,
                media_type=MediaType.MOVIE,
                status=MediaItemStatus.MATCHED,
                parsed_title="Matrix",
                matched_title="The Matrix",
                matched_year=1999,
                tmdb_id=603,
                needs_review=False,
                review_decision=ReviewDecision.PENDING,
            )
        ),
        await repo.create(
            MediaItem(
                scan_session_id=scan_session.id,
                media_type=MediaType.MOVIE,
                status=MediaItemStatus.MATCHED,
                parsed_title="Ignored",
                tmdb_id=1,
                needs_review=False,
                review_decision=ReviewDecision.IGNORED,
            )
        ),
        await repo.create(
            MediaItem(
                scan_session_id=scan_session.id,
                media_type=MediaType.MOVIE,
                status=MediaItemStatus.MATCHED,
                parsed_title="Deferred",
                tmdb_id=2,
                needs_review=False,
                review_decision=ReviewDecision.DEFERRED,
            )
        ),
        await repo.create(
            MediaItem(
                scan_session_id=scan_session.id,
                media_type=MediaType.MOVIE,
                status=MediaItemStatus.MATCHED,
                parsed_title="Needs review",
                needs_review=True,
                review_decision=ReviewDecision.PENDING,
            )
        ),
    ]
    await db_session.commit()
    return scan_session.id, items


async def test_approve_all_matched_approves_eligible_items(db_session: AsyncSession, tmp_path) -> None:
    session_id, items = await _create_session_with_items(db_session, tmp_path)
    result = await BulkReviewService(db_session).approve_all(
        session_id,
        BulkApproveRequest(scope="matched"),
    )
    assert result.approved_count == 1
    assert result.skipped_count == 1
    assert result.ignored_count == 1
    assert result.deferred_count == 1

    refreshed = await MediaItemRepository(db_session).get_by_id(items[0].id)
    assert refreshed is not None
    assert refreshed.review_decision == ReviewDecision.APPROVED
    assert refreshed.review_note == "Bulk approved"


async def test_approve_all_skips_ignored_and_deferred(db_session: AsyncSession, tmp_path) -> None:
    session_id, items = await _create_session_with_items(db_session, tmp_path)
    await BulkReviewService(db_session).approve_all(session_id, BulkApproveRequest(scope="matched"))

    ignored = await MediaItemRepository(db_session).get_by_id(items[1].id)
    deferred = await MediaItemRepository(db_session).get_by_id(items[2].id)
    assert ignored is not None and ignored.review_decision == ReviewDecision.IGNORED
    assert deferred is not None and deferred.review_decision == ReviewDecision.DEFERRED


async def test_bulk_decision_ignored_updates_selected_items(db_session: AsyncSession, tmp_path) -> None:
    session_id, items = await _create_session_with_items(db_session, tmp_path)
    result = await BulkReviewService(db_session).bulk_decision(
        session_id,
        BulkReviewDecisionRequest(item_ids=[items[0].id], decision="ignored", note="Не добавлять"),
    )
    assert result.ignored_count == 1
    refreshed = await MediaItemRepository(db_session).get_by_id(items[0].id)
    assert refreshed is not None
    assert refreshed.review_decision == ReviewDecision.IGNORED
    assert refreshed.status == MediaItemStatus.IGNORED


async def test_bulk_decision_deferred_updates_selected_items(db_session: AsyncSession, tmp_path) -> None:
    session_id, items = await _create_session_with_items(db_session, tmp_path)
    result = await BulkReviewService(db_session).bulk_decision(
        session_id,
        BulkReviewDecisionRequest(item_ids=[items[0].id], decision="deferred", note="Отложено"),
    )
    assert result.deferred_count == 1
    refreshed = await MediaItemRepository(db_session).get_by_id(items[0].id)
    assert refreshed is not None
    assert refreshed.review_decision == ReviewDecision.DEFERRED


async def test_bulk_decision_rejects_manual_override(db_session: AsyncSession, tmp_path) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BulkReviewDecisionRequest(item_ids=[1], decision="manual_override")  # type: ignore[arg-type]
