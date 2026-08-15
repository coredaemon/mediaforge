from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def normalize_storage_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/").casefold()


def _epoch_seconds(moment: datetime) -> int:
    """Seconds since the epoch, reading naive values as the UTC they were written as.

    SQLite hands datetimes back naive even for DateTime(timezone=True) columns, so
    the same mtime yields a tz-aware value when freshly scanned and a naive one when
    reloaded. Calling .timestamp() on the naive value would read it as local time and
    shift the key by the UTC offset, silently invalidating the whole memory cache
    whenever the local offset changes.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp())


def build_file_identity_key(
    *,
    path: str | Path,
    file_name: str,
    size_bytes: int | None,
    modified_at: datetime | None,
) -> str:
    _ = path
    size = size_bytes if size_bytes is not None else -1
    modified = _epoch_seconds(modified_at) if modified_at is not None else -1
    return f"{file_name.casefold()}|{size}|{modified}"


def file_identity_matches(
    *,
    record_key: str,
    path: str | Path,
    file_name: str,
    size_bytes: int | None,
    modified_at: datetime | None,
) -> bool:
    return record_key == build_file_identity_key(
        path=path,
        file_name=file_name,
        size_bytes=size_bytes,
        modified_at=modified_at,
    )
