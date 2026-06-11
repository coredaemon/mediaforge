from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind, MediaItemStatus, MediaType, OperationStatus, OperationType, PlanStatus
from ..models.media_item import MediaItem
from ..models.operation_plan import OperationPlan
from ..models.plan_operation import PlanOperation
from ..models.tmdb_match_candidate import TmdbMatchCandidate
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.operation_plan_repository import OperationPlanRepository
from ..repositories.plan_operation_repository import PlanOperationRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ..schemas.operation_plan import OperationPlanRead
from ..utils.paths import normalize_path
from ..utils.target_paths import (
    build_movie_folder_path,
    build_movie_video_path,
    build_tv_season_folder_path,
    build_tv_show_folder_path,
    build_tv_video_path,
    tmdb_image_download_url,
)
from .scan_session_service import ScanSessionNotFoundError


class NoMatchedItemsError(ValueError):
    """Raised when a scan session has no matched media items to plan."""


class PlanAlreadyExistsError(ValueError):
    """Raised when a dry-run plan already exists and force is disabled."""


class OperationPlanNotFoundError(LookupError):
    """Raised when an operation plan id does not exist."""


class PlanningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_items = MediaItemRepository(session)
        self.media_files = MediaFileRepository(session)
        self.operation_plans = OperationPlanRepository(session)
        self.plan_operations = PlanOperationRepository(session)
        self.tmdb_candidates = TmdbMatchCandidateRepository(session)

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

        matched_items = await self.media_items.list_plannable_by_scan_session(session_id)
        if not matched_items:
            raise NoMatchedItemsError(f"Scan session {session_id} has no matched media items.")

        target_root = normalize_path(scan_session.target_path)
        plan = await self.operation_plans.create(
            OperationPlan(scan_session_id=session_id, status=PlanStatus.DRAFT)
        )

        planned_item_count = 0
        for item in matched_items:
            video_file = await self.media_files.get_video_for_media_item(item.id)
            if video_file is None:
                continue

            selected_candidate = await self.tmdb_candidates.get_selected_for_media_item(item.id)
            operations = self._build_operations_for_item(
                item=item,
                source_video_path=normalize_path(video_file.path),
                video_extension=video_file.extension,
                target_root=target_root,
                selected_candidate=selected_candidate,
            )
            if not operations:
                continue

            for operation in operations:
                operation.plan_id = plan.id
                await self.plan_operations.create(operation)
            planned_item_count += 1

        if planned_item_count == 0:
            await self.operation_plans.delete(plan)
            await self.session.flush()
            raise NoMatchedItemsError(
                f"Scan session {session_id} has matched items, but none could be planned with the current metadata."
            )

        plan.status = PlanStatus.READY
        await self.session.commit()
        await self.session.refresh(plan)
        return OperationPlanRead.model_validate(plan)

    async def get_operation_plan(self, plan_id: int) -> OperationPlan:
        plan = await self.operation_plans.get_by_id(plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {plan_id} was not found.")
        return plan

    async def list_plans_for_scan_session(self, session_id: int) -> list[OperationPlan]:
        scan_session = await self.scan_sessions.get(session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {session_id} was not found.")
        return list(await self.operation_plans.list_by_scan_session(session_id))

    async def list_plan_operations(self, plan_id: int) -> list[PlanOperation]:
        await self.get_operation_plan(plan_id)
        return list(await self.plan_operations.list_by_plan(plan_id))

    def _build_operations_for_item(
        self,
        item: MediaItem,
        source_video_path: Path,
        video_extension: str,
        target_root: Path,
        selected_candidate: TmdbMatchCandidate | None,
    ) -> list[PlanOperation]:
        if item.media_type == MediaType.MOVIE:
            return self._build_movie_operations(
                item=item,
                source_video_path=source_video_path,
                video_extension=video_extension,
                target_root=target_root,
                selected_candidate=selected_candidate,
            )
        if item.media_type == MediaType.TV_EPISODE:
            return self._build_tv_operations(
                item=item,
                source_video_path=source_video_path,
                video_extension=video_extension,
                target_root=target_root,
                selected_candidate=selected_candidate,
            )
        return []

    def _build_movie_operations(
        self,
        item: MediaItem,
        source_video_path: Path,
        video_extension: str,
        target_root: Path,
        selected_candidate: TmdbMatchCandidate | None,
    ) -> list[PlanOperation]:
        if item.matched_title is None or item.matched_year is None:
            return []

        target_folder = build_movie_folder_path(target_root, item.matched_title, item.matched_year)
        target_video_path = build_movie_video_path(
            target_root,
            item.matched_title,
            item.matched_year,
            video_extension,
        )
        operations = [
            self._create_dir_operation(target_folder, item.id),
            self._move_file_operation(source_video_path, target_video_path, item.id),
            self._write_nfo_operation(
                target_folder / "movie.nfo",
                {"media_item_id": item.id, "nfo_type": "movie"},
            ),
        ]
        operations.extend(
            self._download_artwork_operations(
                target_folder=target_folder,
                selected_candidate=selected_candidate,
                media_item_id=item.id,
            )
        )
        return operations

    def _build_tv_operations(
        self,
        item: MediaItem,
        source_video_path: Path,
        video_extension: str,
        target_root: Path,
        selected_candidate: TmdbMatchCandidate | None,
    ) -> list[PlanOperation]:
        if item.matched_title is None or item.season_number is None or item.episode_number is None:
            return []

        target_folder = build_tv_season_folder_path(target_root, item.matched_title, item.season_number)
        target_video_path = build_tv_video_path(
            target_root,
            item.matched_title,
            item.season_number,
            item.episode_number,
            video_extension,
        )
        show_folder = build_tv_show_folder_path(target_root, item.matched_title)
        operations = [
            self._create_dir_operation(target_folder, item.id),
            self._move_file_operation(source_video_path, target_video_path, item.id),
        ]
        operations.extend(
            self._download_artwork_operations(
                target_folder=show_folder,
                selected_candidate=selected_candidate,
                media_item_id=item.id,
            )
        )
        return operations

    def _download_artwork_operations(
        self,
        target_folder: Path,
        selected_candidate: TmdbMatchCandidate | None,
        media_item_id: int,
    ) -> list[PlanOperation]:
        if selected_candidate is None:
            return []

        operations: list[PlanOperation] = []
        if selected_candidate.poster_path:
            operations.append(
                PlanOperation(
                    operation_type=OperationType.DOWNLOAD_FILE,
                    status=OperationStatus.PENDING,
                    source_path=tmdb_image_download_url(selected_candidate.poster_path),
                    target_path=str(target_folder / "poster.jpg"),
                    payload_json={
                        "media_item_id": media_item_id,
                        "asset_type": "poster",
                        "tmdb_path": selected_candidate.poster_path,
                    },
                )
            )
        if selected_candidate.backdrop_path:
            operations.append(
                PlanOperation(
                    operation_type=OperationType.DOWNLOAD_FILE,
                    status=OperationStatus.PENDING,
                    source_path=tmdb_image_download_url(selected_candidate.backdrop_path),
                    target_path=str(target_folder / "fanart.jpg"),
                    payload_json={
                        "media_item_id": media_item_id,
                        "asset_type": "backdrop",
                        "tmdb_path": selected_candidate.backdrop_path,
                    },
                )
            )
        return operations

    def _create_dir_operation(self, target_folder: Path, media_item_id: int) -> PlanOperation:
        return PlanOperation(
            operation_type=OperationType.CREATE_DIR,
            status=OperationStatus.PENDING,
            target_path=str(target_folder),
            payload_json={"media_item_id": media_item_id},
        )

    def _move_file_operation(self, source_path: Path, target_path: Path, media_item_id: int) -> PlanOperation:
        return PlanOperation(
            operation_type=OperationType.MOVE_FILE,
            status=OperationStatus.PENDING,
            source_path=str(source_path),
            target_path=str(target_path),
            payload_json={"media_item_id": media_item_id},
        )

    def _write_nfo_operation(self, target_path: Path, payload: dict) -> PlanOperation:
        return PlanOperation(
            operation_type=OperationType.WRITE_TEXT_FILE,
            status=OperationStatus.PENDING,
            target_path=str(target_path),
            payload_json=payload,
        )
