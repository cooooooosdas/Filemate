param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot "filemate\web"
$issues = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Write-Check {
    param([string]$Label, [string]$Value)
    if (-not $Quiet) {
        Write-Host ("[OK] {0}: {1}" -f $Label, $Value) -ForegroundColor Green
    }
}

function Test-PortAvailable {
    param([int]$Port)
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        $listener.Stop()
    }
}

$python = $null
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    }
}

if (-not $python) {
    $issues.Add("Python 3.10+ was not found. Install Python or run uv sync.")
}
else {
    $pythonVersion = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    $pythonSupported = & $python -c "import sys; print(int(sys.version_info >= (3, 10)))"
    if ($pythonSupported -ne "1") {
        $issues.Add("Python $pythonVersion is too old. FileMate requires Python 3.10+.")
    }
    else {
        Write-Check "Python" "$pythonVersion ($python)"
    }

    & $python -c "import fastapi, uvicorn, dotenv" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $issues.Add("Python dependencies are missing. Run scripts/setup-dev.ps1.")
    }
    else {
        Write-Check "Backend dependencies" "FastAPI / Uvicorn / dotenv"
    }
}

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    $issues.Add("Node.js was not found. Use Node.js 20.19+ or 22.12+.")
}
else {
    $nodeVersion = (& node --version).TrimStart("v")
    $nodeMajor = [int]($nodeVersion.Split(".")[0])
    if ($nodeMajor -lt 20) {
        $issues.Add("Node.js $nodeVersion is too old. Use 20.19+ or 22.12+.")
    }
    else {
        Write-Check "Node.js" $nodeVersion
    }
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    $issues.Add("npm was not found.")
}
elseif (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules"))) {
    $issues.Add("Frontend dependencies are missing. Run scripts/setup-dev.ps1.")
}
else {
    Write-Check "Frontend dependencies" "node_modules ready"
}

$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    $warnings.Add(".env is missing. The base UI works, but AI features require an API key.")
}
else {
    $envText = Get-Content -LiteralPath $envPath -Raw -Encoding utf8
    if ($envText -match "sk-x{8,}" -or $envText -notmatch "(?m)^LLM_API_KEY=.+") {
        $warnings.Add("LLM_API_KEY is empty or still a placeholder. AI features are unavailable.")
    }
    else {
        Write-Check "LLM configuration" ".env configured"
    }
}

foreach ($port in @(8001, 5173)) {
    if (Test-PortAvailable -Port $port) {
        Write-Check "Port $port" "available"
    }
    else {
        $warnings.Add("Port $port is in use. Ignore this only when FileMate is already running.")
    }
}

foreach ($warning in $warnings) {
    if (-not $Quiet) {
        Write-Host "[WARN] $warning" -ForegroundColor Yellow
    }
}

if ($issues.Count -gt 0) {
    foreach ($issue in $issues) {
        Write-Host "[ERROR] $issue" -ForegroundColor Red
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host "`nFileMate development environment is ready." -ForegroundColor Green
}
