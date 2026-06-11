from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import OperationStatus, OperationType, PlanStatus, ReviewDecision
from ..models.media_file import MediaFile
from ..models.operation_plan import OperationPlan
from ..models.plan_operation import PlanOperation
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.operation_plan_repository import OperationPlanRepository
from ..repositories.plan_operation_repository import PlanOperationRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..repositories.tv_repository import TvRepository
from ..schemas.operation_plan import OperationPlanRead
from ..utils.paths import normalize_path
from ..utils.target_paths import (
    build_tv_season_folder_path_direct,
    build_tv_show_folder_path_direct,
    build_tv_video_path_direct,
    tmdb_image_download_url,
)
from .planning_service import NoMatchedItemsError
from .scan_session_service import ScanSessionNotFoundError


class TvPlanningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.tv = TvRepository(session)
        self.media_files = MediaFileRepository(session)
        self.operation_plans = OperationPlanRepository(session)
        self.plan_operations = PlanOperationRepository(session)

    async def create_plan_for_scan_session(self, session_id: int, force: bool = False) -> OperationPlanRead:
        scan_session = await self.scan_sessions.get(session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {session_id} was not found.")

        existing_plan = await self.operation_plans.get_latest_by_scan_session(session_id)
        if existing_plan is not None and existing_plan.status in {PlanStatus.DRAFT, PlanStatus.READY}:
            if not force:
                return OperationPlanRead.model_validate(existing_plan)
            await self.operation_plans.delete_draft_or_ready_for_scan_session(session_id)
            await self.session.flush()

        target_root = normalize_path(scan_session.target_path)
        shows = [
            show
            for show in await self.tv.list_shows(session_id)
            if show.review_decision not in {ReviewDecision.IGNORED, ReviewDecision.DEFERRED}
        ]
        if not shows:
            raise NoMatchedItemsError(f"Scan session {session_id} has no TV shows to plan.")

        plan = await self.operation_plans.create(OperationPlan(scan_session_id=session_id, status=PlanStatus.DRAFT))
        count = 0
        for show in shows:
            if show.needs_review:
                continue
            operations = await self._build_operations_for_show(show, target_root)
            for operation in operations:
                operation.plan_id = plan.id
                await self.plan_operations.create(operation)
            if operations:
                count += 1
        if count == 0:
            await self.operation_plans.delete(plan)
            await self.session.flush()
            raise NoMatchedItemsError("No approved TV shows could be planned.")
        plan.status = PlanStatus.READY
        await self.session.commit()
        await self.session.refresh(plan)
        return OperationPlanRead.model_validate(plan)

    async def _build_operations_for_show(self, show, target_root: Path) -> list[PlanOperation]:
        show_folder = build_tv_show_folder_path_direct(target_root, show.title, show.year)
        operations = [
            _create_dir(show_folder, show.id),
            _write_text(show_folder / "tvshow.nfo", {"tv_show_id": show.id, "nfo_type": "tvshow", "tv_apply_disabled": True}),
        ]
        if show.poster_path:
            operations.append(_download(show.poster_path, show_folder / "poster.jpg", show.id, "poster"))
        if show.backdrop_path:
            operations.append(_download(show.backdrop_path, show_folder / "fanart.jpg", show.id, "backdrop"))
        seasons = await self.tv.list_seasons(show.id)
        for season in seasons:
            season_folder = build_tv_season_folder_path_direct(target_root, show.title, season.season_number, show.year)
            operations.append(_create_dir(season_folder, show.id))
            if season.poster_path:
                operations.append(_download(season.poster_path, season_folder / "poster.jpg", show.id, "season_poster"))
        for episode in await self.tv.list_episodes(show.id):
            if episode.needs_review or not episode.source_file_id:
                continue
            media_file = await self.session.get(MediaFile, episode.source_file_id)
            if media_file is None:
                continue
            extension = Path(media_file.path).suffix or media_file.extension
            target_video = build_tv_video_path_direct(
                target_root,
                show.title,
                episode.season_number,
                episode.episode_number,
                extension,
                year=show.year,
                episode_title=episode.title,
            )
            episode.target_path = str(target_video)
            operations.append(
                PlanOperation(
                    operation_type=OperationType.MOVE_FILE,
                    status=OperationStatus.PENDING,
                    source_path=media_file.path,
                    target_path=str(target_video),
                    payload_json={"tv_show_id": show.id, "tv_episode_id": episode.id, "tv_apply_disabled": True},
                )
            )
            operations.append(
                _write_text(
                    target_video.with_suffix(".nfo"),
                    {"tv_show_id": show.id, "tv_episode_id": episode.id, "nfo_type": "episode", "tv_apply_disabled": True},
                )
            )
        return operations


def _create_dir(path: Path, show_id: int) -> PlanOperation:
    return PlanOperation(
        operation_type=OperationType.CREATE_DIR,
        status=OperationStatus.PENDING,
        target_path=str(path),
        payload_json={"tv_show_id": show_id, "tv_apply_disabled": True},
    )


def _write_text(path: Path, payload: dict) -> PlanOperation:
    return PlanOperation(
        operation_type=OperationType.WRITE_TEXT_FILE,
        status=OperationStatus.PENDING,
        target_path=str(path),
        payload_json=payload,
    )


def _download(tmdb_path: str, path: Path, show_id: int, asset_type: str) -> PlanOperation:
    return PlanOperation(
        operation_type=OperationType.DOWNLOAD_FILE,
        status=OperationStatus.PENDING,
        source_path=tmdb_image_download_url(tmdb_path),
        target_path=str(path),
        payload_json={"tv_show_id": show_id, "asset_type": asset_type, "tmdb_path": tmdb_path, "tv_apply_disabled": True},
    )
