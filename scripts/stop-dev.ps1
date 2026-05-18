$ErrorActionPreference = "SilentlyContinue"

$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*backend.app.main:app*" -or
    $_.CommandLine -like "*Voice-TA*frontend*next*" -or
    $_.CommandLine -like "*Voice-TA*frontend*npm run dev*" -or
    $_.CommandLine -like "*NEXT_PUBLIC_API_BASE_URL*Voice-TA*"
}

if (-not $targets) {
    Write-Host "No Voice TA development services found."
    exit 0
}

$targets | ForEach-Object {
    Write-Host "Stopping $($_.Name) pid=$($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force
}

Write-Host "Voice TA development services stopped."
