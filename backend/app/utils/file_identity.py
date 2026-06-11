from __future__ import annotations

from datetime import datetime
from pathlib import Path


def normalize_storage_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/").casefold()


def build_file_identity_key(
    *,
    path: str | Path,
    file_name: str,
    size_bytes: int | None,
    modified_at: datetime | None,
) -> str:
    _ = path
    size = size_bytes if size_bytes is not None else -1
    modified = int(modified_at.timestamp()) if modified_at is not None else -1
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
