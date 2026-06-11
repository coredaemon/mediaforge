from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.main import app
from backend.app.models.enums import MediaItemStatus, OperationType, PlanStatus
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.operation_plan_repository import OperationPlanRepository
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.parser_service import ParserService
from backend.app.services.planning_service import NoMatchedItemsError, PlanningService
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTmdbClient


async def _prepare_matched_session(db_session: AsyncSession, tmp_path: Path) -> int:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    matrix_source = source_path / "The.Matrix.1999.mkv"
    hannibal_source = source_path / "Hannibal.S01E01.mkv"
    matrix_source.write_bytes(b"movie")
    hannibal_source.write_bytes(b"episode")

    from backend.app.services.scan_session_service import ScanSessionService

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)

    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                poster_path="/matrix-poster.jpg",
                backdrop_path="/matrix-backdrop.jpg",
            )
        ],
        tv_results=[
            TmdbSearchResult(
                tmdb_id=40008,
                media_type="tv",
                title="Hannibal",
                year=2013,
                popularity=60,
                poster_path="/hannibal-poster.jpg",
            )
        ],
    )
    await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    return scan_session.id


async def test_planning_service_creates_dry_run_operations_without_touching_files(
    db_session: AsyncSession,
    tmp_path,
) -> None:
    session_id = await _prepare_matched_session(db_session, tmp_path)
    source_path = tmp_path / "inbox"
    target_path = tmp_path / "library"
    matrix_source = source_path / "The.Matrix.1999.mkv"
    hannibal_source = source_path / "Hannibal.S01E01.mkv"

    plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    operation_types = {operation.operation_type for operation in operations}
    move_operations = [operation for operation in operations if operation.operation_type == OperationType.MOVE_FILE]

    assert plan.status == PlanStatus.READY
    assert OperationType.CREATE_DIR in operation_types
    assert OperationType.MOVE_FILE in operation_types
    assert OperationType.WRITE_TEXT_FILE in operation_types
    assert OperationType.DOWNLOAD_FILE in operation_types
    assert matrix_source.exists()
    assert hannibal_source.exists()
    assert not (target_path / "TV Shows").exists()
    matrix_source_resolved = str(matrix_source.resolve())
    assert any(operation.source_path == matrix_source_resolved for operation in move_operations)
    assert any(
        Path(operation.target_path).as_posix().endswith("The Matrix (1999)/The Matrix (1999).mkv")
        for operation in move_operations
    )
    assert any(
        Path(operation.target_path).as_posix().endswith("The Matrix (1999)/movie.nfo")
        for operation in operations
        if operation.operation_type == OperationType.WRITE_TEXT_FILE
    )
    assert any(
        Path(operation.target_path).as_posix().endswith("The Matrix (1999)/poster.jpg")
        for operation in operations
        if operation.operation_type == OperationType.DOWNLOAD_FILE
    )
    assert any(
        Path(operation.target_path).as_posix().endswith("The Matrix (1999)/fanart.jpg")
        for operation in operations
        if operation.operation_type == OperationType.DOWNLOAD_FILE
    )
    assert any(
        Path(operation.target_path).as_posix().endswith("TV Shows/Hannibal/Season 01/Hannibal S01E01.mkv")
        for operation in move_operations
    )


async def test_planning_service_returns_existing_plan_without_force(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _prepare_matched_session(db_session, tmp_path)

    first_plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    second_plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)

    assert first_plan.id == second_plan.id


async def test_planning_service_replaces_plan_when_force_is_true(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _prepare_matched_session(db_session, tmp_path)

    first_plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    first_operations = await PlanOperationRepository(db_session).list_by_plan(first_plan.id)
    second_plan = await PlanningService(db_session).create_plan_for_scan_session(session_id, force=True)
    second_operations = await PlanOperationRepository(db_session).list_by_plan(second_plan.id)
    plans = await OperationPlanRepository(db_session).list_by_scan_session(session_id)

    assert len(plans) == 1
    assert len(first_operations) > 0
    assert len(second_operations) == len(first_operations)


async def test_planning_service_raises_when_no_matched_items(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()

    from backend.app.services.scan_session_service import ScanSessionService

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await db_session.commit()

    with pytest.raises(NoMatchedItemsError):
        await PlanningService(db_session).create_plan_for_scan_session(scan_session.id)


async def test_planning_service_skips_items_without_required_metadata(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "Broken.Movie.mkv").write_bytes(b"movie")

    from backend.app.services.scan_session_service import ScanSessionService

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)

    item = (await MediaItemRepository(db_session).list_by_scan_session(scan_session.id))[0]
    item.status = MediaItemStatus.MATCHED
    item.matched_title = "Broken Movie"
    item.matched_year = None
    await db_session.commit()

    with pytest.raises(NoMatchedItemsError):
        await PlanningService(db_session).create_plan_for_scan_session(scan_session.id)
