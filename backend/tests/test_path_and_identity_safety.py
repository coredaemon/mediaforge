from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.models.enums import OperationStatus, OperationType
from backend.app.models.plan_operation import PlanOperation
from backend.app.utils.file_identity import build_file_identity_key
from backend.app.utils.path_limits import path_length_error
from backend.app.utils.plan_operations import dedupe_operations
from backend.app.utils.target_paths import (
    build_movie_folder_path,
    build_tv_show_folder_path_direct,
    build_tv_video_path_direct,
    sanitize_path_segment,
)


# --- sanitize_path_segment -------------------------------------------------


@pytest.mark.parametrize("name", ["...", "..", "   ", ".", " . . "])
def test_sanitize_never_returns_an_empty_segment(name: str) -> None:
    """An empty segment silently collapses out of the path."""
    assert sanitize_path_segment(name) != ""


def test_title_that_sanitizes_away_does_not_collapse_into_the_library_root() -> None:
    root = Path("/library")

    show_folder = build_tv_show_folder_path_direct(root, "...", None)
    video = build_tv_video_path_direct(root, "...", 1, 1, ".mkv")
    movie_folder = build_movie_folder_path(root, "..", 2020)

    assert show_folder != root
    assert show_folder.parent == root
    assert video.parent.parent == show_folder
    assert movie_folder.parent == root


@pytest.mark.parametrize("name", ["CON", "aux", "NUL", "COM1", "LPT9", "con.mkv"])
def test_sanitize_escapes_reserved_windows_device_names(name: str) -> None:
    sanitized = sanitize_path_segment(name)
    assert sanitized.split(".")[0].upper() not in {
        "CON", "PRN", "AUX", "NUL", "COM1", "LPT9",
    }


def test_sanitize_strips_control_characters() -> None:
    assert "\x00" not in sanitize_path_segment("Title\x00bad")
    assert "\n" not in sanitize_path_segment("Two\nLines")


def test_sanitize_keeps_ordinary_titles_untouched() -> None:
    assert sanitize_path_segment("Матрица") == "Матрица"
    assert sanitize_path_segment("The Matrix") == "The Matrix"
    assert sanitize_path_segment("Bad: Movie*Name?") == "Bad_ Movie_Name_"
    assert sanitize_path_segment("Contact") == "Contact"


# --- file identity keys ----------------------------------------------------


def test_identity_key_is_stable_across_naive_and_aware_datetimes() -> None:
    """SQLite returns naive datetimes, the scanner produces aware ones.

    Reading the naive value as local time would shift the key by the UTC offset
    and silently invalidate every remembered file.
    """
    aware = datetime.fromtimestamp(1_700_000_000, UTC)
    naive = aware.replace(tzinfo=None)

    common = {"path": "/x/f.mkv", "file_name": "f.mkv", "size_bytes": 10}
    assert build_file_identity_key(**common, modified_at=aware) == build_file_identity_key(
        **common, modified_at=naive
    )


def test_identity_key_still_separates_different_mtimes() -> None:
    common = {"path": "/x/f.mkv", "file_name": "f.mkv", "size_bytes": 10}
    first = datetime.fromtimestamp(1_700_000_000, UTC)
    second = first + timedelta(seconds=5)

    assert build_file_identity_key(**common, modified_at=first) != build_file_identity_key(
        **common, modified_at=second
    )


def test_identity_key_respects_a_real_timezone_offset() -> None:
    """The same instant expressed in another zone must key identically."""
    utc = datetime.fromtimestamp(1_700_000_000, UTC)
    shifted = utc.astimezone(tz=None)

    common = {"path": "/x/f.mkv", "file_name": "f.mkv", "size_bytes": 10}
    assert build_file_identity_key(**common, modified_at=utc) == build_file_identity_key(
        **common, modified_at=shifted
    )


# --- path length -----------------------------------------------------------


def test_short_paths_are_never_rejected() -> None:
    assert path_length_error(str(Path("/library/Show (2024)/Season 01/x.mkv"))) is None


def test_path_length_error_is_platform_consistent() -> None:
    """Either the platform has no limit, or an over-limit path is reported."""
    from backend.app.utils.path_limits import max_path_length

    long_path = "C:\\library\\" + ("x" * 400) + ".mkv"
    if max_path_length() is None:
        assert path_length_error(long_path) is None
    else:
        assert "over the" in (path_length_error(long_path) or "")


def test_over_limit_path_is_reported_when_a_limit_applies(monkeypatch) -> None:
    """Force the constrained branch: most dev machines allow long paths."""
    from backend.app.utils import path_limits

    monkeypatch.setattr(path_limits, "max_path_length", lambda **_: 260)

    assert path_limits.path_length_error("C:\\lib\\" + "x" * 300) is not None
    assert path_limits.path_length_error("C:\\lib\\short.mkv") is None


