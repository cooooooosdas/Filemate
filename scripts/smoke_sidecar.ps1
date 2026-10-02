param(
    [string]$BinaryPath = "",
    [string]$EvidencePath = "",
    [int]$TimeoutSeconds = 45
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
$expectedVersion = (
    Get-Content -Raw -LiteralPath (Join-Path $tauriRoot 'tauri.conf.json') |
        ConvertFrom-Json
).version

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
    FILEMATE_HOST = '127.0.0.1'
    FILEMATE_PORT = '8001'
    FILEMATE_ENV = 'development'
    FILEMATE_IDENTITY_MODE = 'local'
    FILEMATE_INTERVIEW_LOCAL_ONLY = '1'
    FILEMATE_ENABLE_DIGITAL_HUMAN = '1'
    FILEMATE_ENABLE_KNOWLEDGE_GRAPH = '1'
    FILEMATE_ENABLE_PROGRAMMING = '1'
    FILEMATE_ENABLE_INTERVIEW_REVIEW = '1'
    FILEMATE_ENABLE_CAREER = '1'
}
$previousEnvironment = @{}
$previousProxy = [Net.WebRequest]::DefaultWebProxy

function Get-ProcessLogs {
    $stdout = if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -Raw -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
    } else { "" }
    $stderr = if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue
    } else { "" }
    return "stdout:`n$stdout`nstderr:`n$stderr"
}

function Get-BinarySha256 {
    $stream = [IO.File]::OpenRead($BinaryPath)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
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
    # All requests here are loopback; a system proxy must not intercept readiness checks.
    [Net.WebRequest]::DefaultWebProxy = $null
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
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" `
                -Method Get -TimeoutSec 2 -UseBasicParsing
            if ($health.success -and $health.data.version -eq $expectedVersion) {
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (-not $health -or -not $health.success -or $health.data.version -ne $expectedVersion) {
        throw "Sidecar did not report expected version $expectedVersion within $TimeoutSeconds seconds. $(Get-ProcessLogs)"
    }

    $databasePath = $environment.FILEMATE_DB_PATH
    if (-not (Test-Path -LiteralPath $databasePath)) {
        throw "Sidecar health succeeded but SQLite database was not created."
    }

    $moduleChecks = [ordered]@{}
    foreach ($endpoint in @(
        '/api/digital-human/playbacks', '/api/knowledge-graph',
        '/api/programming/problems', '/interview/review/status', '/api/career/catalog'
    )) {
        $moduleResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8001$endpoint" `
            -Method Get -TimeoutSec 10 -UseBasicParsing
        if (-not $moduleResponse.success) {
            throw "Bundled module contract failed: $endpoint"
        }
        $moduleChecks[$endpoint] = $true
    }

    # Verify bundled modules and fonts in an isolated database without model calls.
    $interviewBody = [Text.Encoding]::UTF8.GetBytes((@{
        target_role = 'Packaged runtime synthetic check'
        allow_external_analysis = $false
    } | ConvertTo-Json))
    $created = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/interviews' `
        -Method Post -Body $interviewBody -ContentType 'application/json; charset=utf-8' `
        -TimeoutSec 10 -UseBasicParsing
    $interviewId = $created.data.interview_id
    if (-not $created.success -or -not $interviewId) {
        throw 'Bundled interview creation failed.'
    }
    $answerBody = [Text.Encoding]::UTF8.GetBytes((@{
        answer = 'I explain the background and task, then the action, result and boundaries to review.'
        question_index = 0
        request_key = "release-smoke-$runId"
    } | ConvertTo-Json))
    $answered = Invoke-RestMethod -Uri "http://127.0.0.1:8001/interviews/$interviewId/answers" `
        -Method Post -Body $answerBody -ContentType 'application/json; charset=utf-8' `
        -TimeoutSec 10 -UseBasicParsing
    if (-not $answered.success -or $answered.data.turns.Count -ne 1) {
        throw 'Bundled interview answer persistence failed.'
    }
    $report = Invoke-RestMethod -Uri "http://127.0.0.1:8001/interviews/$interviewId/review" `
        -Method Post -TimeoutSec 10 -UseBasicParsing
    if (-not $report.success) { throw 'Bundled interview report failed.' }
    $pdfPath = Join-Path $workingDir 'synthetic-interview-report.pdf'
    Invoke-WebRequest -Uri "http://127.0.0.1:8001/interviews/$interviewId/review/export?format=pdf" `
        -OutFile $pdfPath -TimeoutSec 15 -UseBasicParsing | Out-Null
    $pdfBytes = [IO.File]::ReadAllBytes($pdfPath)
    if ($pdfBytes.Length -lt 1000 -or [Text.Encoding]::ASCII.GetString($pdfBytes, 0, 5) -ne '%PDF-') {
        throw 'Bundled Chinese PDF export is invalid.'
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
        version = $health.data.version
        expected_version = $expectedVersion
        binary_sha256 = Get-BinarySha256
        sample_kind = 'synthetic_packaged_runtime_regression'
        module_contracts = $moduleChecks
        interview_answer_persisted = $true
        chinese_pdf_exported = $true
        pdf_bytes = $pdfBytes.Length
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
        if (Test-BackendPort) {
            try {
                $headers = @{ "X-FileMate-Shutdown-Token" = $shutdownToken }
                Invoke-RestMethod -Uri "http://127.0.0.1:8001/internal/shutdown" `
                    -Method Post -Headers $headers -TimeoutSec 2 `
                    -UseBasicParsing | Out-Null
                Start-Sleep -Milliseconds 750
            } catch {}
        }
        $process.Refresh()
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }

        $listeners = Get-NetTCPConnection -LocalPort 8001 -State Listen `
            -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $owner = Get-CimInstance Win32_Process `
                -Filter "ProcessId = $($listener.OwningProcess)" `
                -ErrorAction SilentlyContinue
            if ($owner -and $owner.ExecutablePath -eq $BinaryPath) {
                Stop-Process -Id $owner.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    foreach ($name in $environment.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $previousEnvironment[$name],
            "Process"
        )
    }
    [Net.WebRequest]::DefaultWebProxy = $previousProxy
}
