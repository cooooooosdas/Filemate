"""匿名空间保留期与私有恢复副本维护，不删除注册账号。"""

from __future__ import annotations

import re
import secrets
import time
from typing import Any

from filemate.operations.backup import _check_node
from filemate.operations.personal_backup import PersonalBackup
from filemate.operations.workspace_privacy import WorkspaceDeletion, _digest


class RetentionMaintenance:
    def __init__(self, deletion: WorkspaceDeletion, accounts: Any, days: int = 90) -> None:
        if not 7 <= days <= 3650:
            raise ValueError('匿名保留天数须为7至3650')
        self.deletion, self.accounts, self.days = deletion, accounts, days
        self.activity = deletion.data_root / 'privacy-activity'

    def touch(self, owner: str, now: int | None = None) -> None:
        self.deletion._root(owner)
        marker = self.activity / (_digest(owner) + '.json')
        now = int(time.time()) if now is None else now
        if marker.exists() and now - int(self.deletion._read(marker)['last_seen']) < 300:
            return
        self.deletion._write(marker, {'last_seen': now})

    def run(self, storages: Any, active: dict[str, int], exclusive: set[str], open_storage: Any, now: int | None = None) -> dict[str, int]:
        """调用方持租户锁；不与请求/注册/编译/恢复同时清理同一空间。"""
        now = int(time.time()) if now is None else now
        result = {'guests_deleted': 0, 'temp_files_removed': 0, 'temp_directories_removed': 0, 'pending': 0, 'legacy_grace_started': 0}
        users = self.deletion.data_root / 'users'
        if not users.exists():
            return result
        _check_node(users)
        for root in users.iterdir():
            if not re.fullmatch(r'u_[0-9a-f]{32}', root.name):
                continue
            owner = root.name
            if active.get(owner, 0) or owner in exclusive or self.deletion.blocked(owner):
                continue
            _check_node(root)
            registered = self.accounts.workspace_claimed(owner)
            marker = self.activity / (_digest(owner) + '.json')
            if not registered and not marker.exists():
                self.touch(owner, now); result['legacy_grace_started'] += 1
            last_seen = int(self.deletion._read(marker)['last_seen']) if marker.exists() else now
            if not (root / 'filemate.db').exists():
                continue
            expired = not registered and now - last_seen >= self.days * 86400
            if not expired and not (root / '_working' / 'personal-restores').exists():
                continue
            storage = open_storage(owner)
            if storage._conn().execute("SELECT 1 FROM coding_submissions WHERE status IN ('queued','running') LIMIT 1").fetchone() or storage._conn().execute("SELECT 1 FROM sessions WHERE status='processing' LIMIT 1").fetchone():
                continue
            cleaned = PersonalBackup(storage, owner, root / 'inbox', root / 'archive').cleanup(now)
            result['temp_files_removed'] += cleaned['files_removed']; result['temp_directories_removed'] += cleaned['directories_removed']; result['pending'] += cleaned['pending']
            if not expired:
                continue
            with self.accounts._connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('SELECT 1 FROM accounts WHERE workspace_id=?', (owner,)).fetchone():
                    continue
                storages.pop(owner, None); storage.close()
                token = secrets.token_hex(32)
                self.deletion.stage(owner, token, '', {}, action='guest_expiry')
                erased = self.deletion.finish(token)
            result['guests_deleted'] += 1; result['pending'] += int(erased['cleanup_pending'])
            if marker.exists():
                marker.unlink()
        return result
