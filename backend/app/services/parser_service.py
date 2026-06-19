from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind, MediaItemStatus, MediaType, ScanSessionStatus
from ..models.media_item import MediaItem
from ..models.scan_session import ScanSession
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..utils.media_name_parser import parse_media_filename
from .media_classification_service import MediaClassificationService
from .processed_media_service import ProcessedMediaService
from .scan_session_service import ScanSessionNotFoundError
from .sidecar_metadata_service import SidecarMetadataService
from .tv_hints import parse_tv_file_hint


class ParserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)
        self.media_items = MediaItemRepository(session)
        self.processed_media = ProcessedMediaService(session)
        self.sidecar_metadata = SidecarMetadataService(session)

    async def parse_scan_session(self, session_id: int) -> ScanSession:
        scan_session = await self.scan_sessions.get(session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {session_id} was not found.")

        scan_session.status = ScanSessionStatus.PARSING
        scan_session.error_message = None
        await self.session.flush()

        video_files = await self.media_files.list_by_kind(session_id, MediaFileKind.VIDEO)
        classification = await MediaClassificationService(self.session).classify(session_id)
        skip_tv_episode_files = classification.content_type in {"tv", "mixed"} and classification.confidence >= 0.65
        for media_file in video_files:
            if media_file.media_item_id is not None:
                continue
            tv_hint = parse_tv_file_hint(media_file.file_name, list(Path(media_file.path).parts[:-1]))
            if skip_tv_episode_files and tv_hint.season_number is not None and tv_hint.episode_number is not None:
                continue

            memory_record = await self.processed_media.find_reusable_record(media_file)
            if memory_record is not None:
                media_item = await self.media_items.create(
                    MediaItem(
                        scan_session_id=session_id,
                        media_type=MediaType.UNKNOWN,
                        status=MediaItemStatus.DISCOVERED,
                        original_title=media_file.file_name,
                        needs_review=False,
                    )
                )
                self.processed_media.apply_record_to_item(memory_record, media_item, media_file)
                await self.media_files.link_to_media_item(media_file, media_item.id)
                await self.sidecar_metadata.enrich_item_from_sidecars(media_item, media_file)
                await self.sidecar_metadata.link_sidecar_files(session_id, media_item.id, video_file=media_file)
                continue

            candidate = parse_media_filename(media_file.file_name)
            status = self._status_for_candidate(candidate.media_type, candidate.confidence)
            media_item = await self.media_items.create(
                MediaItem(
                    scan_session_id=session_id,
                    media_type=candidate.media_type,
                    status=status,
                    original_title=candidate.original_name,
                    parsed_title=candidate.title,
                    year=candidate.year,
                    season_number=candidate.season_number,
                    episode_number=candidate.episode_number,
                    confidence=candidate.confidence,
                    needs_review=candidate.needs_review or status == MediaItemStatus.NEEDS_REVIEW,
                    memory_status="new",
                )
            )
            await self.media_files.link_to_media_item(media_file, media_item.id)
            await self.sidecar_metadata.enrich_item_from_sidecars(media_item, media_file)
            await self.sidecar_metadata.link_sidecar_files(session_id, media_item.id, video_file=media_file)

        scan_session.status = ScanSessionStatus.PARSED
        scan_session.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(scan_session)
        return scan_session

    def _status_for_candidate(self, media_type: MediaType, confidence: float) -> MediaItemStatus:
        if media_type == MediaType.UNKNOWN or confidence < 0.7:
            return MediaItemStatus.NEEDS_REVIEW
        return MediaItemStatus.DISCOVERED
