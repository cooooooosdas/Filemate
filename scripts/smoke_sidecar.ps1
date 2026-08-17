param(
    [string]$BinaryPath = "",
    [string]$EvidencePath = "",
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$tauriRoot = Join-Path $projectRoot "filemate\web\src-tauri"
$runId = [guid]::NewGuid().ToString("N")
$workingDir = Join-Path $projectRoot "_working\sidecar-smoke\$runId"
$dataDir = Join-Path $workingDir "data"
$archiveDir = Join-Path $workingDir "archive"
$stdoutPath = Join-Path $workingDir "sidecar.stdout.log"
$stderrPath = Join-Path $workingDir "sidecar.stderr.log"
$shutdownToken = [guid]::NewGuid().ToString("N")
$process = $null

if (-not $BinaryPath) {
    $binary = Get-ChildItem -LiteralPath (Join-Path $tauriRoot "binaries") `
        -Filter "filemate-server-*.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $binary) {
        throw "FileMate sidecar was not found. Run npm run desktop:sidecar first."
    }
    $BinaryPath = $binary.FullName
}

$BinaryPath = (Resolve-Path -LiteralPath $BinaryPath).Path
if (-not $EvidencePath) {
    $EvidencePath = Join-Path $workingDir "sidecar-smoke-evidence.json"
}

$environment = @{
    FILEMATE_DATA_DIR = $dataDir
    FILEMATE_DB_PATH = (Join-Path $dataDir "filemate.db")
    FILEMATE_UPLOAD_DIR = (Join-Path $dataDir "inbox")
    FILEMATE_ARCHIVE_DIR = $archiveDir
    FILEMATE_SHUTDOWN_TOKEN = $shutdownToken
}
$previousEnvironment = @{}

function Get-ProcessLogs {
    $stdout = if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -Raw -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
    } else { "" }
    $stderr = if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue
    } else { "" }
    return "stdout:`n$stdout`nstderr:`n$stderr"
}

function Test-BackendPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect("127.0.0.1", 8001, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(300)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

try {
    New-Item -ItemType Directory -Force -Path $workingDir, $dataDir, $archiveDir | Out-Null
    if (Test-BackendPort) {
        throw "Port 8001 is already in use; sidecar smoke requires an isolated runner."
    }
    foreach ($name in $environment.Keys) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $environment[$name], "Process")
    }

    $process = Start-Process -FilePath $BinaryPath `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $health = $null
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            throw "Sidecar exited before readiness (code $($process.ExitCode)). $(Get-ProcessLogs)"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/" `
                -Method Get -TimeoutSec 2 -UseBasicParsing
            if ($health.version -eq "1.2.0") {
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $health -or $health.version -ne "1.2.0") {
        throw "Sidecar did not become ready within $TimeoutSeconds seconds. $(Get-ProcessLogs)"
    }

    $databasePath = $environment.FILEMATE_DB_PATH
    if (-not (Test-Path -LiteralPath $databasePath)) {
        throw "Sidecar health succeeded but SQLite database was not created."
    }

    $headers = @{ "X-FileMate-Shutdown-Token" = $shutdownToken }
    $shutdown = Invoke-RestMethod -Uri "http://127.0.0.1:8001/internal/shutdown" `
        -Method Post -Headers $headers -TimeoutSec 5 -UseBasicParsing
    if (-not $shutdown.success -or -not $shutdown.data.shutting_down) {
        throw "Sidecar rejected the graceful shutdown request."
    }

    $exitDeadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $exitDeadline) {
        $process.Refresh()
        if ($process.HasExited) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    $process.Refresh()
    if (-not $process.HasExited) {
        throw "Sidecar did not exit gracefully after the shutdown request."
    }
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Sidecar returned exit code $exitCode. $(Get-ProcessLogs)"
    }
    if (Test-BackendPort) {
        throw "Sidecar port remained open after graceful shutdown."
    }
    $stderr = Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue
    if ($stderr -notmatch "Application shutdown complete") {
        throw "Uvicorn did not report a completed application shutdown. $(Get-ProcessLogs)"
    }

    $evidence = [ordered]@{
        schema_version = 1
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        binary = $BinaryPath
        version = $health.version
        ready = $true
        database_created = $true
        graceful_shutdown = $true
        port_released = $true
        uvicorn_shutdown_complete = $true
        exit_code_available = ($null -ne $exitCode)
        exit_code = $exitCode
    }
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    if ($evidenceDirectory) {
        New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    }
    $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    Write-Host "Sidecar smoke passed. Evidence: $EvidencePath"
} finally {
    if ($process) {
        $process.Refresh()
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($name in $environment.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $previousEnvironment[$name],
            "Process"
        )
    }
}
