$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$pythonExe = Join-Path $PWD ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $pythonExe) {
    & $pythonExe -m app.main remove-task --site fishc
}
else {
    Write-Host "Virtual environment not found, skip CLI task removal."
    schtasks /Delete /TN "FISHC-Checkin-Daily" /F 2>$null | Out-Null
    schtasks /Delete /TN "FISHC-Checkin-LogonFallback" /F 2>$null | Out-Null
}

Write-Host "Removing legacy tasks if present..."
schtasks /Delete /TN "FISHC-Auto-Checkin" /F 2>$null | Out-Null
schtasks /Delete /TN "FISHC-Auto-Checkin-LogonFallback" /F 2>$null | Out-Null
schtasks /Delete /TN "BBXY-Auto-Checkin" /F 2>$null | Out-Null
schtasks /Delete /TN "BBXY-Auto-Checkin-LogonFallback" /F 2>$null | Out-Null

Write-Host "Cleaning runtime artifacts..."
if (Test-Path ".venv") { Remove-Item -LiteralPath ".venv" -Recurse -Force }
if (Test-Path "data\locks") { Remove-Item -LiteralPath "data\locks\*" -Force -ErrorAction SilentlyContinue }

Write-Host "Uninstall done."
