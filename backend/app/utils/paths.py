from pathlib import Path

from ..models.enums import MediaFileKind

VIDEO_EXTENSIONS = {
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ts",
    ".webm",
    ".wmv",
}
SUBTITLE_EXTENSIONS = {".ass", ".idx", ".srt", ".ssa", ".sub", ".vtt"}
SIDECAR_EXTENSIONS = {".jpeg", ".jpg", ".nfo", ".png", ".webp"}


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUBTITLE_EXTENSIONS


def is_sidecar_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SIDECAR_EXTENSIONS


def classify_media_file_kind(path: str | Path) -> MediaFileKind:
    if is_video_file(path):
        return MediaFileKind.VIDEO
    if is_subtitle_file(path):
        return MediaFileKind.SUBTITLE
    if is_sidecar_file(path):
        return MediaFileKind.SIDECAR
    return MediaFileKind.OTHER
