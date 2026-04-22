param(
    [ValidateSet("fishc")]
    [string]$Site = "fishc",
    [string]$Trigger = "manual",
    [switch]$FallbackIfMissed,
    [string]$ScheduledTime = "09:05"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$pythonExe = Join-Path $PWD ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $pythonExe)) {
    Write-Error "Virtual environment not found. Run .\install.bat first."
    exit 1
}

$args = @("-m", "app.main", "run", "--site", $Site, "--trigger", $Trigger)
if ($FallbackIfMissed) {
    $args += @("--fallback-if-missed", "--scheduled-time", $ScheduledTime)
}

& $pythonExe @args
exit $LASTEXITCODE
