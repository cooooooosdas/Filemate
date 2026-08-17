param(
    [switch]$Setup,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot "filemate\web"
$workingRoot = Join-Path $projectRoot "_working"
$processFile = Join-Path $workingRoot "dev-processes.json"

if ($Setup) {
    & (Join-Path $PSScriptRoot "setup-dev.ps1")
}

& (Join-Path $PSScriptRoot "doctor.ps1") -Quiet
if ($LASTEXITCODE -ne 0) {
    throw "Environment check failed. First run: powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup"
}

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $backendProgram = $venvPython
    $backendArguments = @("server.py")
}
elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $backendProgram = (Get-Command uv).Source
    $backendArguments = @("run", "python", "server.py")
}
else {
    $backendProgram = (Get-Command python).Source
    $backendArguments = @("server.py")
}

if (-not (Test-Path -LiteralPath $workingRoot)) {
    New-Item -ItemType Directory -Path $workingRoot | Out-Null
}

Write-Host "[1/3] Starting FastAPI: http://127.0.0.1:8001" -ForegroundColor Cyan
$backend = Start-Process `
    -FilePath $backendProgram `
    -ArgumentList $backendArguments `
    -WorkingDirectory $projectRoot `
    -PassThru

$backendReady = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($backend.HasExited) {
        throw "Backend exited early with code $($backend.ExitCode)."
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/" -TimeoutSec 1
        if ($health.version) {
            $backendReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $backendReady) {
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    throw "Backend was not ready in 20 seconds. Run python server.py to inspect logs."
}

Write-Host "[2/3] Starting Vue: http://127.0.0.1:5173" -ForegroundColor Cyan
$viteEntry = Join-Path $webRoot "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $viteEntry)) {
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    throw "Vite entry was not found. Run scripts/setup-dev.ps1 first."
}
$frontend = Start-Process `
    -FilePath (Get-Command node).Source `
    -ArgumentList @($viteEntry, "--host", "127.0.0.1") `
    -WorkingDirectory $webRoot `
    -PassThru

$frontendReady = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($frontend.HasExited) {
        Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
        throw "Frontend exited early with code $($frontend.ExitCode)."
    }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -TimeoutSec 1 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $frontendReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $frontendReady) {
    Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    throw "Frontend was not ready in 20 seconds. Run npm run dev in filemate/web to inspect logs."
}

@{
    backend = $backend.Id
    frontend = $frontend.Id
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8

Write-Host "[3/3] FileMate is ready." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend docs: http://127.0.0.1:8001/docs"
Write-Host "Stop: powershell -ExecutionPolicy Bypass -File scripts/stop-dev.ps1"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:5173"
}
