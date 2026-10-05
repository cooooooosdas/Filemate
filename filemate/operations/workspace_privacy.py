"""私有空间删除的持久阶段记录、失败恢复与防止旧身份复活。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any

from filemate.execution import data_actions
from filemate.execution.storage import _now_iso
from filemate.operations.backup import _check_node
from filemate.operations.personal_backup import EXCLUDED_TABLES, _remove_tree


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def deletion_snapshot(storage: Any, roots: list[Path]) -> tuple[str, dict[str, int]]:
    """流式摘要不受导出容量限制，允许大空间真正删除。"""
    checksum = hashlib.sha256()
    counts = {}
    with storage.read_snapshot() as snapshot:
        conn = snapshot._conn()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if row[0] not in EXCLUDED_TABLES]
        for table in tables:
            counts[table] = 0
            checksum.update(table.encode())
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                checksum.update(data_actions.digest(dict(row)).encode())
                counts[table] += 1
    counts['files'] = 0
    for root in roots:
        if not root.exists():
            continue
        _check_node(root)
        for path in sorted(root.rglob('*')):
            _check_node(path)
            if path.is_file():
                checksum.update(str(path.relative_to(root)).encode('utf-8'))
                with path.open('rb') as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                        checksum.update(chunk)
                counts['files'] += 1
    return checksum.hexdigest(), counts


class WorkspaceDeletion:
    def __init__(self, data_root: Path, secret: bytes) -> None:
        self.data_root = data_root.resolve()
        self.actions = self.data_root / '_working' / 'privacy-actions'
        self.trash = self.data_root / '_working' / 'erased-workspaces'
        self.tombstones = self.data_root / 'privacy-tombstones'
        if len(secret) < 32:
            raise ValueError('空间删除签名配置无效')
        self.secret = secret

    def _write(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _check_node(path.parent)
        if path.exists():
            _check_node(path)
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        signature = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        temporary = path.with_suffix('.writing')
        if temporary.exists():
            _check_node(temporary)
        with temporary.open('wb') as handle:
            handle.write(json.dumps({'record': record, 'signature': signature}, ensure_ascii=False).encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)

    def _read(self, path: Path) -> dict[str, Any]:
        _check_node(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('删除阶段记录容量异常')
        wrapper = json.loads(path.read_bytes())
        record = wrapper['record']
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        if not hmac.compare_digest(wrapper['signature'], hmac.new(self.secret, body, hashlib.sha256).hexdigest()):
            raise ValueError('删除阶段记录签名异常')
        return record

    def _root(self, owner: str) -> Path:
        if not re.fullmatch(r'u_[0-9a-f]{32}', owner):
            raise ValueError('学习空间标识非法')
        root = self.data_root / 'users' / owner
        if root.parent.resolve() != (self.data_root / 'users').resolve() or not root.resolve().is_relative_to(self.data_root):
            raise ValueError('学习空间超出托管边界')
        return root

    def _identifier(self, token: str) -> str:
        if not re.fullmatch(r'[0-9a-f]{64}', token):
            raise ValueError('请先预览删除操作')
        return _digest(token)

    def blocked(self, owner: str) -> bool:
        path = self.tombstones / (_digest(owner) + '.json')
        if not path.exists():
            return False
        record = self._read(path)
        return record.get('state') in {'pending', 'erased'}

    def receipt(self, token: str) -> dict[str, Any] | None:
        identifier = self._identifier(token)
        path = self.actions / (identifier + '.json')
        if not path.exists():
            return None
        record = self._read(path)
        if record.get('state') in {'complete', 'cleanup_pending'}:
            return {'deleted': True, 'cleanup_pending': record['state'] != 'complete'}
        return None

    def stage(self, owner: str, token: str, account_id: str, counts: dict[str, int], action: str = 'account_delete') -> None:
        identifier = self._identifier(token)
        root = self._root(owner)
        _check_node(root)
        for child in root.rglob('*'):
            _check_node(child)
        path = self.actions / (identifier + '.json')
        if path.exists():
            raise ValueError('该删除操作已有阶段记录，请重新预览')
        self.trash.mkdir(parents=True, exist_ok=True)
        _check_node(self.trash)
        if (self.trash / identifier).exists():
            raise ValueError('删除暂存位置已存在')
        record = {'action': action, 'state': 'prepared', 'workspace_id': owner,
                  'workspace_hash': _digest(owner), 'account_id': account_id, 'counts': counts, 'created_at': _now_iso()}
        self._write(path, record)
        self._write(self.tombstones / (_digest(owner) + '.json'), {'state': 'pending', 'action_id': identifier, 'created_at': record['created_at']})
        root.rename(self.trash / identifier)
        self._write(path, {**record, 'state': 'staged'})

    def rollback(self, token: str) -> None:
        identifier = self._identifier(token)
        path = self.actions / (identifier + '.json')
        if not path.exists():
            return
        record = self._read(path)
        if record.get('state') in {'complete', 'cleanup_pending'}:
            raise ValueError('已提交的账号删除不能回滚登录资格')
        root = self._root(record['workspace_id'])
        temporary = self.trash / identifier
        if temporary.exists():
            _check_node(temporary)
            if root.exists():
                raise ValueError('回滚目标已存在，拒绝覆盖新数据')
            temporary.rename(root)
        self._write(self.tombstones / (record['workspace_hash'] + '.json'), {'state': 'rolled_back', 'action_id': identifier, 'updated_at': _now_iso()})
        self._write(path, {**record, 'state': 'rolled_back', 'updated_at': _now_iso()})

    def finish(self, token: str) -> dict[str, Any]:
        return self._finish_identifier(self._identifier(token))

    def _finish_identifier(self, identifier: str) -> dict[str, Any]:
        if not re.fullmatch(r'[0-9a-f]{64}', identifier):
            raise ValueError('删除阶段标识非法')
        path = self.actions / (identifier + '.json')
        record = self._read(path)
        temporary = self.trash / identifier
        pending = False
        if temporary.exists():
            try:
                _remove_tree(temporary, self.trash)
            except OSError:
                pending = True
        self._write(self.tombstones / (record['workspace_hash'] + '.json'), {'state': 'erased', 'action_id': identifier, 'updated_at': _now_iso()})
        final = {key: value for key, value in record.items() if key not in {'workspace_id', 'account_id'}}
        self._write(path, {**final, 'state': 'cleanup_pending' if pending else 'complete', 'updated_at': _now_iso()})
        return {'deleted': True, 'cleanup_pending': pending}

    def recover(self, accounts: Any) -> dict[str, int]:
        """启动前根据账号主库的提交结果恢复暂存或完成删除，不猜测阶段。"""
        result = {'rolled_back': 0, 'completed': 0, 'pending': 0}
        if self.actions.exists():
            _check_node(self.actions)
        for path in self.actions.glob('*.json'):
            if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name):
                raise ValueError('删除阶段文件名异常')
            record = self._read(path)
            state = record.get('state')
            if state in {'prepared', 'staged'}:
                with accounts._connection() as db:
                    row = db.execute('SELECT 1 FROM accounts WHERE account_id=? AND workspace_id=?', (record['account_id'], record['workspace_id'])).fetchone()
                if row:
                    # 重启时连接和任务已停止，目录仍使用同一受验证布局。
                    owner = record['workspace_id']; root = self._root(owner); temporary = self.trash / path.stem
                    if temporary.exists():
                        _check_node(temporary)
                        if root.exists():
                            raise ValueError('中断恢复目标已存在，拒绝覆盖')
                        temporary.rename(root)
                    self._write(self.tombstones / (record['workspace_hash'] + '.json'), {'state': 'rolled_back', 'action_id': path.stem, 'updated_at': _now_iso()})
                    self._write(path, {**record, 'state': 'rolled_back', 'updated_at': _now_iso()})
                    result['rolled_back'] += 1
                else:
                    finished = self._finish_identifier(path.stem)
                    result['pending' if finished['cleanup_pending'] else 'completed'] += 1
            elif state == 'cleanup_pending':
                finished = self._finish_identifier(path.stem)
                result['pending' if finished['cleanup_pending'] else 'completed'] += 1
            elif state not in {'complete', 'rolled_back'}:
                raise ValueError('删除阶段状态异常')
        # 删除账本不随业务备份回滚；已注销空间仍不可被旧备份复活。
        users = self.data_root / 'users'
        if users.exists():
            _check_node(users)
            for root in users.iterdir():
                if re.fullmatch(r'u_[0-9a-f]{32}', root.name):
                    marker = self.tombstones / (_digest(root.name) + '.json')
                    if marker.exists() and self._read(marker).get('state') == 'erased':
                        _remove_tree(self._root(root.name), users)
        with accounts._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT account_id, workspace_id FROM accounts').fetchall():
                marker = self.tombstones / (_digest(row['workspace_id']) + '.json')
                if marker.exists() and self._read(marker).get('state') == 'erased':
                    db.execute('DELETE FROM account_sessions WHERE account_id=?', (row['account_id'],))
                    db.execute('DELETE FROM accounts WHERE account_id=?', (row['account_id'],))
        return result

    def retry_cleanup(self) -> int:
        pending = 0
        for path in self.actions.glob('*.json'):
            if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name):
                raise ValueError('删除阶段文件名异常')
            if self._read(path).get('state') == 'cleanup_pending':
                pending += int(self._finish_identifier(path.stem)['cleanup_pending'])
        return pending
