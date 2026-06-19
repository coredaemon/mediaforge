$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$LauncherEntry = Join-Path $ProjectRoot "launcher\mediaforge_launcher.py"
$SpecPath = Join-Path $ProjectRoot "build\launcher-spec"
$WorkPath = Join-Path $ProjectRoot "build\pyinstaller"
$DistPath = Join-Path $ProjectRoot "dist"

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "python")) {
    throw "Python is not available on PATH."
}
if (-not (Test-Command "npm")) {
    throw "Node/npm is not available on PATH."
}

Write-Host "Installing frontend dependencies if needed..."
Push-Location $FrontendRoot
try {
    if (-not (Test-Path "node_modules")) {
        npm ci
    }
    Write-Host "Building frontend for same-origin backend serving..."
    $previousApiBase = $env:VITE_API_BASE_URL
    $env:VITE_API_BASE_URL = ""
    npm run build
}
finally {
    $env:VITE_API_BASE_URL = $previousApiBase
    Pop-Location
}

Write-Host "Ensuring PyInstaller is installed..."
python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    python -m pip install pyinstaller
}

Write-Host "Building MediaForge Launcher.exe..."
New-Item -ItemType Directory -Force -Path $SpecPath, $WorkPath, $DistPath | Out-Null
Push-Location $ProjectRoot
try {
    python -m PyInstaller `
        --noconfirm `
        --windowed `
        --name "MediaForge Launcher" `
        --specpath $SpecPath `
        --workpath $WorkPath `
        --distpath $DistPath `
        $LauncherEntry
}
finally {
    Pop-Location
}

$ExePath = Join-Path $DistPath "MediaForge Launcher\MediaForge Launcher.exe"
if (-not (Test-Path $ExePath)) {
    throw "Launcher build finished, but exe was not found: $ExePath"
}

Write-Host "Launcher built: $ExePath"
