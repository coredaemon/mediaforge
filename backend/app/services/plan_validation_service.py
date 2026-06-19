from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import OperationType, ValidationStatus
from ..models.plan_operation import PlanOperation
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.operation_plan_repository import OperationPlanRepository
from ..repositories.plan_operation_repository import PlanOperationRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..schemas.operation_plan import PlanOperationRead, PlanValidationResult
from ..utils.path_safety import is_trusted_tmdb_url, validate_source_in_session, validate_target_in_session
from ..utils.paths import normalize_path
from .planning_service import OperationPlanNotFoundError


class PlanValidationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.operation_plans = OperationPlanRepository(session)
        self.plan_operations = PlanOperationRepository(session)
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)

    async def validate_plan(self, plan_id: int) -> PlanValidationResult:
        plan = await self.operation_plans.get_by_id(plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {plan_id} was not found.")

        scan_session = await self.scan_sessions.get(plan.scan_session_id)
        if scan_session is None:
            raise OperationPlanNotFoundError(f"Scan session for plan {plan_id} was not found.")

        source_root = normalize_path(scan_session.source_path)
        target_root = normalize_path(scan_session.target_path)
        session_files = {
            normalize_path(media_file.path): media_file
            for media_file in await self.media_files.list_for_scan_session(scan_session.id)
        }

        operations = list(await self.plan_operations.list_by_plan(plan_id))
        ok_count = 0
        warning_count = 0
        conflict_count = 0
        validated_operations: list[PlanOperation] = []

        for operation in operations:
            status, error = self._validate_operation(operation, source_root, target_root, session_files)
            operation.validation_status = status
            operation.validation_error = error
            operation.validated_at = datetime.now(UTC)
            validated_operations.append(operation)

            if status == ValidationStatus.OK:
                ok_count += 1
            elif status == ValidationStatus.WARNING:
                warning_count += 1
            elif status == ValidationStatus.CONFLICT:
                conflict_count += 1

        await self.session.commit()
        for operation in validated_operations:
            await self.session.refresh(operation)

        return PlanValidationResult(
            ok_count=ok_count,
            warning_count=warning_count,
            conflict_count=conflict_count,
            operations=[PlanOperationRead.model_validate(op) for op in validated_operations],
        )

    def _validate_operation(
        self,
        operation: PlanOperation,
        source_root: Path,
        target_root: Path,
        session_files: dict[Path, object],
    ) -> tuple[ValidationStatus, str | None]:
        op_type = operation.operation_type

        if op_type == OperationType.DOWNLOAD_FILE:
            if not operation.source_path:
                return ValidationStatus.CONFLICT, "Download URL is empty"
            if not is_trusted_tmdb_url(operation.source_path):
                return ValidationStatus.CONFLICT, "Download URL is not from trusted TMDB image domain"
            if not operation.target_path:
                return ValidationStatus.CONFLICT, "Download target path is empty"
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                return ValidationStatus.CONFLICT, target_error
            target = normalize_path(operation.target_path)
            if target.exists():
                return ValidationStatus.CONFLICT, f"Target file already exists: {target}"
            return ValidationStatus.OK, None

        if op_type == OperationType.MOVE_FILE:
            if not operation.source_path:
                return ValidationStatus.CONFLICT, "Move source path is empty"
            if not operation.target_path:
                return ValidationStatus.CONFLICT, "Move target path is empty"
            source_error = validate_source_in_session(operation.source_path, source_root)
            if source_error:
                return ValidationStatus.CONFLICT, source_error
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                return ValidationStatus.CONFLICT, target_error
            source = normalize_path(operation.source_path)
            target = normalize_path(operation.target_path)
            if not source.exists():
                return ValidationStatus.CONFLICT, f"Source file missing: {source}"
            if not source.is_file():
                return ValidationStatus.CONFLICT, f"Source path is not a file: {source}"
            if target.exists():
                return ValidationStatus.CONFLICT, f"Target file already exists: {target}"
            media_file = session_files.get(source)
            if media_file is not None:
                current_stat = source.stat()
                if media_file.size_bytes is not None and current_stat.st_size != media_file.size_bytes:
                    return ValidationStatus.CONFLICT, "Source file size changed since scan"
                if media_file.modified_at is not None:
                    current_mtime = datetime.fromtimestamp(current_stat.st_mtime, tz=UTC)
                    stored_mtime = media_file.modified_at
                    if stored_mtime.tzinfo is None:
                        stored_mtime = stored_mtime.replace(tzinfo=UTC)
                    if abs((current_mtime - stored_mtime).total_seconds()) > 1:
                        return ValidationStatus.CONFLICT, "Source file modified since scan"
            return ValidationStatus.OK, None

        if op_type in {OperationType.CREATE_DIR, OperationType.WRITE_TEXT_FILE}:
            if not operation.target_path:
                return ValidationStatus.CONFLICT, "Target path is empty"
            target_error = validate_target_in_session(operation.target_path, target_root)
            if target_error:
                return ValidationStatus.CONFLICT, target_error
            target = normalize_path(operation.target_path)
            if op_type == OperationType.CREATE_DIR:
                if target.exists() and not target.is_dir():
                    return ValidationStatus.CONFLICT, f"Target path exists as file: {target}"
                if target.exists() and target.is_dir():
                    return ValidationStatus.WARNING, f"Directory already exists: {target}"
                return ValidationStatus.OK, None
            if target.exists():
                return ValidationStatus.CONFLICT, f"Target file already exists: {target}"
            payload = operation.payload_json or {}
            if payload.get("media_type") == "tv":
                if payload.get("nfo_type") == "tvshow" and not payload.get("tv_show_id"):
                    return ValidationStatus.CONFLICT, "TV show NFO payload missing tv_show_id"
                if payload.get("nfo_type") == "episode" and (
                    not payload.get("tv_show_id") or not payload.get("tv_episode_id")
                ):
                    return ValidationStatus.CONFLICT, "TV episode NFO payload missing ids"
            return ValidationStatus.OK, None

        return ValidationStatus.OK, None
