from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HEALTH_PATH = "/health"


@dataclass(frozen=True)
class BackendCommand:
    args: list[str]
    cwd: Path
    env: dict[str, str]


def find_free_port(host: str = DEFAULT_HOST, preferred_port: int = DEFAULT_PORT) -> int:
    if preferred_port > 0 and _port_available(host, preferred_port):
        return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def backend_health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}{HEALTH_PATH}"


def ui_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def check_health(host: str, port: int, timeout: float = 1.0) -> bool:
    request = urllib.request.Request(backend_health_url(host, port), headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def wait_for_health(
    host: str,
    port: int,
    *,
    timeout_seconds: float = 30.0,
    interval_seconds: float = 0.5,
    logger: logging.Logger | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        healthy = check_health(host, port)
        if logger:
            logger.info("Health check attempt %s for %s: %s", attempt, backend_health_url(host, port), healthy)
        if healthy:
            return True
        time.sleep(interval_seconds)
    return False


def detect_running_backend(host: str, port: int) -> bool:
    return check_health(host, port, timeout=0.5)


def log_path() -> Path:
    configured = os.getenv("MEDIAFORGE_LAUNCHER_LOG")
    if configured:
        path = Path(configured)
    else:
        local_app_data = os.getenv("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.cwd()
        path = base / "MediaForge" / "logs" / "launcher.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def configure_logger(path: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("mediaforge.launcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(path or log_path(), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def find_project_root(start: Path | None = None) -> Path:
    configured = os.getenv("MEDIAFORGE_PROJECT_ROOT")
    if configured:
        root = Path(configured).resolve()
        if _looks_like_project_root(root):
            return root
        raise FileNotFoundError(f"MEDIAFORGE_PROJECT_ROOT does not look like MediaForge root: {root}")

    starts = []
    if start is not None:
        starts.append(start.resolve())
    if getattr(sys, "frozen", False):
        starts.append(Path(sys.executable).resolve())
    starts.extend([Path.cwd().resolve(), Path(__file__).resolve()])

    for candidate_start in starts:
        for candidate in [candidate_start, *candidate_start.parents]:
            if _looks_like_project_root(candidate):
                return candidate
    raise FileNotFoundError("Could not find MediaForge project root")


def _looks_like_project_root(path: Path) -> bool:
    return (path / "backend" / "app" / "main.py").is_file() and (path / "frontend").is_dir()


def resolve_python_executable(project_root: Path) -> str:
    candidates = [
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    if not getattr(sys, "frozen", False):
        return sys.executable
    return "python"


def build_backend_command(
    project_root: Path,
    host: str,
    port: int,
    *,
    python_executable: str | None = None,
) -> BackendCommand:
    python = python_executable or resolve_python_executable(project_root)
    env = os.environ.copy()
    env["MEDIAFORGE_HOST"] = host
    env["MEDIAFORGE_PORT"] = str(port)
    return BackendCommand(
        args=[
            python,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=project_root,
        env=env,
    )


def start_backend(command: BackendCommand, log_file: Path, logger: logging.Logger | None = None) -> subprocess.Popen:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    stream = log_file.open("a", encoding="utf-8", buffering=1)
    if logger:
        logger.info("Starting backend: %s", " ".join(command.args))
        logger.info("Backend cwd: %s", command.cwd)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        command.args,
        cwd=str(command.cwd),
        env=command.env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )


def stop_process(process: subprocess.Popen | None, logger: logging.Logger | None = None, timeout: float = 8.0) -> None:
    if process is None or process.poll() is not None:
        return
    if logger:
        logger.info("Stopping backend process pid=%s", process.pid)
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if logger:
            logger.warning("Backend did not stop after %.1fs; killing pid=%s", timeout, process.pid)
        process.kill()
        process.wait(timeout=timeout)
    if logger:
        logger.info("Backend process exit code: %s", process.returncode)
