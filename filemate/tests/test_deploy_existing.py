"""用隔离合成资料验证服务器备份和发布包拒绝边界。"""

from __future__ import annotations

import io
import sqlite3
import tarfile
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
