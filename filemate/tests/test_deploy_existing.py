"""用隔离合成资料验证服务器备份和发布包拒绝边界。"""

from __future__ import annotations

import ast
import io
import json
import sqlite3
import tarfile
from argparse import Namespace
from pathlib import Path

import pytest

pytest.importorskip('pwd', reason='既有服务器部署工具仅在Linux使用')
from scripts import deploy_existing as deploy


def _data(root: Path) -> None:
    """创建合成数据库与有效身份文件。"""
    root.mkdir()
    (root / 'identity.secret').write_text('synthetic-only-deployment-key')
    (root / '.bash_profile').write_text('synthetic-server-home-metadata')
    (root / 'identity.secret').chmod(0o600)
    with sqlite3.connect(root / 'filemate.db') as connection:
        connection.execute('CREATE TABLE schema_migrations(version INTEGER)')
        connection.execute('INSERT INTO schema_migrations VALUES(24)')


def test_snapshot_includes_committed_wal_and_restores_permissions(tmp_path, monkeypatch) -> None:
    source = tmp_path / 'source'
    _data(source)
    monkeypatch.setattr(deploy, 'DATA', source)
    connection = sqlite3.connect(source / 'filemate.db')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE synthetic_notes(body TEXT)')
    connection.execute("INSERT INTO synthetic_notes VALUES('synthetic committed WAL')")
    connection.commit()
    try:
        manifest = deploy.snapshot(tmp_path / 'snapshot')
        deploy.restore_drill(tmp_path / 'snapshot', tmp_path / 'restored', manifest)
        with sqlite3.connect(tmp_path / 'restored/filemate.db') as restored:
            assert restored.execute('SELECT COUNT(*) FROM synthetic_notes').fetchone() == (1,)
        assert (tmp_path / 'restored/identity.secret').stat().st_mode & 0o777 == 0o600
        assert (tmp_path / 'restored/.bash_profile').read_text() == 'synthetic-server-home-metadata'
        assert len(manifest['databases']) == 1
    finally:
        connection.close()


def test_snapshot_rejects_external_links(tmp_path, monkeypatch) -> None:
    source = tmp_path / 'source'
    _data(source)
    monkeypatch.setattr(deploy, 'DATA', source)
    (source / 'external').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='链接'):
        deploy.snapshot(tmp_path / 'snapshot')


def test_restore_drill_detects_changed_snapshot(tmp_path, monkeypatch) -> None:
    source = tmp_path / 'source'
    _data(source)
    monkeypatch.setattr(deploy, 'DATA', source)
    manifest = deploy.snapshot(tmp_path / 'snapshot')
    (tmp_path / 'snapshot/identity.secret').write_text('synthetic altered backup')
    with pytest.raises(AssertionError):
        deploy.restore_drill(tmp_path / 'snapshot', tmp_path / 'restored', manifest)
    assert (source / 'identity.secret').read_text() == 'synthetic-only-deployment-key'


@pytest.mark.parametrize('name', ['../outside.txt', '/outside.txt'])
def test_extract_rejects_escaping_members(tmp_path, name) -> None:
    archive = tmp_path / 'release.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        info = tarfile.TarInfo(name)
        info.size = 1
        stream.addfile(info, io.BytesIO(b'x'))
    with pytest.raises(ValueError, match='成员'):
        deploy.extract(archive, tmp_path / 'release', deploy.digest(archive))
    assert not (tmp_path / 'release').exists()


def test_extract_rejects_modified_archive(tmp_path) -> None:
    archive = tmp_path / 'release.tar.gz'
    archive.write_bytes(b'synthetic corrupted release')
    with pytest.raises(ValueError, match='指纹'):
        deploy.extract(archive, tmp_path / 'release', '0' * 64)
    assert not (tmp_path / 'release').exists()


def test_migration_signature_detects_sql_changes(tmp_path) -> None:
    before = tmp_path / 'before.py'
    after = tmp_path / 'after.py'
    before.write_text('_MIGRATIONS = ((24, "test", "CREATE TABLE x(a INT)"),)')
    after.write_text('_MIGRATIONS = ((24, "test", "CREATE TABLE x(a TEXT)"),)')
    assert deploy.migration_signature(before) != deploy.migration_signature(after)


def test_preflight_reads_existing_public_get_routes() -> None:
    source = Path(__file__).resolve().parents[2] / 'server.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    routes = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'get' and isinstance(node.func.value, ast.Name)
        and node.func.value.id == 'app' and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert set(deploy.PREFLIGHT_PATHS) <= routes


def test_upgrade_allows_append_but_rejects_changed_referenced_sql(tmp_path) -> None:
    old = tmp_path / 'old.py'
    new = tmp_path / 'new.py'
    old.write_text('_SQL = "CREATE TABLE x(a INT)"\n_MIGRATIONS = ((24, "old", _SQL),)')
    new.write_text('_SQL = "CREATE TABLE x(a INT)"\n_MIGRATIONS = ((24, "old", _SQL), (25, "accounts", "CREATE TABLE y(a INT)"))')
    deploy.check_migration_upgrade(old, new)
    new.write_text('_SQL = "CREATE TABLE x(a TEXT)"\n_MIGRATIONS = ((24, "old", _SQL), (25, "accounts", "CREATE TABLE y(a INT)"))')
    with pytest.raises(AssertionError, match='改写'):
        deploy.check_migration_upgrade(old, new)


