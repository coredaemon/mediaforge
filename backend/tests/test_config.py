from pathlib import Path

from backend.app.core.config import DEFAULT_DATABASE_PATH, PROJECT_ROOT, Settings


def test_default_database_url_uses_absolute_project_root_path(monkeypatch) -> None:
    monkeypatch.delenv("MEDIAFORGE_DATABASE_URL", raising=False)

    settings = Settings()

    assert DEFAULT_DATABASE_PATH == PROJECT_ROOT / "mediaforge.local.sqlite3"
    assert Path(DEFAULT_DATABASE_PATH).is_absolute()
    assert settings.database_url == f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


def test_database_url_env_override_has_priority(monkeypatch) -> None:
    monkeypatch.setenv("MEDIAFORGE_DATABASE_URL", "sqlite+aiosqlite:////tmp/mediaforge-test.sqlite3")

    settings = Settings()

    assert settings.database_url == "sqlite+aiosqlite:////tmp/mediaforge-test.sqlite3"
