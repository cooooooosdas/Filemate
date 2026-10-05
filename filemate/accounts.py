"""邮箱账户、恢复码和可撤销的服务器会话。"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_HASH_SLOTS = threading.BoundedSemaphore(2)
_SESSION_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
SESSION_SECONDS = 12 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60


class AccountError(ValueError):
    """可直接展示的账号错误。"""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def normalize_email(value: str) -> str:
    """规范化邮箱，不接受电话或显示名称。"""
    email = value.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
        raise AccountError("请输入有效的邮箱地址")
    return email


def validate_password(value: str) -> None:
    """新密码至少九字符并混合字母和数字，保留常见密码检查。"""
    if not 9 <= len(value) <= 128:
        raise AccountError("密码需为 9–128 个字符")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        raise AccountError("密码需同时包含字母和数字，符号可选")
    if len(set(value)) < 4 or value.casefold() in {
        "password123456789",
        "123456789012345",
        "qwertyuiopasdfgh",
    }:
        raise AccountError("这个密码过于常见，请换一个更难猜的口令")


def _password_hash(password: str, salt: str | None = None) -> str:
    """使用带独立随机盐的 scrypt，限制并发内存开销。"""
    salt = salt or secrets.token_hex(16)
    with _HASH_SLOTS:
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=32768,
            r=8,
            p=3,
            dklen=64,
            maxmem=64 * 1024 * 1024,
        ).hex()
    return f"scrypt-v1${salt}${digest}"


def _verify_password(password: str, encoded: str) -> bool:
    """恒定时间比较密码派生值。"""
    _, salt, _ = encoded.split("$")
    return hmac.compare_digest(_password_hash(password, salt), encoded)


def _digest(value: str) -> str:
    """摘要高熵令牌，数据库不保存可直接登录或恢复的秘密。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AccountStore:
    """在主库保存账号索引，将业务数据继续路由到独立资料目录。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._dummy_hash = _password_hash(secrets.token_urlsafe(32))
        self.denied_workspace: Callable[[str], bool] = lambda _workspace: False

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _rate_limit(self, email: str, action: str) -> None:
        now = int(time.time())
        key = _digest(f"{action}:{email}")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM account_attempts WHERE window_start < ?", (now - 900,))
            row = db.execute(
                "SELECT attempts FROM account_attempts WHERE attempt_key=?", (key,)
            ).fetchone()
            if row and row[0] >= 10:
                raise AccountError("尝试次数过多，请 15 分钟后再试", 429)
            db.execute(
                "INSERT INTO account_attempts VALUES (?, ?, 1) "
                "ON CONFLICT(attempt_key) DO UPDATE SET attempts=attempts+1",
                (key, now),
            )

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, str]:
        return {key: row[key] for key in ("account_id", "email", "display_name", "created_at")}

    def workspace_claimed(self, workspace_id: str) -> bool:
        with self._connection() as db:
            return (
                db.execute(
                    "SELECT 1 FROM accounts WHERE workspace_id=?", (workspace_id,)
                ).fetchone()
                is not None
            )

    def resolve_session(self, token: str | None) -> dict[str, Any] | None:
        if not token or not _SESSION_PATTERN.fullmatch(token):
            return None
        with self._connection() as db:
            row = db.execute(
                "SELECT a.*, s.expires_at FROM account_sessions s "
                "JOIN accounts a USING(account_id) WHERE token_hash=? AND expires_at>?",
                (_digest(token), int(time.time())),
            ).fetchone()
            if row is None or self.denied_workspace(row['workspace_id']):
                return None
            return {
                "user": self._public(row),
                "workspace_id": row["workspace_id"],
                "expires_at": row["expires_at"],
            }

    def _new_session(self, db: sqlite3.Connection, account_id: str, remember: bool) -> str:
        now = int(time.time())
        db.execute("DELETE FROM account_sessions WHERE expires_at<=?", (now,))
        db.execute(
            "DELETE FROM account_sessions WHERE account_id=? AND token_hash NOT IN "
            "(SELECT token_hash FROM account_sessions WHERE account_id=? ORDER BY created_at DESC, rowid DESC LIMIT 9)",
            (account_id, account_id),
        )
        token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO account_sessions VALUES (?, ?, ?, ?)",
            (
                _digest(token),
                account_id,
                now,
                now + (REMEMBER_SECONDS if remember else SESSION_SECONDS),
            ),
        )
        return token

    def register(
        self, email: str, password: str, display_name: str, workspace_id: str, remember: bool
    ) -> tuple[dict[str, str], str, str]:
        email = normalize_email(email)
        if self.denied_workspace(workspace_id):
            raise AccountError('原学习空间已删除，请重新打开注册页', 409)
        validate_password(password)
        display_name = display_name.strip()
        if not 2 <= len(display_name) <= 30 or any(ord(ch) < 32 for ch in display_name):
            raise AccountError("昵称需为 2–30 个字符")
        self._rate_limit(email, "register")
        encoded = _password_hash(password)
        recovery_code = secrets.token_urlsafe(32)
        account_id = uuid.uuid4().hex
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO accounts(account_id,email,display_name,password_hash,recovery_hash,workspace_id) VALUES (?,?,?,?,?,?)",
                    (
                        account_id,
                        email,
                        display_name,
                        encoded,
                        _digest(recovery_code),
                        workspace_id,
                    ),
                )
            except sqlite3.IntegrityError:
                raise AccountError(
                    "该邮箱已注册，或当前游客资料已归入账号；请登录或找回密码", 409
                ) from None
            token = self._new_session(db, account_id, remember)
            row = db.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
            return self._public(row), token, recovery_code

    def login(self, email: str, password: str, remember: bool) -> tuple[dict[str, str], str]:
        email = normalize_email(email)
        if not 1 <= len(password) <= 128:
            raise AccountError("邮箱或密码不正确", 401)
        self._rate_limit(email, "login")
        with self._connection() as db:
            row = db.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
        valid = _verify_password(password, row["password_hash"] if row else self._dummy_hash)
        if not row or not valid or self.denied_workspace(row['workspace_id']):
            raise AccountError("邮箱或密码不正确", 401)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT * FROM accounts WHERE account_id=?", (row["account_id"],)
            ).fetchone()
            if current is None or current["password_hash"] != row["password_hash"]:
                raise AccountError("密码已更新，请重新登录", 401)
            return self._public(current), self._new_session(db, row["account_id"], remember)

    def logout(self, token: str | None, all_sessions: bool = False) -> None:
        if not token:
            return
        with self._connection() as db:
            if all_sessions:
                db.execute(
                    "DELETE FROM account_sessions WHERE account_id=(SELECT account_id FROM account_sessions WHERE token_hash=?)",
                    (_digest(token),),
                )
            else:
                db.execute("DELETE FROM account_sessions WHERE token_hash=?", (_digest(token),))

    def recover(self, email: str, recovery_code: str, password: str) -> str:
        email = normalize_email(email)
        validate_password(password)
        self._rate_limit(email, "recover")
        if not _SESSION_PATTERN.fullmatch(recovery_code):
            raise AccountError("邮箱或恢复码不正确", 401)
        with self._connection() as db:
            row = db.execute(
                "SELECT account_id FROM accounts WHERE email=? AND recovery_hash=?",
                (email, _digest(recovery_code)),
            ).fetchone()
        if row is None:
            raise AccountError("邮箱或恢复码不正确", 401)
        encoded = _password_hash(password)
        new_code = secrets.token_urlsafe(32)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE accounts SET password_hash=?, recovery_hash=? WHERE account_id=? AND recovery_hash=?",
                (encoded, _digest(new_code), row[0], _digest(recovery_code)),
            )
            if result.rowcount != 1:
                raise AccountError("恢复码已使用，请使用最新恢复码", 401)
            db.execute("DELETE FROM account_sessions WHERE account_id=?", (row[0],))
        return new_code

    def delete_account(self, account_id: str, password: str,
                       stage_files: Callable[[str], None], rollback_files: Callable[[], None]) -> None:
        """重新验证密码，文件暂存成功后在同一事务撤销全部登录并删除账号。"""
        with self._connection() as db:
            row = db.execute('SELECT * FROM accounts WHERE account_id=?', (account_id,)).fetchone()
        if not row:
            raise AccountError('账号不存在或已注销', 401)
        self._rate_limit(row['email'], 'delete')
        if not 1 <= len(password) <= 128 or not _verify_password(password, row['password_hash']):
            raise AccountError('密码不正确，账号与资料保留', 401)
        staged = False
        committed = False
        try:
            with self._connection() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT * FROM accounts WHERE account_id=?', (account_id,)).fetchone()
                if current is None or current['password_hash'] != row['password_hash'] or current['workspace_id'] != row['workspace_id']:
                    raise AccountError('账号凭据已更新，请重新登录后预览注销', 409)
                staged = True
                stage_files(current['workspace_id'])
                db.execute('DELETE FROM account_sessions WHERE account_id=?', (account_id,))
                db.execute('DELETE FROM accounts WHERE account_id=?', (account_id,))
                for action in ('register', 'login', 'recover', 'delete'):
                    db.execute('DELETE FROM account_attempts WHERE attempt_key=?', (_digest(action + ':' + row['email']),))
                db.commit()
                committed = True
        except Exception:
            if staged and not committed:
                rollback_files()
            raise
