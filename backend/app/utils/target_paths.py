from pathlib import Path

FORBIDDEN_WINDOWS_CHARS = '<>:"/\\|?*'
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"


def sanitize_path_segment(name: str) -> str:
    sanitized = "".join("_" if character in FORBIDDEN_WINDOWS_CHARS else character for character in name)
    return sanitized.rstrip(" .")


def format_season_folder(season_number: int) -> str:
    return f"Season {season_number:02d}"


def format_episode_filename(title: str, season_number: int, episode_number: int, extension: str) -> str:
    safe_title = sanitize_path_segment(title)
    return f"{safe_title} S{season_number:02d}E{episode_number:02d}{extension}"


def build_movie_folder_path(target_root: Path, matched_title: str, matched_year: int) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    return target_root / "Movies" / f"{safe_title} ({matched_year})"


def build_movie_video_path(target_root: Path, matched_title: str, matched_year: int, extension: str) -> Path:
    folder = build_movie_folder_path(target_root, matched_title, matched_year)
    safe_title = sanitize_path_segment(matched_title)
    return folder / f"{safe_title} ({matched_year}){extension}"


def build_tv_season_folder_path(target_root: Path, matched_title: str, season_number: int) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    return target_root / "TV Shows" / safe_title / format_season_folder(season_number)


def build_tv_video_path(
    target_root: Path,
    matched_title: str,
    season_number: int,
    episode_number: int,
    extension: str,
) -> Path:
    folder = build_tv_season_folder_path(target_root, matched_title, season_number)
    return folder / format_episode_filename(matched_title, season_number, episode_number, extension)


def build_tv_show_folder_path(target_root: Path, matched_title: str) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    return target_root / "TV Shows" / safe_title


def tmdb_image_download_url(image_path: str) -> str:
    return f"{TMDB_IMAGE_BASE_URL}{image_path}"
