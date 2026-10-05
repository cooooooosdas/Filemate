"""私有空间的完整数据导出与签名备份恢复，不导出登录凭据。"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from filemate.execution import data_actions
from filemate.execution.storage import _MIGRATIONS, SQLiteStorage, _now_iso
from filemate.operations.backup import _check_node, _relative

MAX_BACKUP_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_DATA_BYTES = 32 * 1024 * 1024
EXCLUDED_TABLES = {'schema_migrations', 'accounts', 'account_sessions', 'account_attempts', 'data_action_previews', 'data_action_audit'}
PATH_KEYS = {'source_path', 'dest_path', 'ics_path', 'path', 'file_path', 'archive_path'}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _remove_tree(path: Path, boundary: Path) -> None:
    resolved = path.resolve()
    allowed = boundary.resolve()
    if resolved == allowed or not resolved.is_relative_to(allowed):
        raise ValueError('清理目标超出本次操作的目录边界')
    _check_node(path)
    shutil.rmtree(path)


class PersonalBackup:
    def __init__(self, storage: SQLiteStorage, owner: str, inbox: Path, archive: Path) -> None:
        self.storage, self.owner = storage, owner
        self.roots = {'inbox': inbox.resolve(), 'archive': archive.resolve()}
        if self.roots['inbox'].is_relative_to(self.roots['archive']) or self.roots['archive'].is_relative_to(self.roots['inbox']):
            raise ValueError('上传与归档目录必须独立，才能安全恢复')
        self.cache = storage.db_path.parent / '_working' / 'personal-restores'
        if any(storage.db_path.resolve().is_relative_to(root) or self.cache.resolve().is_relative_to(root) for root in self.roots.values()):
            raise ValueError('托管文件目录不能包含数据库或运行凭据')

    def _key(self) -> bytes:
        path = self.storage.db_path.with_suffix('.backup-secret')
        try:
            with path.open('xb') as handle:
                handle.write(secrets.token_bytes(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
        _check_node(path)
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError('个人备份签名配置无效')
        return key

    def _remember_cleanup(self, path: Path, boundary: Path, token: str) -> None:
        """只记录本次生成的清理目标，以签名防止替换为任意文件夹。"""
        location = self.cache / 'cleanup.json'
        records = self._cleanup_records()
        records.append({'path': str(path), 'boundary': str(boundary), 'token_hash': data_actions.digest(token)})
        body = _json(records)
        self.cache.mkdir(parents=True, exist_ok=True)
        _check_node(self.cache)
        temporary = self.cache / 'cleanup.writing'
        if temporary.exists():
            _check_node(temporary)
        temporary.write_bytes(_json({'records': records, 'signature': hmac.new(self._key(), body, hashlib.sha256).hexdigest()}))
        temporary.chmod(0o600); temporary.replace(location)

    def _cleanup_records(self) -> list[dict[str, str]]:
        location = self.cache / 'cleanup.json'
        if not location.exists():
            return []
        _check_node(location)
        if location.stat().st_size > 1024 * 1024:
            raise ValueError('清理记录容量异常')
        wrapper = json.loads(location.read_bytes())
        records = wrapper['records']
        if not hmac.compare_digest(wrapper['signature'], hmac.new(self._key(), _json(records), hashlib.sha256).hexdigest()):
            raise ValueError('清理记录签名异常')
        return records

    def cleanup(self, now: int | None = None) -> dict[str, int]:
        """清除无有效确认的恢复副本及成功事务的受验证遗留目录。"""
        now = int(time.time()) if now is None else now
        result = {'files_removed': 0, 'directories_removed': 0, 'pending': 0}
        if not self.cache.exists():
            return result
        _check_node(self.cache)
        with self.storage._write_lock, self.storage._conn() as conn:
            for path in self.cache.glob('*.zip'):
                if not re.fullmatch(r'[0-9a-f]{64}\.zip', path.name):
                    continue
                _check_node(path)
                active = conn.execute("SELECT 1 FROM data_action_previews WHERE action='personal_restore' AND resource_id=? AND result IS NULL AND expires_at>=?", (path.stem, now)).fetchone()
                if not active:
                    try:
                        path.unlink(); result['files_removed'] += 1
                    except OSError:
                        result['pending'] += 1
            retained = []; tokens = set()
            for item in self._cleanup_records():
                path, boundary = Path(item['path']), Path(item['boundary'])
                allowed = (boundary.resolve() == self.cache.resolve() and re.fullmatch(r'stage-[0-9a-f]{32}', path.name)) or (any(boundary.resolve() == root.parent for root in self.roots.values()) and re.fullmatch(r'\.personal-rollback-[0-9a-f]{32}', path.name))
                if not allowed or path.parent.resolve() != boundary.resolve():
                    raise ValueError('遗留目录不属于受验证的个人恢复操作')
                tokens.add(item['token_hash'])
                try:
                    if path.exists():
                        _remove_tree(path, boundary); result['directories_removed'] += 1
                except OSError:
                    retained.append(item); result['pending'] += 1
            location = self.cache / 'cleanup.json'
            if location.exists():
                # 先持久化尚未清除的目录，再更新幂等回执。
                body = _json(retained)
                location.write_bytes(_json({'records': retained, 'signature': hmac.new(self._key(), body, hashlib.sha256).hexdigest()}))
                location.chmod(0o600)
            for token in tokens:
                if any(item['token_hash'] == token for item in retained):
                    continue
                row = conn.execute('SELECT result FROM data_action_previews WHERE token_hash=?', (token,)).fetchone()
                if row and row[0]:
                    receipt = json.loads(row[0]); receipt['cleanup_pending'] = False
                    conn.execute('UPDATE data_action_previews SET result=? WHERE token_hash=?', (json.dumps(receipt, ensure_ascii=False), token))
            for row in conn.execute("SELECT token_hash,resource_id,result FROM data_action_previews WHERE action='personal_restore' AND result IS NOT NULL").fetchall():
                receipt = json.loads(row['result'])
                if receipt.get('cleanup_pending') and not (self.cache / (row['resource_id'] + '.zip')).exists() and not any(item['token_hash'] == row['token_hash'] for item in retained):
                    receipt['cleanup_pending'] = False
                    conn.execute('UPDATE data_action_previews SET result=? WHERE token_hash=?', (json.dumps(receipt, ensure_ascii=False), row['token_hash']))
            conn.execute('DELETE FROM data_action_previews WHERE result IS NULL AND expires_at<?', (now,))
        return result

    def cancel_preview(self, identifier: str, token: str) -> dict[str, bool]:
        with self.storage._write_lock, self.storage._conn() as conn:
            row = conn.execute('SELECT action,resource_id FROM data_action_previews WHERE token_hash=?', (data_actions.digest(token),)).fetchone()
            if row is None or row['action'] != 'personal_restore' or row['resource_id'] != identifier:
                raise ValueError('恢复预览不存在')
            conn.execute('UPDATE data_action_previews SET expires_at=0 WHERE token_hash=? AND result IS NULL', (data_actions.digest(token),))
        result = self.cleanup()
        return {'cancelled': True, 'cleanup_pending': result['pending'] > 0}

    def _tables(self) -> dict[str, list[str]]:
        conn = self.storage._conn()
        return {row[0]: [column[1] for column in conn.execute(f'PRAGMA table_info("{row[0]}")')]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
                if row[0] not in EXCLUDED_TABLES}

    def _snapshot(self) -> dict[str, Any]:
        conn = self.storage._conn()
        tables = {}; total = 0
        for name in self._tables():
            tables[name] = []
            for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid'):
                item = dict(row); total += len(_json(item))
                if total > MAX_DATA_BYTES:
                    raise ValueError('个人业务数据超过32MB自助容量，请使用管理员离线备份；未生成残缺备份')
                tables[name].append(item)
        return {'format_version': 1, 'schema_version': _MIGRATIONS[-1][0], 'owner': self.owner,
                'roots': {key: str(root) for key, root in self.roots.items()}, 'tables': tables,
                'audit': [dict(row) for row in conn.execute('SELECT * FROM data_action_audit ORDER BY event_id')]}

    def _files(self) -> dict[str, bytes]:
        result = {}; total = 0
        for prefix, root in self.roots.items():
            if not root.exists():
                continue
            _check_node(root)
            for path in root.rglob('*'):
                _check_node(path)
                if not path.is_file():
                    continue
                if len(result) >= 5000:
                    raise ValueError('个人备份最多5000个托管文件，请先清理或使用管理员离线备份')
                size = path.stat().st_size
                if size > MAX_BACKUP_BYTES or total + size > MAX_EXPANDED_BYTES:
                    raise ValueError('个人托管文件超过备份容量，请使用管理员离线备份；未生成残缺备份')
                relative = prefix + '/' + path.relative_to(root).as_posix()
                _relative(relative)
                result[relative] = path.read_bytes(); total += size
        return result

    def export(self, backup: bool = True) -> bytes:
        with self.storage._write_lock, self.storage.read_snapshot() as snapshot:
            original = self.storage
            try:
                self.storage = snapshot
                content = self._snapshot()
            finally:
                self.storage = original
            content['created_at'] = _now_iso()
            if not backup:
                return _json(content)
            files = self._files()
            entries = {'personal-data.json': _json(content), **{'files/' + key: value for key, value in files.items()}}
            if sum(len(value) for value in entries.values()) > MAX_EXPANDED_BYTES:
                raise ValueError('个人备份超过128MB展开容量；未生成残缺备份')
            manifest = {'format_version': 1, 'owner': self.owner, 'files': {key: _sha(value) for key, value in entries.items()}}
            signature = hmac.new(self._key(), _json(manifest), hashlib.sha256).hexdigest()
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json', _json({**manifest, 'signature': signature}))
                for name, value in entries.items():
                    archive.writestr(name, value)
            if buffer.tell() > MAX_BACKUP_BYTES:
                raise ValueError('个人备份超过25MB传输容量，请使用管理员离线备份；未生成残缺备份')
            return buffer.getvalue()

    def validate(self, raw: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
        if len(raw) > MAX_BACKUP_BYTES:
            raise ValueError('备份文件不能超过25MB')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (len(entries) > 5002 or len(set(names)) != len(names) or 'manifest.json' not in names
                        or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
                        or any(entry.flag_bits & 1 or entry.is_dir() or entry.file_size > MAX_EXPANDED_BYTES for entry in entries)):
                    raise ValueError('备份条目、加密方式或展开容量无效')
                for name in names:
                    _relative(name)
                if archive.getinfo('manifest.json').file_size > 1024 * 1024:
                    raise ValueError('备份清单过大')
                if 'personal-data.json' not in names or archive.getinfo('personal-data.json').file_size > MAX_DATA_BYTES + 1024 * 1024:
                    raise ValueError('备份业务数据容量无效')
                manifest = json.loads(archive.read('manifest.json'))
                signature = manifest.pop('signature', '')
                if manifest.get('owner') != self.owner or manifest.get('format_version') != 1 or not hmac.compare_digest(str(signature), hmac.new(self._key(), _json(manifest), hashlib.sha256).hexdigest()):
                    raise ValueError('备份不属于此学习空间，签名无效或签名配置已变更')
                hashes = manifest.get('files')
                if not isinstance(hashes, dict) or set(hashes) != set(names) - {'manifest.json'} or 'personal-data.json' not in hashes:
                    raise ValueError('备份清单不完整')
                contents = {name: archive.read(name) for name in hashes}
                if any(_sha(value) != hashes[name] for name, value in contents.items()):
                    raise ValueError('备份内容校验失败')
        except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('不是有效的FileMate个人备份') from exc
        content = json.loads(contents.pop('personal-data.json'))
        allowed = self._tables()
        if content.get('owner') != self.owner or content.get('format_version') != 1 or type(content.get('schema_version')) is not int or not 26 <= content['schema_version'] <= _MIGRATIONS[-1][0]:
            raise ValueError('备份格式、归属或数据库版本不支持')
        tables = content.get('tables')
        if not isinstance(tables, dict) or not set(tables) <= set(allowed) or 'workspaces' not in tables:
            raise ValueError('备份业务表不符合现役合同')
        for name, rows in tables.items():
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not set(row) <= set(allowed[name]) for row in rows):
                raise ValueError('备份字段结构不符合现役合同')
        files = {}
        for name, value in contents.items():
            parts = _relative(name).parts
            if len(parts) < 3 or parts[0] != 'files' or parts[1] not in self.roots:
                raise ValueError('备份包含非托管文件')
            files['/'.join(parts[1:])] = value
        return content, files

    def _revision(self) -> str:
        snapshot = self._snapshot(); snapshot.pop('audit')
        return data_actions.digest({'data': snapshot, 'files': {key: _sha(value) for key, value in self._files().items()}})

    def preview(self, raw: bytes) -> dict[str, Any]:
        content, files = self.validate(raw)
        identifier = _sha(raw)
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            token = data_actions.issue(conn, 'personal_restore', identifier, self._revision())
            self.cache.mkdir(parents=True, exist_ok=True)
            _check_node(self.cache)
            cache_file = self.cache / (identifier + '.zip')
            try:
                with cache_file.open('xb') as handle:
                    handle.write(raw)
                cache_file.chmod(0o600)
            except FileExistsError:
                _check_node(cache_file)
                if _sha(cache_file.read_bytes()) != identifier:
                    raise ValueError('暂存备份校验失败')
            return {'backup_id': identifier, 'confirmation_token': token,
                    'backup_created_at': content.get('created_at'), 'restored_counts': {name: len(rows) for name, rows in content['tables'].items()},
                    'current_counts': {name: len(rows) for name, rows in self._snapshot()['tables'].items()}, 'file_count': len(files),
                    'current_file_count': len(self._files()),
                    'notice': '确认后整体替换当前业务数据与托管上传/归档文件；旧文件操作会话仅作为失败历史，不重放操作。密码、登录会话和API密钥不恢复。请先导出当前数据，其他设备操作会使预览失效。'}

    def _rebind(self, value: Any, old_roots: dict[str, str], key: str = '') -> Any:
        if isinstance(value, dict):
            return {name: self._rebind(item, old_roots, name) for name, item in value.items()}
        if isinstance(value, list):
            return [self._rebind(item, old_roots, key) for item in value]
        if isinstance(value, str) and key in PATH_KEYS:
            for prefix, old in old_roots.items():
                try:
                    relative = Path(value).relative_to(Path(old))
                    return str(self.roots[prefix] / relative)
                except ValueError:
                    pass
            return '' if key == 'source_path' else value
        if isinstance(value, str) and key in {'input_snapshot', 'output_snapshot', 'metadata', 'content', 'context_refs'}:
            try:
                return json.dumps(self._rebind(json.loads(value), old_roots), ensure_ascii=False)
            except (ValueError, TypeError):
                return value
        return value

    def restore(self, identifier: str, token: str) -> dict[str, Any]:
        if len(identifier) != 64 or any(char not in '0123456789abcdef' for char in identifier):
            raise ValueError('请先上传并预览备份')
        staging = self.cache / ('stage-' + secrets.token_hex(16))
        moved: list[tuple[Path, Path]] = []; installed: list[Path] = []
        cleanup_pending = False
        with self.storage._write_lock, self.storage._conn() as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')
                receipt = data_actions.check(conn, 'personal_restore', identifier, token, self._revision())
                if receipt:
                    return receipt
                if conn.execute("SELECT 1 FROM coding_submissions WHERE status IN ('queued','running') LIMIT 1").fetchone() or conn.execute("SELECT 1 FROM sessions WHERE status='processing' LIMIT 1").fetchone():
                    raise ValueError('有任务执行中，请结束后重新预览恢复')
                cache_file = self.cache / (identifier + '.zip'); _check_node(cache_file)
                raw = cache_file.read_bytes()
                if _sha(raw) != identifier:
                    raise ValueError('暂存备份校验失败')
                content, files = self.validate(raw)
                staging.mkdir()
                for prefix in self.roots:
                    (staging / prefix).mkdir()
                for relative, value in files.items():
                    target = staging.joinpath(*_relative(relative).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as handle:
                        handle.write(value)
                for prefix, root in self.roots.items():
                    root.parent.mkdir(parents=True, exist_ok=True)
                    if root.exists():
                        _check_node(root)
                        rollback = root.parent / ('.personal-rollback-' + secrets.token_hex(16))
                        root.rename(rollback); moved.append((root, rollback))
                    installed.append(root)
                    shutil.move(str(staging / prefix), str(root))
                conn.execute('PRAGMA defer_foreign_keys=ON')
                for name in self._tables():
                    conn.execute(f'DELETE FROM "{name}"')
                for name, rows in content['tables'].items():
                    for row in rows:
                        row = self._rebind(row, content['roots'])
                        columns = list(row)
                        placeholders = ','.join('?' for _ in columns)
                        names = ','.join('"' + column + '"' for column in columns)
                        conn.execute(f'INSERT INTO "{name}" ({names}) VALUES ({placeholders})', [row[column] for column in columns])
                conn.execute("UPDATE sessions SET status='failed',error='备份恢复的历史会话；文件操作不重放'")
                conn.execute("UPDATE execution_records SET status='failed',error='备份恢复后禁止重放文件操作'")
                conn.execute("DELETE FROM data_action_previews WHERE action!='personal_restore'")
                if conn.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('恢复的数据关系不完整，当前数据保留')
                receipt = {'restored': True, 'cleanup_pending': False, 'file_count': len(files), 'counts': {name: len(rows) for name, rows in content['tables'].items()}}
                data_actions.finish(conn, 'personal_restore', identifier, token, receipt)
                conn.commit()
            except Exception:
                conn.rollback()
                for root in reversed(installed):
                    if root.exists():
                        _remove_tree(root, root.parent)
                for root, rollback in reversed(moved):
                    rollback.rename(root)
                raise
            finally:
                if staging.exists():
                    try:
                        _remove_tree(staging, self.cache)
                    except OSError:
                        cleanup_pending = True
                        self._remember_cleanup(staging, self.cache, token)
        # 仅清理本次创建并验证过归属的目录；不留下隐含的用户资料副本。
        for _root, rollback in moved:
            try:
                _remove_tree(rollback, _root.parent)
            except OSError:
                cleanup_pending = True
                self._remember_cleanup(rollback, _root.parent, token)
        try:
            cache_file.unlink()
        except OSError:
            cleanup_pending = True
        receipt['cleanup_pending'] = cleanup_pending
        with self.storage._conn() as conn:
            conn.execute('UPDATE data_action_previews SET result=? WHERE token_hash=?', (json.dumps(receipt, ensure_ascii=False), data_actions.digest(token)))
        return receipt
