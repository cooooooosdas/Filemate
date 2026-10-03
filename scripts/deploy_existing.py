"""按已验收提交更新既有NPM/systemd站点，保留完整备份和旧发布。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pwd
import re
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

BACKEND = Path('/opt/filemate')
WEB = Path('/clouddream/nginx-proxy-manage/data/filemate')
DATA = Path('/var/lib/filemate')
CONFIG = Path('/clouddream/nginx-proxy-manage/data/nginx/custom/http.conf')
DROPIN = Path('/etc/systemd/system/filemate-api.service.d/30-release-runtime.conf')
MAINTENANCE = WEB / 'maintenance.flag'
HTTP = build_opener(ProxyHandler({}))
PREFLIGHT_PATHS = (
    '/api/knowledge-graph', '/api/career/status', '/api/programming/status',
    '/api/digital-human/playbacks', '/knowledge/sources', '/analytics/overview',
)


def run(*arguments: str) -> None:
    """检查外部命令退出状态。"""
    subprocess.run(arguments, check=True)


def digest(path: Path) -> str:
    """分块计算发布包和备份指纹。"""
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path: Path, value: Any) -> None:
    """保存本次部署的本地管理证据。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    path.chmod(0o600)


def extract(archive: Path, target: Path, expected: str) -> None:
    """只解包指纹相符、无链接及越界成员的独占目录。"""
    if digest(archive) != expected or target.exists():
        raise ValueError('发布包指纹不符或目标已存在')
    with tarfile.open(archive, 'r:gz') as stream:
        members = stream.getmembers()
        for member in members:
            output = (target / member.name).resolve()
            if not output.is_relative_to(target.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError('发布包包含不支持的成员')
        target.mkdir(parents=True, mode=0o755)
        stream.extractall(target, members=members)


def probe(base: str, path: str, *, html: bool = False) -> tuple[bytes, Any]:
    """检查实际服务响应，不加载模型或私有记录。"""
    request = Request(base + path, headers={
        'Host': 'filemate.asia', 'Accept': 'text/html' if html else 'application/json',
    })
    with HTTP.open(request, timeout=30) as response:
        assert response.status == 200
        return response.read(), response.headers


def health(base: str, version: str) -> None:
    """等候本次候选的实际版本响应。"""
    for attempt in range(45):
        try:
            body, _ = probe(base, '/api/health')
            assert json.loads(body)['data']['version'] == version
            return
        except (OSError, AssertionError, ValueError):
            if attempt == 44:
                raise RuntimeError('候选服务未通过版本健康检查') from None
            time.sleep(1)


def stage(args: argparse.Namespace) -> None:
    """隔离安装并对临时数据运行候选服务。"""
    incoming = BACKEND / 'incoming' / args.release_id
    release = BACKEND / 'releases' / args.release_id
    static = WEB / 'releases' / args.release_id
    environment = BACKEND / 'venvs' / args.release_id
    extract(incoming / 'backend.tar.gz', release, args.backend_sha256)
    extract(incoming / 'web.tar.gz', static, args.web_sha256)
    marker = json.loads((static / 'release.json').read_text())
    assert marker['commit'] == args.commit and marker['version'] == args.version
    assert not (release / '.env').exists()
    account = pwd.getpwnam('filemate')
    for node in [release, *release.rglob('*')]:
        os.chown(node, 0, account.pw_gid)
        node.chmod(0o750 if node.is_dir() else 0o640)
    for node in [static, *static.rglob('*')]:
        node.chmod(0o755 if node.is_dir() else 0o644)
    shutil.copy2(BACKEND / 'current/.env.production', release / '.env.production')
    os.chown(release / '.env.production', 0, account.pw_gid)
    (release / '.env.production').chmod(0o640)
    run('/usr/bin/python3.11', '-m', 'venv', str(environment))
    run(str(environment / 'bin/python'), '-m', 'pip', 'install', '--require-hashes',
        '-r', str(release / 'deploy/requirements-production.lock'))
    run(str(environment / 'bin/python'), '-m', 'pip', 'check')
    # SSH管理员的umask可能令venv归root独占；只授予服务组读取/遍历。
    for node in [environment, *environment.rglob('*')]:
        if not node.is_symlink():
            os.chown(node, 0, account.pw_gid)
            mode = stat.S_IMODE(node.stat().st_mode)
            node.chmod(mode | ((mode & 0o500) >> 3))
    temporary = Path('/var/lib/filemate-preflight') / args.release_id
    temporary.mkdir(parents=True, mode=0o700)
    temporary.parent.chmod(0o755)
    os.chown(temporary, account.pw_uid, account.pw_gid)
    env = os.environ.copy()
    env.update(FILEMATE_ENV='production', FILEMATE_IDENTITY_MODE='anonymous',
               FILEMATE_DATA_DIR=str(temporary), FILEMATE_DB_PATH=str(temporary / 'filemate.db'),
               FILEMATE_UPLOAD_DIR=str(temporary / 'inbox'),
               FILEMATE_ARCHIVE_DIR=str(temporary / 'archive'),
               FILEMATE_ALLOWED_HOSTS='filemate.asia,localhost,127.0.0.1',
               FILEMATE_CORS_ORIGINS='https://filemate.asia', FILEMATE_IDENTITY_SECRET='',
               PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring', LLM_API_KEY='')
    with (incoming / 'staging-api.log').open('w') as output:
        process = subprocess.Popen([
            'runuser', '-u', 'filemate', '--', str(environment / 'bin/python'),
            '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', '8012',
        ], cwd=release, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            health('http://127.0.0.1:8012', args.version)
            for path in PREFLIGHT_PATHS:
                probe('http://127.0.0.1:8012', path)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    save(incoming / 'staged.json', vars(args))
    print(json.dumps({'stage': 'passed', 'release': args.release_id, 'version': args.version}))


def database_facts(path: Path) -> dict[str, Any]:
    """只读校验数据库完整性与迁移版本。"""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        version = connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        return {'schema_version': version, 'integrity': 'ok'}


def snapshot(target: Path) -> dict[str, Any]:
    """停写后备份整个数据根目录，包括旧运维文件和全部匿名分库。"""
    assert not target.exists()
    target.mkdir(mode=0o700)
    records = []
    databases = []
    paths = [DATA] + sorted(DATA.rglob('*'))
    for source in paths:
        if source.is_symlink() or not (source.is_dir() or source.is_file()):
            raise ValueError('数据根目录含链接或特殊文件，需明确备份方案')
        if source.name.endswith(('.db-shm', '.db-wal')):
            assert source.with_name(source.name.rsplit('-', 1)[0]).is_file()
            continue
        if source.name.endswith('.db-journal'):
            raise ValueError('数据库存在未完成回滚日志')
        relative = source.relative_to(DATA)
        output = target / relative
        info = source.stat()
        if source.is_dir():
            output.mkdir(exist_ok=True)
        elif source.suffix == '.db':
            with (
                closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src,
                closing(sqlite3.connect(output)) as dst,
            ):
                src.backup(dst)
            facts = database_facts(output)
            assert facts == database_facts(source)
            databases.append(facts)
        else:
            shutil.copy2(source, output)
            assert digest(source) == digest(output)
        os.chown(output, info.st_uid, info.st_gid)
        output.chmod(stat.S_IMODE(info.st_mode))
        records.append({'path': str(relative), 'uid': info.st_uid, 'gid': info.st_gid,
                        'mode': stat.S_IMODE(info.st_mode),
                        'sha256': digest(output) if output.is_file() else None})
    assert databases and (target / 'identity.secret').is_file()
    return {'records': records, 'databases': databases}


def restore_drill(source: Path, target: Path, manifest: dict[str, Any]) -> None:
    """在新目录验证完整快照、所有权、权限和数据库，保持未启用。"""
    assert not target.exists()
    shutil.copytree(source, target, copy_function=shutil.copy2)
    for record in manifest['records']:
        path = target / record['path']
        os.chown(path, record['uid'], record['gid'])
        path.chmod(record['mode'])
        if record['sha256']:
            assert digest(path) == record['sha256']
        if path.suffix == '.db':
            database_facts(path)
    assert len(list(target.rglob('*.db'))) == len(manifest['databases'])


def atomic_link(target: str, link: Path) -> None:
    """原子切换符号链接，保留所有发布目录。"""
    temporary = link.with_name(link.name + '.release-new')
    assert not temporary.exists() and not temporary.is_symlink()
    temporary.symlink_to(target)
    temporary.replace(link)


def migration_contract(path: Path) -> list[tuple[int, str, str]]:
    """静态读取版本、名称和 SQL，拒绝改写已发布迁移。"""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        for target in node.targets if isinstance(target, ast.Name)
    }
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '_MIGRATIONS' for t in n.targets))
    return [tuple(constants[value.id] if isinstance(value, ast.Name) else ast.literal_eval(value)
                  for value in migration.elts) for migration in node.value.elts]


