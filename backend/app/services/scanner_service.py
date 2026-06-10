import os
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind, ScanSessionStatus
from ..models.media_file import MediaFile
from ..models.scan_session import ScanSession
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..utils.paths import classify_media_file_kind, normalize_path
from .scan_session_service import ScanSessionNotFoundError


class ScannerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)

    async def discover(self, scan_session_id: int) -> ScanSession:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")

        source_path = normalize_path(scan_session.source_path)
        if not source_path.exists() or not source_path.is_dir():
            scan_session.status = ScanSessionStatus.FAILED
            scan_session.error_message = "Source path does not exist or is not a directory."
            scan_session.finished_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(scan_session)
            return scan_session

        scan_session.status = ScanSessionStatus.DISCOVERING
        scan_session.started_at = datetime.now(UTC)
        scan_session.finished_at = None
        scan_session.error_message = None
        await self.media_files.delete_for_scan_session(scan_session_id)
        await self.session.flush()

        try:
            for file_path, scan_error in self._walk_files(source_path):
                await self.media_files.add(self._build_media_file(scan_session_id, file_path, scan_error))
            scan_session.status = ScanSessionStatus.DISCOVERED
            scan_session.finished_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(scan_session)
            return scan_session
        except OSError as exc:
            logger.exception("Critical scanner failure for session {}", scan_session_id)
            scan_session.status = ScanSessionStatus.FAILED
            scan_session.error_message = str(exc)
            scan_session.finished_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(scan_session)
            return scan_session

    def _walk_files(self, root: Path) -> list[tuple[Path, str | None]]:
        discovered: list[tuple[Path, str | None]] = []
        pending = [root]

        while pending:
            directory = pending.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError as exc:
                logger.warning("Could not scan directory {}: {}", directory, exc)
                discovered.append((directory, str(exc)))
                continue

            for entry in entries:
                entry_path = Path(entry.path)
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry_path)
                    elif entry.is_file(follow_symlinks=False):
                        discovered.append((entry_path, None))
                except OSError as exc:
                    logger.warning("Could not inspect path {}: {}", entry_path, exc)
                    discovered.append((entry_path, str(exc)))

        return discovered

    def _build_media_file(self, scan_session_id: int, path: Path, scan_error: str | None) -> MediaFile:
        kind = classify_media_file_kind(path)
        size_bytes: int | None = None
        if scan_error is None:
            try:
                size_bytes = path.stat().st_size
            except OSError as exc:
                logger.warning("Could not read file metadata for {}: {}", path, exc)
                scan_error = str(exc)

        return MediaFile(
            scan_session_id=scan_session_id,
            path=str(path),
            file_name=path.name,
            extension=path.suffix.lower(),
            size_bytes=size_bytes,
            kind=kind,
            is_video=kind == MediaFileKind.VIDEO,
            is_subtitle=kind == MediaFileKind.SUBTITLE,
            is_sidecar=kind == MediaFileKind.SIDECAR,
            scan_error=scan_error,
        )
