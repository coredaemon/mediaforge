from fastapi.testclient import TestClient

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.main import app
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbEpisodeResult, TmdbSearchResult, TmdbSeasonDetailsResult
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


def test_tv_plan_apply_api_applies_safe_tv_operations(client: TestClient, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        tv_results=[TmdbSearchResult(tmdb_id=123, media_type="tv", title="Test Show", year=2024)],
        tv_details={123: TmdbDetailsResult(tmdb_id=123, media_type="tv", title="Test Show", year=2024)},
        tv_season_details={
            (123, 1): TmdbSeasonDetailsResult(
                tmdb_season_id=456,
                season_number=1,
                episodes=[TmdbEpisodeResult(tmdb_episode_id=789, season_number=1, episode_number=1, title="Pilot")],
            )
        },
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    source_path = tmp_path / "inbox"
    target_path = tmp_path / "library"
    (source_path / "Test Show" / "Season 01").mkdir(parents=True)
    target_path.mkdir()
    (source_path / "Test Show" / "Season 01" / "Test Show S01E01.mkv").write_bytes(b"episode")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]
    assert client.post(f"/scan-sessions/{session_id}/discover").status_code == 200
    assert client.post(f"/scan-sessions/{session_id}/parse").status_code == 200
    assert client.post(f"/scan-sessions/{session_id}/analyze-tv").status_code == 200

    shows_response = client.get(f"/scan-sessions/{session_id}/tv-shows")
    assert shows_response.status_code == 200
    show_id = shows_response.json()[0]["id"]
    decision_response = client.post(f"/tv-shows/{show_id}/review-decision", json={"decision": "approved"})
    assert decision_response.status_code == 200

    plan_response = client.post(f"/scan-sessions/{session_id}/plan-tv?force=true")
    assert plan_response.status_code == 200
    plan_id = plan_response.json()["id"]
    apply_response = client.post(f"/operation-plans/{plan_id}/apply", json={"confirm": True})

    assert apply_response.status_code == 200
    result = apply_response.json()
    assert result["status"] == "APPLIED"
    assert result["failed_operations"] == 0
    assert not (source_path / "Test Show" / "Season 01" / "Test Show S01E01.mkv").exists()
    moved_videos = list(target_path.rglob("*.mkv"))
    assert len(moved_videos) == 1
    assert any(path.name == "tvshow.nfo" for path in target_path.rglob("*.nfo"))
    assert moved_videos[0].with_suffix(".nfo").exists()

    second_apply_response = client.post(f"/operation-plans/{plan_id}/apply", json={"confirm": True})
    assert second_apply_response.status_code == 400
    assert "already been applied" in second_apply_response.json()["detail"]

    app.dependency_overrides.pop(get_tmdb_client, None)