def migration_signature(path: Path) -> str:
    """对完整 SQL 合同计算摘要。"""
    return hashlib.sha256(json.dumps(migration_contract(path)).encode()).hexdigest()


def check_migration_upgrade(before: Path, after: Path) -> None:
    """只允许同版本或在完整旧合同之后追加新迁移。"""
    old, new = migration_contract(before), migration_contract(after)
    assert new[:len(old)] == old, '候选改写或删除了已发布迁移'
    assert all(new[index][0] > new[index - 1][0] for index in range(1, len(new)))


def activate(args: argparse.Namespace) -> None:
    """停写、完整备份与恢复演练后切换；验证失败则自动回退代码。"""
    incoming = BACKEND / 'incoming' / args.release_id
    staged = json.loads((incoming / 'staged.json').read_text())
    assert all(staged[key] == vars(args)[key] for key in staged if key != 'action')
    assert not MAINTENANCE.exists()
    old_backend = os.readlink(BACKEND / 'current')
    old_web = os.readlink(WEB / 'current')
    release = BACKEND / 'releases' / args.release_id
    check_migration_upgrade(BACKEND / 'current/filemate/execution/storage.py',
                            release / 'filemate/execution/storage.py')
    backup = Path('/var/backups/filemate') / (args.release_id + '-' +
              datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    shutil.copy2(CONFIG, backup / 'nginx-before.conf')
    if DROPIN.exists():
        shutil.copy2(DROPIN, backup / 'dropin-before.conf')
    before_service = subprocess.check_output(['systemctl', 'cat', 'filemate-api'])
    (backup / 'systemd-before.service').write_bytes(before_service)
    save(backup / 'release-metadata.json', {
        'previous_backend': old_backend, 'previous_web': old_web,
        'release': args.release_id, 'commit': args.commit, 'version': args.version,
        'backend_sha256': args.backend_sha256, 'web_sha256': args.web_sha256,
    })
    MAINTENANCE.touch(mode=0o644)
    try:
        run('systemctl', 'stop', 'filemate-api')
        manifest = snapshot(backup / 'data')
        save(backup / 'ownership.json', manifest)
        restore_drill(backup / 'data', backup / 'restore-drill', manifest)
        shutil.copy2(release / 'deploy/nginx.filemate.conf', CONFIG)
        run('docker', 'exec', 'nginx-app', 'nginx', '-t')
        DROPIN.write_text('[Service]\nExecStart=\nExecStart=/opt/filemate/venvs/' +
                          args.release_id + '/bin/python /opt/filemate/current/server.py\n')
        atomic_link(str(release), BACKEND / 'current')
        atomic_link('releases/' + args.release_id, WEB / 'current')
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', 'filemate-api')
        health('http://172.18.0.1:8001', args.version)
        run('docker', 'exec', 'nginx-app', 'nginx', '-s', 'reload')
        # 维护标记仅阻断网关；切换前通过实际Nginx容器校验本包文件映射。
        run('docker', 'exec', 'nginx-app', 'test', '-r', '/data/filemate/current/index.html')
        save(backup / 'result.json', {'passed': True, 'backup_restore_verified': True,
             'database_count': len(manifest['databases']),
             'file_count': sum(bool(r['sha256']) for r in manifest['records']),
             'schemas': sorted({d['schema_version'] for d in manifest['databases']}),
             'commit': args.commit, 'version': args.version,
             'rollback_policy': 'after public writes use a release preserving accounts and schema; never restore old snapshot over new data'})
    except Exception:
        run('systemctl', 'stop', 'filemate-api')
        atomic_link(old_backend, BACKEND / 'current')
        atomic_link(old_web, WEB / 'current')
        shutil.copy2(backup / 'nginx-before.conf', CONFIG)
        if (backup / 'dropin-before.conf').exists():
            shutil.copy2(backup / 'dropin-before.conf', DROPIN)
        elif DROPIN.exists():
            DROPIN.unlink()
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', 'filemate-api')
        run('docker', 'exec', 'nginx-app', 'nginx', '-t')
        run('docker', 'exec', 'nginx-app', 'nginx', '-s', 'reload')
        MAINTENANCE.unlink()
        raise
    MAINTENANCE.unlink()
    health('https://filemate.asia', args.version)
    body, headers = probe('https://filemate.asia', '/', html=True)
    assert headers.get('Cache-Control') == 'no-store'
    assets = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', body.decode())
    assert assets
    for asset in assets:
        content, response_headers = probe('https://filemate.asia', asset)
        assert content and 'immutable' in response_headers.get('Cache-Control', '')
    marker, _ = probe('https://filemate.asia', '/release.json')
    assert json.loads(marker)['commit'] == args.commit
    print(json.dumps({'activation': 'passed', 'version': args.version,
                      'commit': args.commit, 'backup': str(backup)}))


def main() -> None:
    """仅支持已明确授权的既有生产拓扑。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'activate'])
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--backend-sha256', required=True)
    parser.add_argument('--web-sha256', required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0 and re.fullmatch(r'alpha[1-9][0-9]*-[0-9a-f]{7,40}', args.release_id)
    assert re.fullmatch(r'[0-9a-f]{40}', args.commit)
    assert all(re.fullmatch(r'[0-9a-f]{64}', value) for value in
               [args.backend_sha256, args.web_sha256])
    {'stage': stage, 'activate': activate}[args.action](args)


if __name__ == '__main__':
    main()
