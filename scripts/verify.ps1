param(
    [switch]$IsolateFrontend
)

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
    $frontendRoot = Join-Path $realRoot "filemate/web"
    if ($IsolateFrontend) {
        # Keep npm ci away from native binaries locked by a running Windows Vite process.
        $frontendCopy = Join-Path $realRoot ("_working/verify-web-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $frontendCopy | Out-Null
        foreach ($folder in @("src", "public", "tests")) {
            $sourceFolder = Join-Path $frontendRoot $folder
            if (Test-Path -LiteralPath $sourceFolder) {
                Copy-Item -LiteralPath $sourceFolder -Destination $frontendCopy -Recurse
            }
        }
        foreach ($file in @("package.json", "package-lock.json", "index.html", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", "env.d.ts")) {
            $sourceFile = Join-Path $frontendRoot $file
            if (Test-Path -LiteralPath $sourceFile) {
                Copy-Item -LiteralPath $sourceFile -Destination $frontendCopy
            }
        }
        Write-Output "Frontend verification workspace: $frontendCopy"
        $frontendRoot = $frontendCopy
    }
    Push-Location $frontendRoot
    try {
        npm.cmd ci
        Assert-LastExitCode "npm ci"
        npm.cmd test
        Assert-LastExitCode "frontend tests"
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
