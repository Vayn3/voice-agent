param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $Root "frontend"

Write-Host "Starting Voice TA development services..."

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "frontend/node_modules not found. Running npm install first..."
    Push-Location $FrontendDir
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

$BackendCommand = "cd /d `"$Root`" && conda run -n voiceTA python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $BackendPort"
$FrontendCommand = "cd /d `"$FrontendDir`" && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$BackendPort&& npm run dev -- --port $FrontendPort"

Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $BackendCommand -WindowStyle Normal
Start-Sleep -Seconds 1
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $FrontendCommand -WindowStyle Normal

Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Close the two opened terminal windows, or run scripts/stop-dev.ps1, to stop the services."
