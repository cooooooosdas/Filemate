$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

# 项目被移动到其他盘并通过目录联接访问时，Vite/Rolldown 会拿到真实绝对路径，
# 导致 build 报错；统一切换到真实路径后再执行命令。
$rootItem = Get-Item -LiteralPath $projectRoot -Force
if ($rootItem.LinkType -eq 'Junction' -and $rootItem.Target) {
    $projectRoot = [string]$rootItem.Target
}

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Push-Location $projectRoot
try {
    uv sync --extra dev
    Assert-LastExitCode "uv sync"
    uv run ruff check server.py main.py filemate/execution `
        filemate/tests/test_storage.py `
        filemate/tests/test_file_ops.py `
        filemate/tests/test_archiver.py `
        filemate/tests/test_confirmation_executor.py `
        filemate/tests/test_server_persistence.py `
        filemate/tests/test_retrieval.py `
        filemate/tests/test_study.py `
        filemate/study `
        filemate/understanding/interview.py `
        filemate/understanding/retrieval.py `
        evaluation/run_evaluation.py `
        evaluation/analyze_study.py `
        evaluation/analyze_feedback.py
    Assert-LastExitCode "Ruff"
    uv run pytest filemate/tests -q -m "not e2e"
    Assert-LastExitCode "pytest"

    $realRoot = Split-Path -Parent $PSScriptRoot
    $realItem = Get-Item -LiteralPath $realRoot -Force
    if ($realItem.LinkType -eq 'Junction' -and $realItem.Target) {
        $realRoot = [string]$realItem.Target
    }
    Push-Location (Join-Path $realRoot "filemate/web")
    try {
        npm.cmd ci
        Assert-LastExitCode "npm ci"
        npm.cmd run build
        Assert-LastExitCode "frontend build"
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
