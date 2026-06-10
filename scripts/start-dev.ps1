$ScriptDir = $PSScriptRoot

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $ScriptDir "start-backend.ps1")
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $ScriptDir "start-frontend.ps1")
)

Write-Host ""
Write-Host "MediaForge dev servers are starting in separate windows."
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host ""
