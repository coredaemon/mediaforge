from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.session import async_session_factory
from ..models.apply_operation_log import ApplyOperationLog
from ..models.apply_run import ApplyRun
from ..models.enums import ApplyRunStatus, OperationStatus, OperationType, PlanStatus, ValidationStatus
from ..models.plan_operation import PlanOperation
from ..repositories.apply_run_repository import ApplyRunRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.operation_plan_repository import OperationPlanRepository
from ..repositories.plan_operation_repository import PlanOperationRepository
from ..schemas.operation_plan import ApplyRunRead, PlanApplyResult
from ..utils.nfo_builder import build_episode_nfo, build_movie_nfo, build_tvshow_nfo
from ..utils.path_safety import is_trusted_tmdb_url, validate_source_in_session, validate_target_in_session
from ..utils.paths import normalize_path
from .plan_validation_service import PlanValidationService
from .planning_service import OperationPlanNotFoundError
from .processed_media_service import ProcessedMediaService

logger = logging.getLogger(__name__)


class PlanApplyError(ValueError):
    """Raised when plan apply preconditions fail."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class ApplyService:
    DOWNLOAD_TIMEOUT_SECONDS = 30

    def __init__(self, session: AsyncSession, http_client: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.operation_plans = OperationPlanRepository(session)
        self.plan_operations = PlanOperationRepository(session)
        self.apply_runs = ApplyRunRepository(session)
        self.media_items = MediaItemRepository(session)
        self.processed_media = ProcessedMediaService(session)
        self.validation = PlanValidationService(session)
        self._http_client = http_client

    async def apply_plan(self, plan_id: int, confirm: bool) -> PlanApplyResult:
        result = await self.start_apply(plan_id, confirm=confirm)
        return await self.execute_apply_run(result.apply_run_id)

    async def start_apply(self, plan_id: int, confirm: bool) -> PlanApplyResult:
        if not confirm:
            raise PlanApplyError("Apply requires confirm=true")

        plan = await self.operation_plans.get_by_id(plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {plan_id} was not found.")
        if plan.status != PlanStatus.READY:
            if plan.status == PlanStatus.APPLYING:
                raise PlanApplyError("Plan is already applying", error_code="apply_in_progress")
            if plan.status == PlanStatus.APPLIED:
                raise PlanApplyError("Plan has already been applied")
            raise PlanApplyError(f"Plan status must be READY, got {plan.status}")

        validation_result = await self.validation.validate_plan(plan_id)
        if validation_result.conflict_count > 0:
            raise PlanApplyError(
                f"Plan has {validation_result.conflict_count} conflict(s); apply is blocked"
            )

        operations = list(await self.plan_operations.list_by_plan(plan_id))
        if not operations:
            raise PlanApplyError("Plan has no operations")

        apply_run = await self.apply_runs.create(
            ApplyRun(
                operation_plan_id=plan_id,
                status=ApplyRunStatus.RUNNING,
                total_operations=len(operations),
            )
        )
        plan.status = PlanStatus.APPLYING
        await self.session.commit()
        await self.session.refresh(plan)
        await self.session.refresh(apply_run)

        return PlanApplyResult(
            plan_id=plan.id,
            apply_run_id=apply_run.id,
            status=plan.status,
            total_operations=apply_run.total_operations,
            done_operations=apply_run.done_operations,
            failed_operations=apply_run.failed_operations,
            error_message=apply_run.error_message,
        )

    async def execute_apply_run(self, apply_run_id: int) -> PlanApplyResult:
        apply_run = await self.session.get(ApplyRun, apply_run_id)
        if apply_run is None:
            raise PlanApplyError(f"Apply run {apply_run_id} was not found")
        plan = await self.operation_plans.get_by_id(apply_run.operation_plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {apply_run.operation_plan_id} was not found.")
        if apply_run.status != ApplyRunStatus.RUNNING:
            return PlanApplyResult(
                plan_id=plan.id,
                apply_run_id=apply_run.id,
                status=plan.status,
                total_operations=apply_run.total_operations,
                done_operations=apply_run.done_operations,
                failed_operations=apply_run.failed_operations,
                error_message=apply_run.error_message,
            )

        operations = list(await self.plan_operations.list_by_plan(plan.id))
        done_count = 0
        failed_count = 0
        fatal_error: str | None = None

        for operation in operations:
            if operation.validation_status == ValidationStatus.CONFLICT:
                await self._mark_operation_failed(operation, apply_run, "Operation has validation conflict")
                failed_count += 1
                fatal_error = operation.validation_error or "Validation conflict"
                apply_run.done_operations = done_count
                apply_run.failed_operations = failed_count
                await self.session.commit()
                break

            started_at = datetime.now(UTC)
            operation.status = OperationStatus.RUNNING
            operation.started_at = started_at
            await self.session.flush()

            try:
                rollback_data = await self._execute_operation(operation, plan.scan_session_id)
                finished_at = datetime.now(UTC)
                operation.status = OperationStatus.DONE
                operation.finished_at = finished_at
                operation.error_message = None
                await self._create_log(
                    apply_run,
                    operation,
                    OperationStatus.DONE,
                    started_at,
                    finished_at,
                    rollback_data=rollback_data,
                )
                done_count += 1
            except Exception as exc:  # noqa: BLE001 - surface apply failure to user
                finished_at = datetime.now(UTC)
                message = str(exc)
                operation.status = OperationStatus.FAILED
                operation.finished_at = finished_at
                operation.error_message = message[:2000]
                await self._create_log(
                    apply_run,
                    operation,
                    OperationStatus.FAILED,
                    started_at,
                    finished_at,
                    error_message=message,
                )
                failed_count += 1
                fatal_error = message
                apply_run.done_operations = done_count
                apply_run.failed_operations = failed_count
                await self.session.commit()
                break

            apply_run.done_operations = done_count
            apply_run.failed_operations = failed_count
            await self.session.commit()

        apply_run.finished_at = datetime.now(UTC)
        apply_run.done_operations = done_count
        apply_run.failed_operations = failed_count

        if fatal_error:
            apply_run.status = ApplyRunStatus.FAILED
            apply_run.error_message = fatal_error
            plan.status = PlanStatus.FAILED
        else:
            apply_run.status = ApplyRunStatus.COMPLETED
            plan.status = PlanStatus.APPLIED
            plan.applied_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(plan)
        await self.session.refresh(apply_run)

        return PlanApplyResult(
            plan_id=plan.id,
            apply_run_id=apply_run.id,
            status=plan.status,
            total_operations=apply_run.total_operations,
            done_operations=apply_run.done_operations,
            failed_operations=apply_run.failed_operations,
            error_message=apply_run.error_message,
        )

    async def list_apply_runs(self, plan_id: int) -> list[ApplyRunRead]:
        plan = await self.operation_plans.get_by_id(plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {plan_id} was not found.")
        runs = await self.apply_runs.list_by_plan(plan_id)
        return [ApplyRunRead.model_validate(run) for run in runs]

    async def _execute_operation(self, operation: PlanOperation, scan_session_id: int) -> dict | None:
        from ..repositories.scan_session_repository import ScanSessionRepository

        scan_session = await ScanSessionRepository(self.session).get(scan_session_id)
        if scan_session is None:
            raise PlanApplyError("Scan session not found")

        source_root = scan_session.source_path
        target_root = scan_session.target_path
        op_type = operation.operation_type

        if op_type == OperationType.CREATE_DIR:
            if not operation.target_path:
                raise PlanApplyError("CREATE_DIR target path is empty")
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                raise PlanApplyError(target_error)
            target = normalize_path(operation.target_path)
            if target.exists() and not target.is_dir():
                raise PlanApplyError(f"Target exists as file: {target}")
            target.mkdir(parents=True, exist_ok=True)
            return None

        if op_type == OperationType.MOVE_FILE:
            if not operation.source_path or not operation.target_path:
                raise PlanApplyError("MOVE_FILE requires source and target paths")
            source_error = validate_source_in_session(operation.source_path, source_root)
            if source_error:
                raise PlanApplyError(source_error)
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                raise PlanApplyError(target_error)
            source = normalize_path(operation.source_path)
            target = normalize_path(operation.target_path)
            if not source.exists():
                raise PlanApplyError(f"Source file missing: {source}")
            if target.exists():
                raise PlanApplyError(f"Target file already exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            await self._record_tv_episode_move(operation, target)
            return {
                "operation_type": op_type.value,
                "source_path": str(source),
                "target_path": str(target),
                "from": str(source),
                "to": str(target),
            }

        if op_type == OperationType.WRITE_TEXT_FILE:
            if not operation.target_path:
                raise PlanApplyError("WRITE_TEXT_FILE target path is empty")
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                raise PlanApplyError(target_error)
            target = normalize_path(operation.target_path)
            if target.exists():
                raise PlanApplyError(f"Target file already exists: {target}")
            content = await self._build_text_content(operation)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"path": str(target), "bytes": len(content.encode("utf-8"))}

        if op_type == OperationType.DOWNLOAD_FILE:
            if not operation.source_path or not operation.target_path:
                raise PlanApplyError("DOWNLOAD_FILE requires source URL and target path")
            if not is_trusted_tmdb_url(operation.source_path):
                raise PlanApplyError("Download URL is not from trusted TMDB image domain")
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                raise PlanApplyError(target_error)
            target = normalize_path(operation.target_path)
            if target.exists():
                raise PlanApplyError(f"Target file already exists: {target}")
            content = await self._download_bytes(operation.source_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return {"url": operation.source_path, "path": str(target), "bytes": len(content)}

        raise PlanApplyError(f"Unsupported operation type: {op_type}")

    async def _record_tv_episode_move(self, operation: PlanOperation, target: Path) -> None:
        payload = operation.payload_json or {}
        episode_id = payload.get("tv_episode_id")
        if payload.get("media_type") != "tv" or not episode_id:
            return

        from ..repositories.tv_repository import TvRepository

        show_id = payload.get("tv_show_id")
        if not show_id:
            return
        tv_repo = TvRepository(self.session)
        show = await tv_repo.get_show(int(show_id))
        if show is None:
            return
        episode = next(
            (episode for episode in await tv_repo.list_episodes(show.id) if episode.id == int(episode_id)),
            None,
        )
        if episode is None or not episode.source_file_id:
            return
        from ..models.media_file import MediaFile

        media_file = await self.session.get(MediaFile, episode.source_file_id)
        if media_file is None:
            return
        await self.processed_media.record_from_tv_episode(
            show,
            episode,
            media_file,
            session_id=show.scan_session_id,
            target_path=str(target),
        )

    async def _build_text_content(self, operation: PlanOperation) -> str:
        payload = operation.payload_json or {}
        media_item_id = payload.get("media_item_id")
        nfo_type = payload.get("nfo_type")
        if media_item_id and nfo_type == "movie":
            item = await self.media_items.get_by_id(int(media_item_id))
            if item is None:
                raise PlanApplyError(f"Media item {media_item_id} not found for NFO generation")
            return build_movie_nfo(item)
        if nfo_type in {"tvshow", "episode"}:
            from ..repositories.tv_repository import TvRepository

            tv_repo = TvRepository(self.session)
            show_id = payload.get("tv_show_id")
            if not show_id:
                raise PlanApplyError("TV NFO payload missing tv_show_id")
            show = await tv_repo.get_show(int(show_id))
            if show is None:
                raise PlanApplyError(f"TV show {show_id} not found for NFO generation")
            if nfo_type == "tvshow":
                return build_tvshow_nfo(show)
            episode_id = payload.get("tv_episode_id")
            if not episode_id:
                raise PlanApplyError("Episode NFO payload missing tv_episode_id")
            episode = next(
                (episode for episode in await tv_repo.list_episodes(show.id) if episode.id == int(episode_id)),
                None,
            )
            if episode is None:
                raise PlanApplyError(f"TV episode {episode_id} not found for NFO generation")
            return build_episode_nfo(show, episode)
        raise PlanApplyError("WRITE_TEXT_FILE payload missing media_item_id or nfo_type")

    async def _download_bytes(self, url: str) -> bytes:
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=self.DOWNLOAD_TIMEOUT_SECONDS)
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise PlanApplyError(f"Download failed with status {response.status_code}")
            content_type = response.headers.get("content-type", "")
            if content_type and not content_type.startswith("image/"):
                raise PlanApplyError(f"Unexpected content type: {content_type}")
            return response.content
        finally:
            if owns_client and client is not None:
                await client.aclose()

    async def _mark_operation_failed(
        self,
        operation: PlanOperation,
        apply_run: ApplyRun,
        message: str,
    ) -> None:
        started_at = datetime.now(UTC)
        operation.status = OperationStatus.FAILED
        operation.started_at = started_at
        operation.finished_at = started_at
        operation.error_message = message
        await self._create_log(
            apply_run,
            operation,
            OperationStatus.FAILED,
            started_at,
            started_at,
            error_message=message,
        )

    async def _create_log(
        self,
        apply_run: ApplyRun,
        operation: PlanOperation,
        status: OperationStatus,
        started_at: datetime,
        finished_at: datetime,
        error_message: str | None = None,
        rollback_data: dict | None = None,
    ) -> None:
        log = ApplyOperationLog(
            apply_run_id=apply_run.id,
            plan_operation_id=operation.id,
            operation_type=operation.operation_type,
            status=status,
            source_path=operation.source_path,
            target_path=operation.target_path,
            error_message=error_message[:2000] if error_message else None,
            started_at=started_at,
            finished_at=finished_at,
            rollback_data=rollback_data,
        )
        self.session.add(log)
        await self.session.flush()


# Strong references keep fire-and-forget tasks alive until completion
# (asyncio only holds weak references to scheduled tasks).
_background_apply_tasks: set[asyncio.Task[None]] = set()


def schedule_apply_run(
    apply_run_id: int,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> asyncio.Task[None]:
    task = asyncio.create_task(execute_apply_run_in_background(apply_run_id, session_factory))
    _background_apply_tasks.add(task)
    task.add_done_callback(_background_apply_tasks.discard)
    return task


async def execute_apply_run_in_background(
    apply_run_id: int,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> None:
    try:
        async with session_factory() as session:
            await ApplyService(session).execute_apply_run(apply_run_id)
    except Exception as exc:  # noqa: BLE001 - a stuck APPLYING plan is worse than a broad catch
        logger.exception("Background apply run %s crashed", apply_run_id)
        try:
            async with session_factory() as session:
                await _mark_apply_run_crashed(session, apply_run_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark apply run %s as failed", apply_run_id)


async def _mark_apply_run_crashed(session: AsyncSession, apply_run_id: int, message: str) -> None:
    apply_run = await session.get(ApplyRun, apply_run_id)
    if apply_run is None:
        return
    if apply_run.status == ApplyRunStatus.RUNNING:
        apply_run.status = ApplyRunStatus.FAILED
        apply_run.error_message = message[:2000]
        apply_run.finished_at = datetime.now(UTC)
    plan = await OperationPlanRepository(session).get_by_id(apply_run.operation_plan_id)
    if plan is not None and plan.status == PlanStatus.APPLYING:
        plan.status = PlanStatus.FAILED
    await session.commit()
