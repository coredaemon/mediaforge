"""Tests for path validation in the scan-session creation HTTP route."""

from fastapi.testclient import TestClient


def test_create_session_rejects_identical_source_and_target(client: TestClient, tmp_path) -> None:
    folder = tmp_path / "media"
    folder.mkdir()

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(folder), "target_path": str(folder)},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "совпадают" in detail.lower() or "одинаков" in detail.lower()


def test_create_session_rejects_same_paths_with_mixed_slashes(client: TestClient, tmp_path) -> None:
    r"""D:/Foo and D:\Foo should be treated as the same path."""
    folder = tmp_path / "media"
    folder.mkdir()

    # Build path strings with both slash styles pointing to the same dir.
    path_forward = str(folder).replace("\\", "/")
    path_back = str(folder).replace("/", "\\")

    response = client.post(
        "/scan-sessions",
        json={"source_path": path_forward, "target_path": path_back},
    )

    assert response.status_code == 400
    assert "совпадают" in response.json()["detail"].lower()


def test_create_session_rejects_nonexistent_source(client: TestClient, tmp_path) -> None:
    target = tmp_path / "library"
    target.mkdir()
    nonexistent = tmp_path / "does_not_exist"

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(nonexistent), "target_path": str(target)},
    )

    assert response.status_code == 400
    assert "не найдена" in response.json()["detail"].lower()


def test_create_session_rejects_nonexistent_target(client: TestClient, tmp_path) -> None:
    source = tmp_path / "inbox"
    source.mkdir()
    nonexistent = tmp_path / "does_not_exist"

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(nonexistent)},
    )

    assert response.status_code == 400
    assert "не найдена" in response.json()["detail"].lower()


def test_create_session_accepts_windows_backslash_paths(client: TestClient, tmp_path) -> None:
    """Backend must accept paths with backslashes (Windows style)."""
    source = tmp_path / "Фильмы"
    source.mkdir()
    target = tmp_path / "Медиатека"
    target.mkdir()

    # Use backslashes explicitly.
    source_bs = str(source).replace("/", "\\")
    target_bs = str(target).replace("/", "\\")

    response = client.post(
        "/scan-sessions",
        json={"source_path": source_bs, "target_path": target_bs},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CREATED"


def test_create_session_accepts_cyrillic_paths(client: TestClient, tmp_path) -> None:
    """Backend must handle Cyrillic directory names without errors."""
    source = tmp_path / "Входящие"
    source.mkdir()
    target = tmp_path / "Библиотека"
    target.mkdir()

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CREATED"
    # Paths stored in DB should contain the Cyrillic names.
    assert "Входящие" in data["source_path"] or "Библиотека" in data["target_path"]
