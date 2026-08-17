param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$EvidencePath = "",
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bundlePath = (Resolve-Path -LiteralPath $BundleRoot).Path
$runId = [guid]::NewGuid().ToString("N")
$workingDir = Join-Path $projectRoot "_working\installer-smoke\$runId"
$installRoot = Join-Path $workingDir "installed\FileMate"
$appProcess = $null
$originalPath = $env:PATH

if (-not $EvidencePath) {
    $EvidencePath = Join-Path $workingDir "installer-smoke-evidence.json"
}

$msi = Get-ChildItem -LiteralPath $bundlePath -Recurse -Filter "*.msi" -File |
    Select-Object -First 1
$nsis = Get-ChildItem -LiteralPath $bundlePath -Recurse -Filter "*-setup.exe" -File |
    Select-Object -First 1
if (-not $msi) {
    throw "MSI artifact was not found under $bundlePath."
}
if (-not $nsis) {
    throw "NSIS artifact was not found under $bundlePath."
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
    New-Item -ItemType Directory -Force -Path $workingDir | Out-Null
    if (Test-BackendPort) {
        throw "Port 8001 is already in use; installer smoke requires an isolated runner."
    }

    $install = Start-Process -FilePath $nsis.FullName `
        -ArgumentList "/S /D=$installRoot" -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "NSIS silent install failed with exit code $($install.ExitCode)."
    }

    $appExecutable = Get-ChildItem -LiteralPath $installRoot -Recurse `
        -Filter "*.exe" -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -notlike "uninstall*.exe" -and
            $_.Name -notlike "filemate-server-*.exe"
        } |
        Select-Object -First 1
    if (-not $appExecutable) {
        throw "Installed FileMate desktop executable was not found under $installRoot."
    }
    $uninstaller = Get-ChildItem -LiteralPath $installRoot -Recurse `
        -Filter "uninstall*.exe" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $uninstaller) {
        throw "NSIS uninstaller was not found under $installRoot."
    }

    # 只保留 Windows 系统路径，证明桌面运行时不依赖 CI 预装的 Python/Node。
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    if (Get-Command python -ErrorAction SilentlyContinue) {
        throw "Python is still discoverable after PATH isolation."
    }

    $appProcess = Start-Process -FilePath $appExecutable.FullName `
        -WorkingDirectory $appExecutable.DirectoryName -PassThru
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $health = $null
    while ((Get-Date) -lt $deadline) {
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            throw "Installed FileMate exited before backend readiness."
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
        throw "Installed FileMate backend did not become ready."
    }

    $dataCandidates = @(
        (Join-Path $env:APPDATA "cn.filemate.campus-twin\filemate.db"),
        (Join-Path $env:LOCALAPPDATA "cn.filemate.campus-twin\filemate.db")
    )
    $databasePath = $null
    $dataDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $dataDeadline -and -not $databasePath) {
        $databasePath = $dataCandidates | Where-Object {
            Test-Path -LiteralPath $_
        } | Select-Object -First 1
        if (-not $databasePath) {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $databasePath) {
        throw "Installed app did not create its application-data database."
    }
    $sentinelPath = Join-Path (Split-Path -Parent $databasePath) "uninstall-preserve.sentinel"
    [System.IO.File]::WriteAllText($sentinelPath, "FileMate user data must survive uninstall.")

    if (-not $appProcess.CloseMainWindow()) {
        throw "Installed app did not expose a closable main window."
    }
    $exitDeadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $exitDeadline) {
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    $appProcess.Refresh()
    if (-not $appProcess.HasExited) {
        throw "Installed app did not exit after its main window closed."
    }

    $portDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $portDeadline -and (Test-BackendPort)) {
        Start-Sleep -Milliseconds 250
    }
    if (Test-BackendPort) {
        throw "Backend sidecar remained alive after the desktop app exited."
    }

    $uninstall = Start-Process -FilePath $uninstaller.FullName `
        -ArgumentList "/S" -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "NSIS silent uninstall failed with exit code $($uninstall.ExitCode)."
    }
    if (Test-Path -LiteralPath $appExecutable.FullName) {
        throw "Application executable remained after uninstall."
    }
    if (-not (Test-Path -LiteralPath $databasePath) -or
        -not (Test-Path -LiteralPath $sentinelPath)) {
        throw "Uninstall removed FileMate user data."
    }

    $evidence = [ordered]@{
        schema_version = 1
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        msi = $msi.FullName
        nsis = $nsis.FullName
        installed_executable = $appExecutable.Name
        silent_install = $true
        python_absent_from_path = $true
        app_started = $true
        backend_ready = $true
        graceful_exit = $true
        sidecar_stopped = $true
        silent_uninstall = $true
        user_data_preserved = $true
    }
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    if ($evidenceDirectory) {
        New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    }
    $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    Write-Host "Windows installer smoke passed. Evidence: $EvidencePath"
} finally {
    $env:PATH = $originalPath
    if ($appProcess) {
        $appProcess.Refresh()
        if (-not $appProcess.HasExited) {
            $appProcess.CloseMainWindow() | Out-Null
            Start-Sleep -Seconds 2
            $appProcess.Refresh()
            if (-not $appProcess.HasExited) {
                Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
