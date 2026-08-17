$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot "filemate\web"

Push-Location $projectRoot
try {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "[1/2] Installing Python dependencies with uv..." -ForegroundColor Cyan
        uv sync --extra dev
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            throw "Python 3.10+ was not found. Install Python or uv first."
        }
        if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
            & $python.Source -m venv .venv
        }
        Write-Host "[1/2] Installing Python dependencies with pip..." -ForegroundColor Cyan
        & ".venv\Scripts\python.exe" -m pip install --upgrade pip
        & ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
    }

    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js first."
    }
    Write-Host "[2/2] Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location $webRoot
    try {
        npm.cmd ci
    }
    finally {
        Pop-Location
    }

    & (Join-Path $PSScriptRoot "doctor.ps1")
}
finally {
    Pop-Location
}
