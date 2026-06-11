from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_item import MediaItem
from backend.app.models.tmdb_match_candidate import TmdbMatchCandidate
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.tmdb_service import TMDBService


async def _create_item_with_candidates(db_session: AsyncSession, tmp_path):
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item_repo = MediaItemRepository(db_session)
    candidate_repo = TmdbMatchCandidateRepository(db_session)
    item = await item_repo.create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            parsed_title="Matrix",
            year=1999,
            needs_review=True,
        )
    )
    first = await candidate_repo.create(
        TmdbMatchCandidate(
            media_item_id=item.id,
            tmdb_id=603,
            media_type="movie",
            title="The Matrix",
            year=1999,
            score=0.91,
            is_selected=True,
        )
    )
    second = await candidate_repo.create(
        TmdbMatchCandidate(
            media_item_id=item.id,
            tmdb_id=604,
            media_type="movie",
            title="The Matrix Reloaded",
            year=2003,
            score=0.72,
            is_selected=False,
        )
    )
    await db_session.commit()
    return item, first, second


async def test_select_candidate_updates_media_item(db_session: AsyncSession, tmp_path) -> None:
    item, _, second = await _create_item_with_candidates(db_session, tmp_path)

    selected = await TMDBService(db_session).select_candidate(item.id, second.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)

    assert selected.is_selected
    assert refreshed is not None
    assert refreshed.tmdb_id == second.tmdb_id
    assert refreshed.tmdb_media_type == second.media_type
    assert refreshed.matched_title == second.title
    assert refreshed.matched_year == second.year
    assert refreshed.match_confidence == second.score
    assert refreshed.status == MediaItemStatus.MATCHED
    assert not refreshed.needs_review


async def test_select_candidate_clears_previous_selected_candidate(db_session: AsyncSession, tmp_path) -> None:
    item, first, second = await _create_item_with_candidates(db_session, tmp_path)

    await TMDBService(db_session).select_candidate(item.id, second.id)
    candidates = await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id)
    selected_ids = {candidate.id for candidate in candidates if candidate.is_selected}

    assert first.id not in selected_ids
    assert selected_ids == {second.id}
