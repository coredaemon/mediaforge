from fastapi.testclient import TestClient


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
