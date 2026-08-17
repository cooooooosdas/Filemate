$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot "_working\dev-processes.json"

if (-not (Test-Path -LiteralPath $processFile)) {
    Write-Host "No FileMate development process record was found." -ForegroundColor Yellow
    exit 0
}

$record = Get-Content -LiteralPath $processFile -Raw -Encoding utf8 | ConvertFrom-Json
foreach ($processId in @($record.frontend, $record.backend)) {
    if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $processId
        Write-Host "Stopped process $processId." -ForegroundColor Green
    }
}

Remove-Item -LiteralPath $processFile
