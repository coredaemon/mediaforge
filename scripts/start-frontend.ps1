$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"
Set-Location $FrontendRoot

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    npm install
}

Write-Host "Starting frontend on http://127.0.0.1:5173"
if (-not $env:VITE_API_BASE_URL) {
    $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
}
npm run dev -- --host 127.0.0.1 --port 5173
