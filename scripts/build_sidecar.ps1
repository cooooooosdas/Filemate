param(
    [string]$TargetTriple = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$tauriRoot = Join-Path $projectRoot "filemate\web\src-tauri"
$binaryDir = Join-Path $tauriRoot "binaries"
$workingDir = Join-Path $projectRoot "_working\pyinstaller"
$uvCacheDir = Join-Path $projectRoot "_working\uv-cache"
$promptData = Join-Path $projectRoot "filemate\understanding\prompts"
$rulesData = Join-Path $projectRoot "filemate\understanding\rules"

if (-not $TargetTriple) {
    $isWindows = [System.Environment]::OSVersion.Platform -eq `
        [System.PlatformID]::Win32NT
    if ($isWindows) {
        $TargetTriple = switch ($env:PROCESSOR_ARCHITECTURE) {
            "ARM64" { "aarch64-pc-windows-msvc" }
            "x86" { "i686-pc-windows-msvc" }
            default { "x86_64-pc-windows-msvc" }
        }
    } else {
        $rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
        if (-not $rustcCommand) {
            throw "Rust was not found and the target triple could not be inferred."
        }
        $hostLine = & $rustcCommand.Source -vV | Select-String -Pattern '^host:\s+(.+)$'
        if (-not $hostLine) {
            throw "Could not determine the target triple from rustc -vV."
        }
        $TargetTriple = $hostLine.Matches[0].Groups[1].Value.Trim()
    }
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install uv before building the sidecar."
}

$binaryName = "filemate-server-$TargetTriple"

New-Item -ItemType Directory -Force -Path $binaryDir | Out-Null
New-Item -ItemType Directory -Force -Path $workingDir | Out-Null
New-Item -ItemType Directory -Force -Path $uvCacheDir | Out-Null

$previousUvCacheDir = $env:UV_CACHE_DIR
$env:UV_CACHE_DIR = $uvCacheDir
Push-Location $projectRoot
try {
    uv run --no-project `
        --with-requirements requirements-desktop.txt `
        --with "pyinstaller>=6.0" `
        pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name $binaryName `
        --distpath $binaryDir `
        --workpath (Join-Path $workingDir "build") `
        --specpath (Join-Path $workingDir "spec") `
        --paths $projectRoot `
        --hidden-import uvicorn.logging `
        --hidden-import uvicorn.loops.auto `
        --hidden-import uvicorn.protocols.http.auto `
        --hidden-import uvicorn.protocols.websockets.auto `
        --hidden-import uvicorn.lifespan.on `
        --collect-data icalendar `
        --add-data "$promptData;filemate/understanding/prompts" `
        --add-data "$rulesData;filemate/understanding/rules" `
        server.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller sidecar build failed."
    }
}
finally {
    Pop-Location
    if ($null -eq $previousUvCacheDir) {
        Remove-Item Env:UV_CACHE_DIR -ErrorAction SilentlyContinue
    } else {
        $env:UV_CACHE_DIR = $previousUvCacheDir
    }
}

$extension = if ([System.Environment]::OSVersion.Platform -eq `
    [System.PlatformID]::Win32NT) { ".exe" } else { "" }
$expectedBinary = Join-Path $binaryDir "$binaryName$extension"
if (-not (Test-Path $expectedBinary)) {
    throw "Sidecar output was not found: $expectedBinary"
}
Write-Host "Sidecar ready: $expectedBinary"
