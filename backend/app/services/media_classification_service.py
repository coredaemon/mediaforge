from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..schemas.classification import ExtensionCount, MediaClassificationResult
from ..services.scan_session_service import ScanSessionNotFoundError
from ..services.tv_hints import parse_tv_file_hint
from ..utils.media_name_parser import parse_media_filename
from ..utils.paths import VIDEO_EXTENSIONS


class MediaClassificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)

    async def classify(self, scan_session_id: int) -> MediaClassificationResult:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        files = list(await self.media_files.list_for_scan_session(scan_session_id))
        total = len(files)
        videos = [file for file in files if file.kind == MediaFileKind.VIDEO]
        subtitles = [file for file in files if file.kind == MediaFileKind.SUBTITLE]
        sidecars = [file for file in files if file.kind == MediaFileKind.SIDECAR]
        folders = {str(Path(file.path).parent) for file in files}

        movie_like = 0
        tv_like = 0
        for file in videos:
            parsed = parse_media_filename(file.file_name)
            parents = list(Path(file.path).parts[:-1])
            tv_hint = parse_tv_file_hint(file.file_name, parents)
            if tv_hint.season_number is not None and tv_hint.episode_number is not None:
                tv_like += 1
            elif parsed.year is not None:
                movie_like += 1

        warnings: list[str] = []
        if total > 0 and not videos:
            warnings.append(
                "Файлы найдены, но видео не обнаружено. Проверьте расширения файлов или список поддерживаемых форматов."
            )

        content_type, confidence, reason = _classify(total, len(videos), movie_like, tv_like)
        return MediaClassificationResult(
            scan_session_id=scan_session_id,
            content_type=content_type,
            confidence=confidence,
            reason=reason,
            total_files=total,
            video_files=len(videos),
            subtitle_files=len(subtitles),
            sidecar_files=len(sidecars),
            nested_folder_count=max(0, len(folders) - 1),
            known_extensions=_extension_counts(file.extension for file in files if file.extension in VIDEO_EXTENSIONS),
            ignored_extensions=_extension_counts(
                file.extension for file in files if file.kind == MediaFileKind.OTHER and file.extension
            ),
            movie_like_files=movie_like,
            tv_like_files=tv_like,
            mixed=content_type == "mixed",
            needs_user_decision=content_type == "unknown" or confidence < 0.65,
            warnings=warnings,
        )


def _classify(total: int, video_count: int, movie_like: int, tv_like: int) -> tuple[str, float, str]:
    if total == 0:
        return "unknown", 0.0, "В папке пока нет просканированных файлов."
    if video_count == 0:
        return "unknown", 0.2, "Файлы есть, но поддерживаемые видеоформаты не обнаружены."
    if tv_like and movie_like:
        return "mixed", 0.78, "Найдены признаки фильмов и сериалов."
    if tv_like >= max(1, int(video_count * 0.5)):
        return "tv", min(0.95, 0.65 + tv_like / max(video_count, 1) * 0.3), "Найдены сезонные папки или шаблоны серий."
    if movie_like >= max(1, int(video_count * 0.5)):
        return "movies", min(0.92, 0.6 + movie_like / max(video_count, 1) * 0.3), "Найдены файлы с признаками фильмов и годов."
    return "unknown", 0.45, "Недостаточно сильных признаков фильмов или сериалов."


def _extension_counts(values) -> list[ExtensionCount]:
    counts = Counter(value.lower() for value in values if value)
    return [ExtensionCount(extension=ext, count=count) for ext, count in sorted(counts.items())]
