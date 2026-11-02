param([switch]$CheckRecordedEvidence,[switch]$RecordEvidence)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  $env:PYTHONUTF8='1'
  if($CheckRecordedEvidence){
    & .venv/Scripts/python.exe -m scripts.acceptance.wrongbook_learning_evidence
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
    Push-Location filemate/web
    try { npm.cmd test; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE} } finally {Pop-Location}
  } elseif($RecordEvidence){
    & .venv/Scripts/python.exe -m scripts.acceptance.wrongbook_learning_evidence --record
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  } else {
    & .venv/Scripts/python.exe -m ruff check scripts/acceptance/wrongbook_learning_fixture.py scripts/acceptance/wrongbook_learning_evidence.py
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
    Write-Output 'Full gate passed. Run the documented isolated browser fixture and both flag builds before -RecordEvidence.'
  }
} finally {Pop-Location}
