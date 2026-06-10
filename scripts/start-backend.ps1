$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Initializing database..."
python -m backend.scripts.init_db

Write-Host "Starting backend on http://127.0.0.1:8000"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
