from pathlib import Path

from backend.app.services.filesystem_service import browse_directory, get_filesystem_roots


def test_roots_returns_non_empty_list() -> None:
    roots = get_filesystem_roots()

    assert len(roots) > 0
    assert all(isinstance(r, str) for r in roots)


def test_browse_tmp_path_returns_subdirectories(tmp_path: Path) -> None:
    (tmp_path / "movies").mkdir()
    (tmp_path / "shows").mkdir()
    (tmp_path / "hidden").mkdir()

    result = browse_directory(str(tmp_path))

    assert result.readable is True
    assert result.error is None
    names = {entry.name for entry in result.directories}
    assert "movies" in names
    assert "shows" in names


def test_browse_returns_full_paths_in_entries(tmp_path: Path) -> None:
    sub = tmp_path / "subfolder"
    sub.mkdir()

    result = browse_directory(str(tmp_path))

    found = next((e for e in result.directories if e.name == "subfolder"), None)
    assert found is not None
    assert Path(found.path) == sub.resolve()


def test_browse_non_existent_path_returns_controlled_error() -> None:
    result = browse_directory("/this/path/does/not/exist/xyz123")

    assert result.readable is False
    assert result.error is not None
    assert result.directories == []


def test_browse_file_path_returns_error(tmp_path: Path) -> None:
    file_path = tmp_path / "test.txt"
    file_path.write_text("data")

    result = browse_directory(str(file_path))

    assert result.readable is False
    assert result.error is not None


def test_browse_sets_parent_path(tmp_path: Path) -> None:
    sub = tmp_path / "child"
    sub.mkdir()

    result = browse_directory(str(sub))

    assert result.parent_path is not None
    assert Path(result.parent_path) == tmp_path.resolve()


def test_browse_current_path_is_resolved(tmp_path: Path) -> None:
    result = browse_directory(str(tmp_path))

    assert Path(result.current_path) == tmp_path.resolve()
