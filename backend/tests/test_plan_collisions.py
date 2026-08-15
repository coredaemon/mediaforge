from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.models.enums import MediaFileKind, OperationType, PlanStatus, ValidationStatus
from backend.app.models.media_file import MediaFile
from backend.app.models.scan_session import ScanSession
from backend.app.models.tv_episode import TvEpisode
from backend.app.models.tv_season import TvSeason
from backend.app.models.tv_show import TvShow
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.services.apply_service import ApplyService
from backend.app.services.plan_validation_service import PlanValidationService
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tv_planning_service import TvPlanningService


async def _session_with_two_files_for_one_episode(db_session, tmp_path: Path) -> ScanSession:
    """A show whose grouping puts two different files on the same episode number.

    A 1080p and a 720p rip of the same episode is the everyday version of this.
    """
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show").mkdir(parents=True)
    target.mkdir()
    (source / "Show" / "Show S01E01 1080p.mkv").write_text("video-a")
    (source / "Show" / "Show S01E01 720p.mkv").write_text("video-b")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)

    files = (
        await db_session.execute(
            select(MediaFile).where(
                MediaFile.scan_session_id == scan_session.id,
                MediaFile.kind == MediaFileKind.VIDEO,
            )
        )
    ).scalars().all()

    show = TvShow(
        scan_session_id=scan_session.id,
        title="Show",
        year=2024,
        tmdb_id=1,
        needs_review=False,
        confidence=0.99,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    for media_file in sorted(files, key=lambda f: f.file_name):
        db_session.add(
            TvEpisode(
                show_id=show.id,
                season_id=season.id,
                source_file_id=media_file.id,
                season_number=1,
                episode_number=1,
                title="Pilot",
                source_path=media_file.path,
                needs_review=False,
            )
        )
    await db_session.commit()
    return scan_session


@pytest.mark.asyncio
async def test_validation_flags_two_operations_writing_the_same_target(db_session, tmp_path: Path) -> None:
    scan_session = await _session_with_two_files_for_one_episode(db_session, tmp_path)
    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)

    result = await PlanValidationService(db_session).validate_plan(plan.id)

    assert result.conflict_count > 0, "colliding targets must be reported before apply"
    conflicts = [op for op in result.operations if op.validation_status == ValidationStatus.CONFLICT]
    assert any("write the same target" in (op.validation_error or "") for op in conflicts)


