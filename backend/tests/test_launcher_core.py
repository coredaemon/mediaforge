import logging
from pathlib import Path

from launcher import core


def test_find_free_port_prefers_available_port() -> None:
    port = core.find_free_port(preferred_port=0)

    assert isinstance(port, int)
    assert port > 0


def test_backend_command_uses_project_module_and_port(tmp_path: Path) -> None:
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()

    command = core.build_backend_command(tmp_path, "127.0.0.1", 8765, python_executable="python-test")

    assert command.cwd == tmp_path
    assert command.args == [
        "python-test",
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert command.env["MEDIAFORGE_PORT"] == "8765"


def test_log_path_creates_parent_from_env(tmp_path: Path, monkeypatch) -> None:
    expected = tmp_path / "logs" / "launcher.log"
    monkeypatch.setenv("MEDIAFORGE_LAUNCHER_LOG", str(expected))

    path = core.log_path()

    assert path == expected
    assert expected.parent.is_dir()


def test_find_project_root_uses_env(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    monkeypatch.setenv("MEDIAFORGE_PROJECT_ROOT", str(tmp_path))

    assert core.find_project_root() == tmp_path.resolve()


def test_wait_for_health_success_and_failure(monkeypatch) -> None:
    attempts = iter([False, True])
    monkeypatch.setattr(core, "check_health", lambda host, port: next(attempts))

    assert core.wait_for_health("127.0.0.1", 8765, timeout_seconds=1, interval_seconds=0) is True

    monkeypatch.setattr(core, "check_health", lambda host, port: False)
    assert core.wait_for_health("127.0.0.1", 8765, timeout_seconds=0.01, interval_seconds=0) is False


def test_detect_running_backend_uses_health(monkeypatch) -> None:
    monkeypatch.setattr(core, "check_health", lambda host, port, timeout=0.5: True)

    assert core.detect_running_backend("127.0.0.1", 8765) is True


def test_configure_logger_writes_log_file(tmp_path: Path) -> None:
    path = tmp_path / "launcher.log"
    logger = core.configure_logger(path)
    logger.info("hello launcher")
    for handler in logger.handlers:
        handler.flush()

    assert "hello launcher" in path.read_text(encoding="utf-8")
    assert isinstance(logger, logging.Logger)