def test_joint_candidate_rejects_mismatched_code_and_incomplete_options(tmp_path, monkeypatch) -> None:
    base = tmp_path / 'judge'
    candidate = base / 'releases/new'
    release = tmp_path / 'release'
    monkeypatch.setattr(deploy, 'JUDGE', base)
    calls = []
    monkeypatch.setattr(deploy, 'run', lambda *args: calls.append(args))
    args = Namespace(judge_source=str(candidate), judge_image='sha256:' + '1' * 64)
    for directory in (candidate, release):
        (directory / 'filemate/programming').mkdir(parents=True)
        for name in ('linux_broker.py', 'linux_docker.py', 'judge.py', 'windows_sandbox.py', 'problems.py'):
            (directory / 'filemate/programming' / name).write_text('synthetic matching candidate')
    deploy.judge_candidate(args, release)
    assert '--activate' not in calls[-1]
    calls.clear()
    (candidate / 'filemate/programming/linux_docker.py').write_text('synthetic old adapter')
    with pytest.raises(ValueError, match='代码不同'):
        deploy.judge_candidate(args, release)
    assert not calls
    args.judge_image = None
    with pytest.raises(ValueError, match='同时提供'):
        deploy.judge_candidate(args, release)


@pytest.mark.parametrize('failure', ['install', 'readiness'])
def test_joint_failure_restores_both_services_before_leaving_maintenance(tmp_path, monkeypatch, failure) -> None:
    for name in ('BACKEND', 'WEB', 'JUDGE', 'BACKUPS'):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(deploy, name, directory)
    monkeypatch.setattr(deploy, 'MAINTENANCE', deploy.WEB / 'maintenance.flag')
    for name in ('CONFIG', 'DROPIN', 'JUDGE_ENV', 'JUDGE_UNIT'):
        path = tmp_path / name.lower()
        path.write_text('synthetic old ' + name)
        monkeypatch.setattr(deploy, name, path)
    old_judge = deploy.JUDGE / 'releases/old'
    new_judge = deploy.JUDGE / 'releases/new'
    old_judge.mkdir(parents=True)
    new_judge.mkdir()
    (deploy.JUDGE / 'current').symlink_to(old_judge)
    old_backend = deploy.BACKEND / 'releases/old'
    release_id = 'alpha4-12345678'
    release = deploy.BACKEND / 'releases' / release_id
    for directory in (old_backend, release):
        (directory / 'filemate/execution').mkdir(parents=True)
        (directory / 'filemate/execution/storage.py').write_text('_MIGRATIONS = ((24, "old", "same SQL"),)')
    (release / 'deploy').mkdir()
    (release / 'deploy/nginx.filemate.conf').write_text('synthetic new nginx')
    (deploy.BACKEND / 'current').symlink_to(old_backend)
    (deploy.WEB / 'releases/old').mkdir(parents=True)
    (deploy.WEB / 'releases' / release_id).mkdir()
    (deploy.WEB / 'current').symlink_to('releases/old')
    source = tmp_path / 'data'
    _data(source)
    monkeypatch.setattr(deploy, 'DATA', source)
    args = Namespace(action='activate', release_id=release_id, commit='1' * 40,
                     version='synthetic-version', backend_sha256='2' * 64, web_sha256='3' * 64,
                     judge_source=str(new_judge), judge_image='sha256:' + '4' * 64)
    incoming = deploy.BACKEND / 'incoming' / release_id
    incoming.mkdir(parents=True)
    (incoming / 'staged.json').write_text(json.dumps(vars(args)))
    calls = []

    def run(*arguments):
        calls.append(arguments)
        if '--activate' in arguments:
            deploy.atomic_link(str(new_judge), deploy.JUDGE / 'current')
            deploy.JUDGE_ENV.write_text('synthetic new env')
            deploy.JUDGE_UNIT.write_text('synthetic new unit')
            if failure == 'install':
                raise RuntimeError('synthetic install failure')

    monkeypatch.setattr(deploy, 'run', run)
    monkeypatch.setattr(deploy, 'judge_candidate', lambda *args: None)
    monkeypatch.setattr(deploy.subprocess, 'check_output', lambda *args: b'synthetic old API unit')
    monkeypatch.setattr(deploy, 'health', lambda *args: None)
    monkeypatch.setattr(deploy, 'probe', lambda *args: (b'{"data":{"ready":false}}', {}))
    with pytest.raises((RuntimeError, AssertionError)):
        deploy.activate(args)
    assert (deploy.BACKEND / 'current').resolve() == old_backend
    assert (deploy.WEB / 'current').resolve() == deploy.WEB / 'releases/old'
    assert (deploy.JUDGE / 'current').resolve() == old_judge
    assert deploy.JUDGE_ENV.read_text() == 'synthetic old JUDGE_ENV'
    assert deploy.JUDGE_ENV.stat().st_mode & 0o777 == 0o600
    assert deploy.JUDGE_UNIT.read_text() == 'synthetic old JUDGE_UNIT'
    assert deploy.CONFIG.read_text() == 'synthetic old CONFIG'
    assert deploy.DROPIN.read_text() == 'synthetic old DROPIN'
    assert not deploy.MAINTENANCE.exists()
    assert calls.index(('systemctl', 'stop', 'filemate-api')) < calls.index(('systemctl', 'stop', 'filemate-judge'))
    assert calls.index(('systemctl', 'start', 'filemate-judge')) < calls.index(('systemctl', 'start', 'filemate-api'), calls.index(('systemctl', 'start', 'filemate-judge')))
    assert (source / 'identity.secret').read_text() == 'synthetic-only-deployment-key'
