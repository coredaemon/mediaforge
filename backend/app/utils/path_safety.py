from pathlib import Path
from urllib.parse import urlparse

from .paths import normalize_path

TMDB_IMAGE_HOST = "image.tmdb.org"


def is_within_root(path: Path, root: Path) -> bool:
    try:
        normalized_path = normalize_path(path)
        normalized_root = normalize_path(root)
        normalized_path.relative_to(normalized_root)
        return True
    except ValueError:
        return False


def validate_source_in_session(path: str | Path, source_root: str | Path) -> str | None:
    normalized = normalize_path(path)
    root = normalize_path(source_root)
    if not is_within_root(normalized, root):
        return f"Source path escapes session root: {normalized}"
    return None


def validate_target_in_session(path: str | Path, target_root: str | Path) -> str | None:
    normalized = normalize_path(path)
    root = normalize_path(target_root)
    if not is_within_root(normalized, root):
        return f"Target path escapes session root: {normalized}"
    return None


def is_trusted_tmdb_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host == TMDB_IMAGE_HOST or host.endswith(f".{TMDB_IMAGE_HOST}")
