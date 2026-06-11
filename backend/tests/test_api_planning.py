from fastapi.testclient import TestClient

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.main import app
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.tests.fakes import FakeTmdbClient


def test_scan_session_plan_api_flow(client: TestClient, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                poster_path="/matrix-poster.jpg",
            )
        ],
        tv_results=[TmdbSearchResult(tmdb_id=40008, media_type="tv", title="Hannibal", year=2013)],
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    matrix_source = source_path / "The.Matrix.1999.mkv"
    hannibal_source = source_path / "Hannibal.S01E01.mkv"
    matrix_source.write_bytes(b"movie")
    hannibal_source.write_bytes(b"episode")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")
    client.post(f"/scan-sessions/{session_id}/parse")
    client.post(f"/scan-sessions/{session_id}/match-tmdb")

    plan_response = client.post(f"/scan-sessions/{session_id}/plan")
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["status"] == "READY"
    assert plan["scan_session_id"] == session_id

    plans_response = client.get(f"/scan-sessions/{session_id}/plans")
    assert plans_response.status_code == 200
    assert len(plans_response.json()) == 1

    get_plan_response = client.get(f"/operation-plans/{plan['id']}")
    assert get_plan_response.status_code == 200
    assert get_plan_response.json()["id"] == plan["id"]

    operations_response = client.get(f"/operation-plans/{plan['id']}/operations")
    assert operations_response.status_code == 200
    operations = operations_response.json()
    operation_types = {operation["operation_type"] for operation in operations}
    assert operation_types == {"CREATE_DIR", "MOVE_FILE", "WRITE_TEXT_FILE", "DOWNLOAD_FILE"}
    assert matrix_source.exists()
    assert hannibal_source.exists()
    movie_move_targets = [
        operation["target_path"]
        for operation in operations
        if operation["operation_type"] == "MOVE_FILE" and "The Matrix" in operation["target_path"]
    ]
    assert movie_move_targets
    assert "/Movies/" not in movie_move_targets[0].replace("\\", "/")

    app.dependency_overrides.pop(get_tmdb_client, None)


def test_create_plan_without_matched_items_returns_400(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]

    response = client.post(f"/scan-sessions/{session_id}/plan")

    assert response.status_code == 400
    assert "no matched media items" in response.json()["detail"].lower()
