from pathlib import Path

VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".wmv"}
SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".sub", ".vtt"}
SIDECAR_EXTENSIONS = {".jpeg", ".jpg", ".json", ".nfo", ".png", ".webp", ".xml"}


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUBTITLE_EXTENSIONS


def is_sidecar_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SIDECAR_EXTENSIONS
