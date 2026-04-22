$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Resolve-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = "py"; Args = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = "python"; Args = @() }
    }
    throw "Python not found. Please install Python 3.10+ and add it to PATH."
}

$pythonCmd = Resolve-Python

if (!(Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    & $pythonCmd.Exe @($pythonCmd.Args + @("-m", "venv", ".venv"))
}

Write-Host "Installing dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r .\requirements.txt

if (!(Test-Path "config")) {
    New-Item -ItemType Directory -Path "config" | Out-Null
}

if (!(Test-Path "config\global.env")) {
    Copy-Item "config\global.env.example" "config\global.env"
    Write-Host "Created config\global.env"
}

if (!(Test-Path "config\fishc.env")) {
    Copy-Item "config\fishc.env.example" "config\fishc.env"
    Write-Host "Created config\fishc.env"
}

$dirs = @("data", "data\status", "data\history", "data\logs", "data\locks", "tests\unit", "tests\integration", "tests\fixtures")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

Write-Host "Installing scheduled tasks for fishc..."
& ".\.venv\Scripts\python.exe" -m app.main install-task --site fishc

Write-Host ""
Write-Host "Install completed."
Write-Host "1) Fill config\fishc.env with your account/cookie"
Write-Host "2) Test run: .\run_now.bat"
Write-Host "3) Health check: powershell -File .\scripts\doctor.ps1"
