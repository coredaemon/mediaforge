from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_item import MediaItem
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTmdbClient


async def test_tmdb_matching_auto_selects_high_confidence_movie(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.DISCOVERED,
            parsed_title="The Matrix",
            year=1999,
            needs_review=False,
        )
    )
    await db_session.commit()
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(tmdb_id=603, media_type="movie", title="The Matrix", year=1999, popularity=80)
        ]
    )

    result = await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)
    candidates = await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id)

    assert result.matched_count == 1
    assert refreshed is not None
    assert refreshed.status == MediaItemStatus.MATCHED
    assert refreshed.tmdb_id == 603
    assert refreshed.tmdb_media_type == "movie"
    assert refreshed.matched_title == "The Matrix"
    assert refreshed.matched_year == 1999
    assert candidates[0].is_selected


async def test_tmdb_matching_auto_selects_tv_episode_at_show_level(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.TV_EPISODE,
            status=MediaItemStatus.DISCOVERED,
            parsed_title="Hannibal",
            season_number=1,
            episode_number=1,
            needs_review=False,
        )
    )
    await db_session.commit()
    fake_client = FakeTmdbClient(
        tv_results=[TmdbSearchResult(tmdb_id=40008, media_type="tv", title="Hannibal", year=2013, popularity=60)]
    )

    result = await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)

    assert result.matched_count == 1
    assert refreshed is not None
    assert refreshed.status == MediaItemStatus.MATCHED
    assert refreshed.tmdb_id == 40008
    assert refreshed.tmdb_media_type == "tv"


async def test_tmdb_matching_marks_item_unmatched_when_no_candidates(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.DISCOVERED,
            parsed_title="No Such Movie",
            needs_review=False,
        )
    )
    await db_session.commit()

    result = await TMDBService(db_session, client=FakeTmdbClient()).match_scan_session(scan_session.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)

    assert result.unmatched_count == 1
    assert refreshed is not None
    assert refreshed.status == MediaItemStatus.UNMATCHED
    assert refreshed.needs_review


async def test_tmdb_matching_does_not_duplicate_candidates_on_force_rematch(
    db_session: AsyncSession,
    tmp_path,
) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.DISCOVERED,
            parsed_title="The Matrix",
            year=1999,
            needs_review=False,
        )
    )
    await db_session.commit()
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(tmdb_id=603, media_type="movie", title="The Matrix", year=1999),
            TmdbSearchResult(tmdb_id=604, media_type="movie", title="The Matrix Reloaded", year=2003),
        ]
    )

    await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id, force=True)
    candidates = await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id)

    assert len(candidates) == 2
