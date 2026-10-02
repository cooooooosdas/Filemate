param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$EvidencePath = "",
    [int]$TimeoutSeconds = 45,
    [switch]$IsolatedRunner,
    [switch]$VerifyInheritedEnvironment
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bundlePath = (Resolve-Path -LiteralPath $BundleRoot).Path
$runId = [guid]::NewGuid().ToString("N")
$workingDir = Join-Path $projectRoot "_working\installer-smoke\$runId"
$installRoot = Join-Path $workingDir "installed\FileMate"
$appProcess = $null
$originalPath = $env:PATH
$originalProxy = [Net.WebRequest]::DefaultWebProxy
$uninstaller = $null
$roamingAppData = [Environment]::GetFolderPath("ApplicationData")
$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$previousEnvironment = @{}
$stage = "preflight"
$expectedVersion = (
    Get-Content -Raw -LiteralPath (
        Join-Path $projectRoot "filemate\web\src-tauri\tauri.conf.json"
    ) | ConvertFrom-Json
).version

if (-not $IsolatedRunner -and $env:GITHUB_ACTIONS -ne 'true') {
    throw 'Installer smoke may only run in disposable Windows CI or with -IsolatedRunner on a disposable VM.'
}

if (-not $EvidencePath) {
    $EvidencePath = Join-Path $workingDir "installer-smoke-evidence.json"
}

$msi = Get-ChildItem -LiteralPath $bundlePath -Recurse -Filter "*.msi" -File |
    Select-Object -First 1
$nsis = Get-ChildItem -LiteralPath $bundlePath -Recurse -Filter "*-setup.exe" -File |
    Select-Object -First 1
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
    [Net.WebRequest]::DefaultWebProxy = $null
    New-Item -ItemType Directory -Force -Path $workingDir | Out-Null
    if (Test-BackendPort) {
        throw "Port 8001 is already in use; installer smoke requires an isolated runner."
    }
    foreach ($dataRoot in @($roamingAppData, $localAppData)) {
        if (Test-Path -LiteralPath (Join-Path $dataRoot "cn.filemate.campus-twin")) {
            throw "Existing FileMate application data found; use a fresh disposable runner."
        }
    }

    $stage = "silent_install"
    $install = Start-Process -FilePath $nsis.FullName `
        -ArgumentList "/S /D=$installRoot" -WindowStyle Hidden -Wait -PassThru
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

    if ($VerifyInheritedEnvironment) {
        # 模拟从网站运维终端启动桌面，不能让父进程参数改变本地安全边界。
        $inheritedEnvironment = @{
            FILEMATE_HOST = "0.0.0.0"
            FILEMATE_PORT = "18081"
            FILEMATE_ENV = "production"
            FILEMATE_IDENTITY_MODE = "anonymous"
            FILEMATE_ALLOWED_HOSTS = "filemate-test.invalid"
            FILEMATE_CORS_ORIGINS = "https://filemate-test.invalid"
        }
        foreach ($name in $inheritedEnvironment.Keys) {
            $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            [Environment]::SetEnvironmentVariable($name, $inheritedEnvironment[$name], "Process")
        }
    }

    $stage = "backend_ready"
    $appProcess = Start-Process -FilePath $appExecutable.FullName `
        -WorkingDirectory $appExecutable.DirectoryName -WindowStyle Hidden -PassThru
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
            if ($health.version -eq $expectedVersion) {
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $health -or $health.version -ne $expectedVersion) {
        throw "Installed FileMate backend did not become ready."
    }

    $stage = "desktop_isolation"
    if ($VerifyInheritedEnvironment) {
        $listeners = @(Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction Stop)
        if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
            throw "Desktop backend is not bound exclusively to IPv4 loopback."
        }
        $localResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8001/" `
            -Method Get -TimeoutSec 5 -UseBasicParsing
        if ($localResponse.Headers["Set-Cookie"]) {
            throw "Desktop backend inherited website anonymous identity mode."
        }
        foreach ($origin in @("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")) {
            $preflight = Invoke-WebRequest -Uri "http://127.0.0.1:8001/knowledge/sources" `
                -Method Options -TimeoutSec 5 -UseBasicParsing -Headers @{
                    Origin = $origin
                    "Access-Control-Request-Method" = "GET"
                }
            if ($preflight.Headers["Access-Control-Allow-Origin"] -ne $origin) {
                throw "Desktop origin is not allowed: $origin"
            }
        }
    }

    $llmSettings = Invoke-RestMethod -Uri "http://127.0.0.1:8001/settings/llm" `
        -Method Get -TimeoutSec 5 -UseBasicParsing
    if (-not $llmSettings.success -or `
        -not $llmSettings.data.secure_storage_available) {
        throw "Installed FileMate cannot access the Windows secure credential store."
    }

    $dataCandidates = @(
        (Join-Path $roamingAppData "cn.filemate.campus-twin\filemate.db"),
        (Join-Path $localAppData "cn.filemate.campus-twin\filemate.db")
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

    $stage = "graceful_exit"
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

    $stage = "silent_uninstall"
    $uninstall = Start-Process -FilePath $uninstaller.FullName `
        -ArgumentList "/S" -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "NSIS silent uninstall failed with exit code $($uninstall.ExitCode)."
    }
    if (Test-Path -LiteralPath $appExecutable.FullName) {
        throw "Application executable remained after uninstall."
    }
    if (-not (Test-Path -LiteralPath $databasePath)) {
        throw "Uninstall removed FileMate user data."
    }

    $evidence = [ordered]@{
        schema_version = 2
        passed = $true
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        msi = if ($msi) { $msi.FullName } else { $null }
        nsis = $nsis.FullName
        version = $expectedVersion
        installed_executable = $appExecutable.Name
        silent_install = $true
        python_absent_from_path = $true
        app_started = $true
        backend_ready = $true
        secure_credential_store_ready = $true
        graceful_exit = $true
        sidecar_stopped = $true
        silent_uninstall = $true
        user_data_preserved = $true
        inherited_environment_checked = [bool]$VerifyInheritedEnvironment
        desktop_loopback_identity_origins_preserved = if ($VerifyInheritedEnvironment) { $true } else { $null }
    }
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    if ($evidenceDirectory) {
        New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    }
    $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    Write-Host "Windows installer smoke passed. Evidence: $EvidencePath"
} catch {
    $failure = [ordered]@{
        schema_version = 2
        passed = $false
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        version = $expectedVersion
        failed_stage = $stage
        error = $_.Exception.Message
        inherited_environment_checked = [bool]$VerifyInheritedEnvironment
    }
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    if ($evidenceDirectory) {
        New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    }
    $failure | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    throw
} finally {
    $env:PATH = $originalPath
    [Net.WebRequest]::DefaultWebProxy = $originalProxy
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
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
    if ($uninstaller -and (Test-Path -LiteralPath $uninstaller.FullName)) {
        Start-Process -FilePath $uninstaller.FullName `
            -ArgumentList "/S" -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue | Out-Null
    }
}
