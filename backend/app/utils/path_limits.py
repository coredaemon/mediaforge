from __future__ import annotations

import sys
from functools import lru_cache

# Classic Windows MAX_PATH. Paths at or above this fail to create unless the
# machine opted into long paths, and mkdir needs a little more headroom than
# a plain file because it must be able to hold a child entry.
WINDOWS_MAX_PATH = 260
WINDOWS_MAX_DIR_PATH = 248


@lru_cache(maxsize=1)
def long_paths_enabled() -> bool:
    """True when Windows is configured to accept paths beyond MAX_PATH."""
    if sys.platform != "win32":
        return True
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(value)
    except OSError:
        # Missing key or no access: assume the conservative limit still applies.
        return False


def max_path_length(*, is_directory: bool = False) -> int | None:
    """Longest usable path, or None when the platform imposes no practical limit."""
    if sys.platform != "win32" or long_paths_enabled():
        return None
    return WINDOWS_MAX_DIR_PATH if is_directory else WINDOWS_MAX_PATH


def path_length_error(path: str, *, is_directory: bool = False) -> str | None:
    """Describe why *path* is too long for this platform, or None when it fits."""
    limit = max_path_length(is_directory=is_directory)
    if limit is None or len(path) < limit:
        return None
    return (
        f"Path is {len(path)} characters, over the {limit}-character Windows limit: {path}. "
        "Shorten the library folder or enable long path support."
    )
