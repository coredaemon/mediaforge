# MediaForge Launcher

`MediaForge Launcher.exe` is a small Windows launcher for a prepared MediaForge project folder.

It starts the FastAPI backend, waits for `/health`, opens the browser, shows a simple status window, and stops the backend process it started.

This is not a full installer yet. The launcher expects to run inside or next to a prepared repository/release folder that contains the backend code, frontend build output, and Python dependencies.

## Build

From the repository root:

```powershell
.\scripts\build-launcher.ps1
```

The script builds `frontend/dist`, installs PyInstaller if needed, and writes:

```text
dist/MediaForge Launcher/MediaForge Launcher.exe
```

The generated `dist/` and `build/` folders are local artifacts and are not committed.

## Runtime

Default URL:

```text
http://127.0.0.1:8765/
```

Launcher log:

```text
%LOCALAPPDATA%\MediaForge\logs\launcher.log
```

Optional environment variables:

- `MEDIAFORGE_PROJECT_ROOT`: explicit project root.
- `MEDIAFORGE_LAUNCHER_LOG`: explicit launcher log file.

