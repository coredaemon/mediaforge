from fastapi.testclient import TestClient

from backend.app.main import _candidate_static_dirs, create_app


def _write_static_dist(root) -> None:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text('<html><head></head><body><div id="root"></div></body></html>', encoding="utf-8")
    (assets / "index-test.js").write_text("console.log('ok');", encoding="utf-8")


def test_default_static_candidates_include_repo_frontend_dist() -> None:
    candidates = _candidate_static_dirs()

    assert any(path.as_posix().endswith("MediaForge/frontend/dist") for path in candidates)


def test_root_returns_frontend_index_when_static_dist_exists(tmp_path, monkeypatch) -> None:
    static_dir = tmp_path / "dist"
    _write_static_dist(static_dir)
    monkeypatch.setenv("MEDIAFORGE_STATIC_DIR", str(static_dir))

    client = TestClient(create_app())
    response = client.get("/", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


def test_spa_route_returns_frontend_index_when_static_dist_exists(tmp_path, monkeypatch) -> None:
    static_dir = tmp_path / "dist"
    _write_static_dist(static_dir)
    monkeypatch.setenv("MEDIAFORGE_STATIC_DIR", str(static_dir))

    client = TestClient(create_app())
    response = client.get("/sessions/1", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


def test_settings_navigation_returns_index_but_health_stays_api(tmp_path, monkeypatch) -> None:
    static_dir = tmp_path / "dist"
    _write_static_dist(static_dir)
    monkeypatch.setenv("MEDIAFORGE_STATIC_DIR", str(static_dir))

    client = TestClient(create_app())
    settings_response = client.get("/settings", headers={"accept": "text/html"})
    health_response = client.get("/health", headers={"accept": "text/html"})

    assert settings_response.status_code == 200
    assert '<div id="root"></div>' in settings_response.text
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "app": "MediaForge"}


def test_frontend_assets_are_served(tmp_path, monkeypatch) -> None:
    static_dir = tmp_path / "dist"
    _write_static_dist(static_dir)
    monkeypatch.setenv("MEDIAFORGE_STATIC_DIR", str(static_dir))

    client = TestClient(create_app())
    response = client.get("/assets/index-test.js")

    assert response.status_code == 200
    assert "console.log('ok');" in response.text
