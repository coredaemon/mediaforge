"""Tests for path validation in the scan-session creation HTTP route."""

import pytest
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
    # Message uses verb stem "совпадат" covering both "совпадают" and "совпадать".
    assert "совпадат" in detail.lower() or "одинаков" in detail.lower()


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
    assert "совпадат" in response.json()["detail"].lower()


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


# ---------------------------------------------------------------------------
# Nested path validation tests
# ---------------------------------------------------------------------------


def test_create_session_rejects_target_inside_source(client: TestClient, tmp_path) -> None:
    """target_path that is a subdirectory of source_path must be rejected."""
    source = tmp_path / "Фильмы"
    source.mkdir()
    target = source / "Медиасервер"
    target.mkdir()

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "медиатеки находится внутри" in detail or "внутри папки с файлами" in detail


def test_create_session_rejects_target_inside_source_mixed_slashes(client: TestClient, tmp_path) -> None:
    """Mixed forward/back slashes must still trigger nested-path rejection."""
    source = tmp_path / "Фильмы"
    source.mkdir()
    target = source / "Медиасервер"
    target.mkdir()

    source_fwd = str(source).replace("\\", "/")
    target_back = str(target).replace("/", "\\")

    response = client.post(
        "/scan-sessions",
        json={"source_path": source_fwd, "target_path": target_back},
    )

    assert response.status_code == 400


def test_create_session_rejects_source_inside_target(client: TestClient, tmp_path) -> None:
    """source_path that is a subdirectory of target_path must be rejected."""
    target = tmp_path / "Библиотека"
    target.mkdir()
    source = target / "Входящие"
    source.mkdir()

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "файлами находится внутри" in detail or "внутри папки медиатеки" in detail


def test_create_session_accepts_sibling_folders(client: TestClient, tmp_path) -> None:
    """Two sibling folders (same parent, different names) must be accepted."""
    source = tmp_path / "Исходники"
    source.mkdir()
    target = tmp_path / "Медиатека"
    target.mkdir()

    response = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CREATED"


def test_create_session_accepts_cyrillic_sibling_folders(client: TestClient, tmp_path) -> None:
    """Cyrillic sibling folders with backslash paths must be accepted."""
    source = tmp_path / "Фильмы"
    source.mkdir()
    target = tmp_path / "Медиасервер"
    target.mkdir()

    source_bs = str(source).replace("/", "\\")
    target_bs = str(target).replace("/", "\\")

    response = client.post(
        "/scan-sessions",
        json={"source_path": source_bs, "target_path": target_bs},
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Empty-collection endpoint tests (no 500 when session has no data)
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_session(client: TestClient, tmp_path):
    """Create a session with two sibling folders but no media files."""
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    resp = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_get_session_without_data_returns_200(client: TestClient, empty_session: int) -> None:
    """`GET /scan-sessions/{id}` must succeed even when no files/items/plans exist."""
    response = client.get(f"/scan-sessions/{empty_session}")
    assert response.status_code == 200
    assert response.json()["id"] == empty_session


def test_list_files_empty_returns_empty_list(client: TestClient, empty_session: int) -> None:
    """`GET /scan-sessions/{id}/files` returns [] when no files have been scanned."""
    response = client.get(f"/scan-sessions/{empty_session}/files")
    assert response.status_code == 200
    assert response.json() == []


def test_list_items_empty_returns_empty_list(client: TestClient, empty_session: int) -> None:
    """`GET /scan-sessions/{id}/items` returns [] when no items have been parsed."""
    response = client.get(f"/scan-sessions/{empty_session}/items")
    assert response.status_code == 200
    assert response.json() == []


def test_list_plans_empty_returns_empty_list(client: TestClient, empty_session: int) -> None:
    """`GET /scan-sessions/{id}/plans` returns [] when no plans have been created."""
    response = client.get(f"/scan-sessions/{empty_session}/plans")
    assert response.status_code == 200
    assert response.json() == []


def test_get_nonexistent_session_returns_404(client: TestClient) -> None:
    """`GET /scan-sessions/99999` must return 404 with a descriptive message."""
    response = client.get("/scan-sessions/99999")
    assert response.status_code == 404
    assert "не найдена" in response.json()["detail"].lower() or "not found" in response.json()["detail"].lower()