@pytest.mark.asyncio
async def test_colliding_plan_cannot_be_applied(db_session, tmp_path: Path) -> None:
    """The dry-run contract: a plan that would fail halfway never starts."""
    scan_session = await _session_with_two_files_for_one_episode(db_session, tmp_path)
    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    source = tmp_path / "source"
    target = tmp_path / "target"

    from backend.app.services.apply_service import PlanApplyError

    with pytest.raises(PlanApplyError, match="conflict"):
        await ApplyService(db_session).apply_plan(plan.id, confirm=True)

    # Nothing may have moved: both source files are still where they started.
    assert sorted(p.name for p in source.rglob("*") if p.is_file()) == [
        "Show S01E01 1080p.mkv",
        "Show S01E01 720p.mkv",
    ]
    assert [p for p in target.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_validation_flags_two_moves_of_the_same_source(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show").mkdir(parents=True)
    target.mkdir()
    (source / "Show" / "Show S01E01.mkv").write_text("video")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    media_file = (
        await db_session.execute(
            select(MediaFile).where(MediaFile.kind == MediaFileKind.VIDEO)
        )
    ).scalars().one()

    show = TvShow(
        scan_session_id=scan_session.id, title="Show", year=2024,
        tmdb_id=1, needs_review=False, confidence=0.99,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    # One file claimed by two different episode numbers.
    for episode_number in (1, 2):
        db_session.add(
            TvEpisode(
                show_id=show.id, season_id=season.id, source_file_id=media_file.id,
                season_number=1, episode_number=episode_number, title=f"E{episode_number}",
                source_path=media_file.path, needs_review=False,
            )
        )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    result = await PlanValidationService(db_session).validate_plan(plan.id)

    assert result.conflict_count > 0
    assert any(
        "move the same source" in (op.validation_error or "") for op in result.operations
    )


@pytest.mark.asyncio
async def test_clean_tv_plan_still_validates_without_conflicts(db_session, tmp_path: Path) -> None:
    """Guard against the collision check firing on legitimate plans."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show").mkdir(parents=True)
    target.mkdir()
    (source / "Show" / "Show S01E01.mkv").write_text("a")
    (source / "Show" / "Show S01E02.mkv").write_text("b")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    files = (
        await db_session.execute(
            select(MediaFile).where(MediaFile.kind == MediaFileKind.VIDEO)
        )
    ).scalars().all()

    show = TvShow(
        scan_session_id=scan_session.id, title="Show", year=2024,
        tmdb_id=1, needs_review=False, confidence=0.99,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    for index, media_file in enumerate(sorted(files, key=lambda f: f.file_name), start=1):
        db_session.add(
            TvEpisode(
                show_id=show.id, season_id=season.id, source_file_id=media_file.id,
                season_number=1, episode_number=index, title=f"Episode {index}",
                source_path=media_file.path, needs_review=False,
            )
        )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    result = await PlanValidationService(db_session).validate_plan(plan.id)

    assert result.conflict_count == 0
    apply_result = await ApplyService(db_session).apply_plan(plan.id, confirm=True)
    assert apply_result.status == PlanStatus.APPLIED
    assert (target / "Show (2024)" / "Season 01" / "Show - S01E01 - Episode 1.mkv").is_file()
    assert (target / "Show (2024)" / "Season 01" / "Show - S01E02 - Episode 2.mkv").is_file()


@pytest.mark.asyncio
async def test_second_apply_of_the_same_plan_is_refused(db_session, tmp_path: Path) -> None:
    """Only one apply run may ever own a plan, or the same files move twice."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show").mkdir(parents=True)
    target.mkdir()
    (source / "Show" / "Show S01E01.mkv").write_text("video")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    media_file = (
        await db_session.execute(select(MediaFile).where(MediaFile.kind == MediaFileKind.VIDEO))
    ).scalars().one()

    show = TvShow(
        scan_session_id=scan_session.id, title="Show", year=2024,
        tmdb_id=1, needs_review=False, confidence=0.99,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id, season_id=season.id, source_file_id=media_file.id,
            season_number=1, episode_number=1, title="Pilot",
            source_path=media_file.path, needs_review=False,
        )
    )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    service = ApplyService(db_session)

    first = await service.start_apply(plan.id, confirm=True)
    assert first.apply_run_id is not None

    from backend.app.services.apply_service import PlanApplyError

    with pytest.raises(PlanApplyError) as excinfo:
        await service.start_apply(plan.id, confirm=True)
    assert excinfo.value.error_code == "apply_in_progress"


@pytest.mark.asyncio
async def test_plan_does_not_repeat_shared_folder_operations(db_session, tmp_path: Path) -> None:
    """Show-level artwork and folders are emitted once, not once per episode."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show").mkdir(parents=True)
    target.mkdir()
    for index in (1, 2, 3):
        (source / "Show" / f"Show S01E0{index}.mkv").write_text("video")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    files = (
        await db_session.execute(
            select(MediaFile).where(MediaFile.kind == MediaFileKind.VIDEO)
        )
    ).scalars().all()

    show = TvShow(
        scan_session_id=scan_session.id, title="Show", year=2024, tmdb_id=1,
        needs_review=False, confidence=0.99,
        poster_path="/poster.jpg", backdrop_path="/backdrop.jpg",
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    for index, media_file in enumerate(sorted(files, key=lambda f: f.file_name), start=1):
        db_session.add(
            TvEpisode(
                show_id=show.id, season_id=season.id, source_file_id=media_file.id,
                season_number=1, episode_number=index, title=f"Episode {index}",
                source_path=media_file.path, needs_review=False,
            )
        )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)

    repeated = {
        target_path: count
        for target_path, count in Counter(
            operation.target_path
            for operation in operations
            if operation.operation_type != OperationType.CREATE_DIR
        ).items()
        if count > 1
    }
    assert not repeated, f"plan repeats operations: {repeated}"
