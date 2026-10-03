param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [string]$User = 'root',
    [int]$Port = 22,
    [string]$ArchivePath = '_working\deploy\filemate-release.tar.gz',
    [string]$EnvironmentFile = '_working\deploy\.env.production'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$archive = (Resolve-Path -LiteralPath (Join-Path $projectRoot $ArchivePath)).Path
$environment = (Resolve-Path -LiteralPath (Join-Path $projectRoot $EnvironmentFile)).Path
$releaseId = Get-Date -Format 'yyyyMMdd-HHmmss'
$remoteArchive = "/tmp/filemate-$releaseId.tar.gz"
$remoteEnvironment = "/tmp/filemate-$releaseId.env"
$remoteRelease = "/opt/filemate/releases/$releaseId"
$destination = "$User@$HostName"

Write-Host "[1/3] 上传 FileMate 发布包..."
& scp -P $Port -- $archive "${destination}:$remoteArchive"
if ($LASTEXITCODE -ne 0) { throw '发布包上传失败' }
& scp -P $Port -- $environment "${destination}:$remoteEnvironment"
if ($LASTEXITCODE -ne 0) { throw '生产环境配置上传失败' }

Write-Host "[2/3] 在 ECS 上构建并启动..."
$remoteCommand = @"
set -euo pipefail
mkdir -p '$remoteRelease'
tar -xzf '$remoteArchive' -C '$remoteRelease'
install -m 600 '$remoteEnvironment' '$remoteRelease/deploy/.env.production'
cd '$remoteRelease'
bash deploy/bootstrap-ubuntu.sh
ln -sfn '$remoteRelease' /opt/filemate/current
rm -f '$remoteArchive' '$remoteEnvironment'
"@
& ssh -tt -p $Port -- $destination $remoteCommand
if ($LASTEXITCODE -ne 0) { throw 'ECS 部署失败' }

Write-Host "[3/3] 部署完成。"
Write-Host "服务器：$HostName"
