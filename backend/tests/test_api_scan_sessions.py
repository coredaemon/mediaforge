from fastapi.testclient import TestClient

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.main import app
from backend.tests.fakes import FakeTmdbClient


def test_scan_session_api_flow(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "Movie.1999.mkv").write_bytes(b"video")
    (source_path / "Movie.1999.srt").write_text("subtitle", encoding="utf-8")
    (source_path / "movie.nfo").write_text("metadata", encoding="utf-8")
    (source_path / "readme.txt").write_text("notes", encoding="utf-8")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["status"] == "CREATED"

    list_response = client.get("/scan-sessions")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/scan-sessions/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]

    discover_response = client.post(f"/scan-sessions/{created['id']}/discover")
    assert discover_response.status_code == 200
    assert discover_response.json()["status"] == "DISCOVERED"

    files_response = client.get(f"/scan-sessions/{created['id']}/files")
    assert files_response.status_code == 200
    files = files_response.json()
    assert len(files) == 4
    assert {media_file["file_name"]: media_file["kind"] for media_file in files} == {
        "Movie.1999.mkv": "VIDEO",
        "Movie.1999.srt": "SUBTITLE",
        "movie.nfo": "SIDECAR",
        "readme.txt": "OTHER",
    }


def test_scan_session_parse_api_flow(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.1080p.BluRay.x264.mkv").write_bytes(b"video")
    (source_path / "The.Matrix.1999.srt").write_text("subtitle", encoding="utf-8")
    (source_path / "Hannibal.S01E01.mkv").write_bytes(b"video")
    (source_path / "readme.txt").write_text("notes", encoding="utf-8")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")

    parse_response = client.post(f"/scan-sessions/{session_id}/parse")
    assert parse_response.status_code == 200
    assert parse_response.json()["status"] == "PARSED"

    items_response = client.get(f"/scan-sessions/{session_id}/items")
    assert items_response.status_code == 200
    items = items_response.json()
    assert len(items) == 2
    assert {item["parsed_title"]: item["media_type"] for item in items} == {
        "The Matrix": "MOVIE",
        "Hannibal": "TV_EPISODE",
    }


def test_scan_session_tmdb_match_api_flow(client: TestClient, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(tmdb_id=603, media_type="movie", title="The Matrix", year=1999, popularity=80)
        ],
        tv_results=[TmdbSearchResult(tmdb_id=40008, media_type="tv", title="Hannibal", year=2013, popularity=60)],
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.mkv").write_bytes(b"video")
    (source_path / "Hannibal.S01E01.mkv").write_bytes(b"video")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")
    client.post(f"/scan-sessions/{session_id}/parse")

    match_response = client.post(f"/scan-sessions/{session_id}/match-tmdb")
    assert match_response.status_code == 200
    assert match_response.json()["matched_count"] == 2

    items_response = client.get(f"/scan-sessions/{session_id}/items")
    items = items_response.json()
    matrix_item = next(item for item in items if item["parsed_title"] == "The Matrix")
    assert matrix_item["status"] == "MATCHED"
    assert matrix_item["tmdb_id"] == 603

    candidates_response = client.get(f"/items/{matrix_item['id']}/tmdb-candidates")
    assert candidates_response.status_code == 200
    candidates = candidates_response.json()
    assert len(candidates) == 1
    assert candidates[0]["is_selected"]
    app.dependency_overrides.pop(get_tmdb_client, None)


def test_tmdb_match_without_api_key_returns_400(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]

    response = client.post(f"/scan-sessions/{session_id}/match-tmdb")

    assert response.status_code == 400
    assert response.json()["detail"] == "TMDB_API_KEY is not configured"
