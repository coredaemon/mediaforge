from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..schemas.tv import TvFolderContext, TvFolderFileHint
from ..utils.nfo_parser import parse_nfo_file
from ..utils.paths import normalize_path
from .scan_session_service import ScanSessionNotFoundError
from .tv_hints import parse_tv_file_hint


class TvFolderContextBuilder:
    MAX_DEPTH = 6
    MAX_FILES = 500

    def __init__(self, session: AsyncSession) -> None:
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)

    async def build(self, scan_session_id: int) -> TvFolderContext:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")

        root = normalize_path(scan_session.source_path)
        files = list(await self.media_files.list_for_scan_session(scan_session_id))
        folders: set[str] = set()
        file_hints: list[TvFolderFileHint] = []
        possible_titles: list[str] = []
        warnings: list[str] = []
        truncated = len(files) > self.MAX_FILES

        for media_file in files[: self.MAX_FILES]:
            path = normalize_path(media_file.path)
            try:
                relative = path.relative_to(root)
            except ValueError:
                relative = Path(media_file.file_name)
            parents = list(relative.parts[:-1])
            if len(parents) > self.MAX_DEPTH:
                warnings.append(f"Folder depth truncated for {relative}")
                parents = parents[: self.MAX_DEPTH]
            for idx in range(1, len(parents) + 1):
                folders.add(str(Path(*parents[:idx])))

            hint = parse_tv_file_hint(media_file.file_name, parents)
            if hint.possible_title and hint.possible_title not in possible_titles:
                possible_titles.append(hint.possible_title)
            sidecar_ids = None
            if media_file.kind == MediaFileKind.SIDECAR and media_file.extension.lower() == ".nfo":
                parsed = parse_nfo_file(path)
                sidecar_ids = {
                    "tmdb_id": parsed.tmdb_id,
                    "imdb_id": parsed.imdb_id,
                    "tvdb_id": parsed.tvdb_id,
                    "wikidata_id": parsed.wikidata_id,
                    "media_type_hint": parsed.media_type_hint,
                }

            file_hints.append(
                TvFolderFileHint(
                    relative_path=str(relative),
                    file_name=media_file.file_name,
                    kind=media_file.kind.value,
                    size_bytes=media_file.size_bytes,
                    modified_at=media_file.modified_at.isoformat() if media_file.modified_at else None,
                    season_number=hint.season_number,
                    episode_number=hint.episode_number,
                    possible_title=hint.possible_title,
                    sidecar_ids=sidecar_ids,
                )
            )

        if truncated:
            warnings.append(f"Folder context truncated to {self.MAX_FILES} files; video/NFO hints are prioritized in analysis.")

        return TvFolderContext(
            root_path=str(root),
            folders=sorted(folders),
            files=file_hints,
            possible_show_titles=possible_titles[:10],
            warnings=warnings,
            truncated=truncated,
        )
