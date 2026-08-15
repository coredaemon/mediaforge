from pathlib import Path

FORBIDDEN_WINDOWS_CHARS = '<>:"/\\|?*'
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"

# Windows refuses to create these names regardless of extension.
RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

# Stands in for a title that sanitizes away to nothing ("...", "   ").
# An empty segment would silently collapse out of the path and drop the
# whole show into the library root.
FALLBACK_PATH_SEGMENT = "_"


def sanitize_path_segment(name: str) -> str:
    sanitized = "".join(
        "_" if character in FORBIDDEN_WINDOWS_CHARS or ord(character) < 32 else character
        for character in name
    )
    sanitized = sanitized.strip().rstrip(" .")
    if not sanitized:
        return FALLBACK_PATH_SEGMENT
    if sanitized.split(".")[0].upper() in RESERVED_WINDOWS_NAMES:
        return f"_{sanitized}"
    return sanitized


def format_season_folder(season_number: int) -> str:
    return f"Season {season_number:02d}"


def format_episode_marker(season_number: int, episode_number: int, episode_number_end: int | None = None) -> str:
    """S02E01, or S02E01-E02 for a file holding two aired episodes.

    The range form is what Jellyfin, Plex and Kodi expect for merged releases.
    """
    marker = f"S{season_number:02d}E{episode_number:02d}"
    if episode_number_end and episode_number_end != episode_number:
        return f"{marker}-E{episode_number_end:02d}"
    return marker


def format_episode_filename(
    title: str,
    season_number: int,
    episode_number: int,
    extension: str,
    episode_title: str | None = None,
    episode_number_end: int | None = None,
) -> str:
    safe_title = sanitize_path_segment(title)
    marker = format_episode_marker(season_number, episode_number, episode_number_end)
    if episode_title:
        safe_episode_title = sanitize_path_segment(episode_title)
        return f"{safe_title} - {marker} - {safe_episode_title}{extension}"
    return f"{safe_title} {marker}{extension}"


def build_movie_folder_path(target_root: Path, matched_title: str, matched_year: int) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    return target_root / f"{safe_title} ({matched_year})"


def build_movie_video_path(target_root: Path, matched_title: str, matched_year: int, extension: str) -> Path:
    folder = build_movie_folder_path(target_root, matched_title, matched_year)
    safe_title = sanitize_path_segment(matched_title)
    return folder / f"{safe_title} ({matched_year}){extension}"


def build_tv_season_folder_path(target_root: Path, matched_title: str, season_number: int) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    return target_root / "TV Shows" / safe_title / format_season_folder(season_number)


def build_tv_show_folder_path_direct(target_root: Path, matched_title: str, year: int | None = None) -> Path:
    safe_title = sanitize_path_segment(matched_title)
    suffix = f" ({year})" if year else ""
    return target_root / f"{safe_title}{suffix}"


def build_tv_season_folder_path_direct(
    target_root: Path,
    matched_title: str,
    season_number: int,
    year: int | None = None,
) -> Path:
    return build_tv_show_folder_path_direct(target_root, matched_title, year) / format_season_folder(season_number)


def build_tv_video_path_direct(
    target_root: Path,
    matched_title: str,
    season_number: int,
    episode_number: int,
    extension: str,
    *,
    year: int | None = None,
    episode_title: str | None = None,
    episode_number_end: int | None = None,
) -> Path:
    folder = build_tv_season_folder_path_direct(target_root, matched_title, season_number, year)
    return folder / format_episode_filename(
        matched_title,
        season_number,
        episode_number,
        extension,
        episode_title,
        episode_number_end,
    )


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
