from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaItemStatus, MediaType
from ..models.media_file import MediaFile
from ..models.media_item import MediaItem
from ..models.processed_media_record import ProcessedMediaRecord
from ..models.tv_episode import TvEpisode
from ..models.tv_show import TvShow
from ..repositories.processed_media_repository import ProcessedMediaRepository
from ..utils.file_identity import build_file_identity_key, file_identity_matches
from ..utils.tmdb_images import tmdb_image_url


class ProcessedMediaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.records = ProcessedMediaRepository(session)

    async def find_reusable_record(self, media_file: MediaFile) -> ProcessedMediaRecord | None:
        if media_file.size_bytes is None:
            return None
        identity_key = build_file_identity_key(
            path=media_file.path,
            file_name=media_file.file_name,
            size_bytes=media_file.size_bytes,
            modified_at=media_file.modified_at,
        )
        record = await self.records.get_by_identity_key(identity_key)
        if record is None:
            return None
        if not file_identity_matches(
            record_key=record.file_identity_key,
            path=media_file.path,
            file_name=media_file.file_name,
            size_bytes=media_file.size_bytes,
            modified_at=media_file.modified_at,
        ):
            return None
        return record

    def apply_record_to_item(self, record: ProcessedMediaRecord, item: MediaItem, media_file: MediaFile) -> None:
        item.reused_from_memory = True
        item.memory_status = "reused"
        media_file.reused_from_memory = True

        if record.media_type:
            try:
                item.media_type = MediaType(record.media_type)
            except ValueError:
                pass
        if record.status:
            status_map = {
                "matched": MediaItemStatus.MATCHED,
                "needs_review": MediaItemStatus.NEEDS_REVIEW,
                "unmatched": MediaItemStatus.UNMATCHED,
                "ignored": MediaItemStatus.IGNORED,
                "recognized": MediaItemStatus.DISCOVERED,
                "ready": MediaItemStatus.MATCHED,
                "new": MediaItemStatus.DISCOVERED,
            }
            item.status = status_map.get(record.status, MediaItemStatus.DISCOVERED)

        item.original_title = record.file_name
        item.parsed_title = record.clean_title or record.matched_title or record.localized_title
        item.year = record.year
        item.season_number = record.season
        item.episode_number = record.episode
        item.tmdb_id = record.tmdb_id
        item.tmdb_media_type = record.tmdb_media_type
        item.matched_title = record.matched_title or record.localized_title
        item.matched_year = record.year
        item.match_confidence = record.match_confidence
        item.imdb_id = record.imdb_id
        item.tvdb_id = record.tvdb_id
        item.wikidata_id = record.wikidata_id
        item.localized_title = record.localized_title
        item.localized_overview = record.localized_overview
        item.tmdb_original_title = record.tmdb_original_title
        item.poster_path = record.poster_path
        item.backdrop_path = record.backdrop_path
        item.poster_url = record.poster_url
        item.backdrop_url = record.backdrop_url
        item.metadata_language = record.metadata_language
        item.needs_review = item.status == MediaItemStatus.NEEDS_REVIEW
        item.local_ai_status = "skipped"
        item.gemini_status = "skipped"
        item.local_ai_error = "Reused from processed media memory."
        item.gemini_error = None
        item.match_source = record.match_source or ("memory" if record.tmdb_id else None)
        item.sidecar_source_path = record.sidecar_source_path
        item.local_poster_path = record.local_poster_path
        item.local_backdrop_path = record.local_backdrop_path
        if record.tmdb_id and item.status == MediaItemStatus.MATCHED:
            item.needs_review = False

    async def record_from_item(
        self,
        item: MediaItem,
        media_file: MediaFile | None,
        *,
        session_id: int | None = None,
        planned: bool = False,
    ) -> ProcessedMediaRecord | None:
        if media_file is None or media_file.size_bytes is None:
            return None

        identity_key = build_file_identity_key(
            path=media_file.path,
            file_name=media_file.file_name,
            size_bytes=media_file.size_bytes,
            modified_at=media_file.modified_at,
        )
        now = datetime.now(UTC)
        record = ProcessedMediaRecord(
            source_path=media_file.path,
            file_name=media_file.file_name,
            file_stem=Path(media_file.file_name).stem,
            file_extension=media_file.extension,
            file_size=media_file.size_bytes,
            modified_at=media_file.modified_at,
            file_identity_key=identity_key,
            media_type=item.media_type.value if item.media_type else None,
            status=_memory_status_from_item(item),
            clean_title=item.parsed_title or item.ai_clean_title or item.gemini_clean_title,
            year=item.year or item.matched_year,
            season=item.season_number,
            episode=item.episode_number,
            tmdb_id=item.tmdb_id,
            tmdb_media_type=item.tmdb_media_type,
            matched_title=item.matched_title or item.localized_title,
            match_confidence=item.match_confidence,
            imdb_id=item.imdb_id,
            tvdb_id=item.tvdb_id,
            wikidata_id=item.wikidata_id,
            localized_title=item.localized_title or item.matched_title,
            localized_overview=item.localized_overview,
            tmdb_original_title=item.tmdb_original_title,
            poster_path=item.poster_path,
            backdrop_path=item.backdrop_path,
            poster_url=item.poster_url or tmdb_image_url(item.poster_path),
            backdrop_url=item.backdrop_url or tmdb_image_url(item.backdrop_path, "w780"),
            metadata_language=item.metadata_language,
            match_source=item.match_source,
            sidecar_source_path=item.sidecar_source_path,
            local_poster_path=item.local_poster_path,
            local_backdrop_path=item.local_backdrop_path,
            last_seen_at=now,
            last_scanned_at=now,
            last_recognized_at=now if item.tmdb_id or item.parsed_title else None,
            last_planned_at=now if planned else None,
            last_session_id=session_id,
            last_media_item_id=item.id,
        )
        return await self.records.upsert(record)

    async def record_from_tv_episode(
        self,
        show: TvShow,
        episode: TvEpisode,
        media_file: MediaFile | None,
        *,
        session_id: int | None = None,
        target_path: str | None = None,
    ) -> ProcessedMediaRecord | None:
        if media_file is None or media_file.size_bytes is None:
            return None

        identity_key = build_file_identity_key(
            path=media_file.path,
            file_name=media_file.file_name,
            size_bytes=media_file.size_bytes,
            modified_at=media_file.modified_at,
        )
        now = datetime.now(UTC)
        title = episode.title or f"S{episode.season_number:02d}E{episode.episode_number:02d}"
        record = ProcessedMediaRecord(
            source_path=target_path or media_file.path,
            file_name=media_file.file_name,
            file_stem=Path(media_file.file_name).stem,
            file_extension=media_file.extension,
            file_size=media_file.size_bytes,
            modified_at=media_file.modified_at,
            file_identity_key=identity_key,
            media_type="tv",
            status="matched",
            clean_title=title,
            year=show.year,
            season=episode.season_number,
            episode=episode.episode_number,
            tv_show_title=show.title,
            tv_season_number=episode.season_number,
            tv_episode_number=episode.episode_number,
            tmdb_show_id=show.tmdb_id,
            tmdb_episode_id=episode.tmdb_episode_id,
            tmdb_id=show.tmdb_id,
            tmdb_media_type="tv",
            matched_title=show.title,
            match_confidence=episode.confidence or show.confidence,
            imdb_id=show.imdb_id,
            tvdb_id=show.tvdb_id,
            wikidata_id=show.wikidata_id,
            localized_title=title,
            localized_overview=episode.overview,
            tmdb_original_title=show.original_title,
            poster_path=show.poster_path,
            backdrop_path=show.backdrop_path,
            poster_url=show.poster_url or tmdb_image_url(show.poster_path),
            backdrop_url=show.backdrop_url or tmdb_image_url(show.backdrop_path, "w780"),
            metadata_language=show.language,
            match_source=episode.match_source or show.match_source,
            last_seen_at=now,
            last_scanned_at=now,
            last_recognized_at=now,
            last_planned_at=now,
            last_session_id=session_id,
        )
        return await self.records.upsert(record)


def _memory_status_from_item(item: MediaItem) -> str:
    if item.status == MediaItemStatus.MATCHED:
        return "matched"
    if item.status == MediaItemStatus.NEEDS_REVIEW:
        return "needs_review"
    if item.status == MediaItemStatus.UNMATCHED:
        return "unmatched"
    if item.status == MediaItemStatus.IGNORED:
        return "ignored"
    if item.parsed_title:
        return "recognized"
    return "new"
