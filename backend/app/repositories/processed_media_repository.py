from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.processed_media_record import ProcessedMediaRecord


class ProcessedMediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_identity_key(self, file_identity_key: str) -> ProcessedMediaRecord | None:
        result = await self.session.execute(
            select(ProcessedMediaRecord).where(ProcessedMediaRecord.file_identity_key == file_identity_key)
        )
        return result.scalar_one_or_none()

    async def upsert(self, record: ProcessedMediaRecord) -> ProcessedMediaRecord:
        existing = await self.get_by_identity_key(record.file_identity_key)
        now = datetime.now(UTC)
        if existing is None:
            record.last_seen_at = now
            self.session.add(record)
            await self.session.flush()
            return record

        for field in (
            "source_path",
            "file_name",
            "file_stem",
            "file_extension",
            "file_size",
            "modified_at",
            "media_type",
            "status",
            "clean_title",
            "year",
            "season",
            "episode",
            "tv_show_title",
            "tv_season_number",
            "tv_episode_number",
            "tmdb_show_id",
            "tmdb_episode_id",
            "tmdb_id",
            "tmdb_media_type",
            "matched_title",
            "match_confidence",
            "imdb_id",
            "tvdb_id",
            "wikidata_id",
            "localized_title",
            "localized_overview",
            "tmdb_original_title",
            "poster_path",
            "backdrop_path",
            "poster_url",
            "backdrop_url",
            "metadata_language",
            "match_source",
            "sidecar_source_path",
            "local_poster_path",
            "local_backdrop_path",
            "last_session_id",
            "last_media_item_id",
        ):
            value = getattr(record, field)
            if value is not None:
                setattr(existing, field, value)

        existing.last_seen_at = now
        existing.scan_count += 1
        if record.last_scanned_at:
            existing.last_scanned_at = record.last_scanned_at
        if record.last_recognized_at:
            existing.last_recognized_at = record.last_recognized_at
            existing.recognition_count += 1
        if record.last_planned_at:
            existing.last_planned_at = record.last_planned_at
        await self.session.flush()
        return existing
