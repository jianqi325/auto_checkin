param(
    [ValidateSet("fishc")]
    [string]$Site = "fishc"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$pythonExe = Join-Path $PWD ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $pythonExe)) {
    Write-Error "Virtual environment not found. Run .\install.bat first."
    exit 1
}

& $pythonExe -m app.main doctor --site $Site
exit $LASTEXITCODE