@pytest.mark.asyncio
async def test_validation_blocks_a_plan_whose_target_is_too_long(monkeypatch, db_session, tmp_path) -> None:
    """An over-limit target must be caught by dry-run, not by a failing apply."""
    from backend.app.models.enums import PlanStatus, ValidationStatus
    from backend.app.models.operation_plan import OperationPlan
    from backend.app.models.scan_session import ScanSession
    from backend.app.services import plan_validation_service

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "a.mkv").write_text("video")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    plan = OperationPlan(scan_session_id=scan_session.id, status=PlanStatus.READY)
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        PlanOperation(
            plan_id=plan.id,
            operation_type=OperationType.MOVE_FILE,
            status=OperationStatus.PENDING,
            source_path=str(source / "a.mkv"),
            target_path=str(target / ("d" * 300) / "a.mkv"),
            payload_json={},
        )
    )
    await db_session.commit()

    monkeypatch.setattr(plan_validation_service, "path_length_error", lambda path, **_: (
        f"Path is {len(path)} characters, over the 260-character Windows limit: {path}."
        if len(path) >= 260
        else None
    ))

    result = await plan_validation_service.PlanValidationService(db_session).validate_plan(plan.id)

    assert result.conflict_count == 1
    assert result.operations[0].validation_status == ValidationStatus.CONFLICT
    assert "over the 260-character" in (result.operations[0].validation_error or "")


# --- episode NFO sidecar path ----------------------------------------------


def test_sidecar_nfo_sits_next_to_the_video() -> None:
    from backend.app.services.tv_planning_service import _sidecar_nfo_path

    video = Path("/lib/Show - S01E01 - Pilot.mkv")
    assert _sidecar_nfo_path(video, ".mkv") == Path("/lib/Show - S01E01 - Pilot.nfo")


def test_sidecar_nfo_keeps_a_dotted_title_on_an_extensionless_file() -> None:
    """with_suffix would eat ". 2" here and write the NFO under a truncated name."""
    from backend.app.services.tv_planning_service import _sidecar_nfo_path

    video = Path("/lib/Show - S01E01 - Vol. 2")
    assert _sidecar_nfo_path(video, "") == Path("/lib/Show - S01E01 - Vol. 2.nfo")


def test_sidecar_nfo_handles_a_dotted_title_with_an_extension() -> None:
    from backend.app.services.tv_planning_service import _sidecar_nfo_path

    video = Path("/lib/Show - S01E01 - Vol. 2.mkv")
    assert _sidecar_nfo_path(video, ".mkv") == Path("/lib/Show - S01E01 - Vol. 2.nfo")


# --- plan operation dedup --------------------------------------------------


def _operation(op_type: OperationType, source: str | None, target: str) -> PlanOperation:
    return PlanOperation(
        operation_type=op_type,
        status=OperationStatus.PENDING,
        source_path=source,
        target_path=target,
        payload_json={},
    )


def test_dedupe_drops_verbatim_repeats() -> None:
    operations = [
        _operation(OperationType.CREATE_DIR, None, "/lib/Show"),
        _operation(OperationType.DOWNLOAD_FILE, "https://img/p.jpg", "/lib/Show/poster.jpg"),
        _operation(OperationType.CREATE_DIR, None, "/lib/Show"),
        _operation(OperationType.DOWNLOAD_FILE, "https://img/p.jpg", "/lib/Show/poster.jpg"),
    ]

    unique = dedupe_operations(operations)

    assert len(unique) == 2
    assert [op.target_path for op in unique] == ["/lib/Show", "/lib/Show/poster.jpg"]


def test_dedupe_keeps_real_collisions_for_validation_to_report() -> None:
    """Same target, different source is a genuine conflict, not a repeat."""
    operations = [
        _operation(OperationType.MOVE_FILE, "/in/a.mkv", "/lib/Show/S01E01.mkv"),
        _operation(OperationType.MOVE_FILE, "/in/b.mkv", "/lib/Show/S01E01.mkv"),
    ]

    assert len(dedupe_operations(operations)) == 2


def test_dedupe_preserves_order() -> None:
    operations = [
        _operation(OperationType.CREATE_DIR, None, "/lib/A"),
        _operation(OperationType.CREATE_DIR, None, "/lib/B"),
        _operation(OperationType.CREATE_DIR, None, "/lib/A"),
        _operation(OperationType.CREATE_DIR, None, "/lib/C"),
    ]

    assert [op.target_path for op in dedupe_operations(operations)] == ["/lib/A", "/lib/B", "/lib/C"]
