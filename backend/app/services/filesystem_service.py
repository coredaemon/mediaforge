import string
import sys
from pathlib import Path

from ..schemas.settings import BrowseResult, DirectoryEntry


def get_filesystem_roots() -> list[str]:
    if sys.platform == "win32":
        roots = []
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:/")
            if drive.exists():
                roots.append(str(drive).replace("\\", "/"))
        return roots
    home = Path.home()
    return ["/", str(home)]


def browse_directory(path: str) -> BrowseResult:
    target = Path(path).resolve()
    parent: str | None = None
    if target.parent != target:
        parent = str(target.parent)

    if not target.exists():
        return BrowseResult(
            current_path=str(target),
            parent_path=parent,
            directories=[],
            readable=False,
            error=f"Путь не существует: {target}",
        )

    if not target.is_dir():
        return BrowseResult(
            current_path=str(target),
            parent_path=parent,
            directories=[],
            readable=False,
            error=f"Не является папкой: {target}",
        )

    try:
        entries = sorted(
            (
                DirectoryEntry(name=item.name, path=str(item))
                for item in target.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            ),
            key=lambda e: e.name.lower(),
        )
        return BrowseResult(
            current_path=str(target),
            parent_path=parent,
            directories=entries,
            readable=True,
        )
    except PermissionError:
        return BrowseResult(
            current_path=str(target),
            parent_path=parent,
            directories=[],
            readable=False,
            error="Нет доступа к папке",
        )
    except OSError as exc:
        return BrowseResult(
            current_path=str(target),
            parent_path=parent,
            directories=[],
            readable=False,
            error=str(exc),
        )
