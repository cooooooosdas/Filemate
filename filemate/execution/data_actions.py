"""用户数据操作的预览凭据、修订检查与最小审计记录。"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

SCHEMA = """
CREATE TABLE data_action_previews (
    token_hash TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    result TEXT
);
CREATE INDEX idx_data_action_expiry ON data_action_previews(expires_at);
CREATE TABLE data_action_audit (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    affected TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);
"""


def digest(value: Any) -> str:
    """生成稳定修订摘要，不把正文写入操作记录。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def issue(conn: Any, action: str, resource_id: str, revision: str) -> str:
    """签发绑定当前数据修订的短期随机确认凭据。"""
    token = secrets.token_hex(32)
    conn.execute("DELETE FROM data_action_previews WHERE result IS NULL AND expires_at < ?",
                 (int(time.time()),))
    conn.execute("INSERT INTO data_action_previews VALUES (?, ?, ?, ?, ?, NULL)",
                 (digest(token), action, resource_id, revision, int(time.time()) + 900))
    return token


def check(conn: Any, action: str, resource_id: str, token: str,
          revision: str | None) -> dict[str, Any] | None:
    """返回成功回执；过期、越权或数据变化时拒绝继续。"""
    row = conn.execute("SELECT * FROM data_action_previews WHERE token_hash=?",
                       (digest(token),)).fetchone()
    if row is None or row["action"] != action or row["resource_id"] != resource_id:
        raise ValueError("请重新预览此操作")
    if row["result"] is not None:
        return json.loads(row["result"])
    if row["expires_at"] < int(time.time()) or revision != row["revision"]:
        raise ValueError("资料已变化或预览已过期，请重新预览")
    return None


def finish(conn: Any, action: str, resource_id: str, token: str,
           result: dict[str, Any]) -> None:
    """将删除与回执、审计事件写入同一事务。"""
    conn.execute("UPDATE data_action_previews SET result=? WHERE token_hash=?",
                 (json.dumps(result, ensure_ascii=False), digest(token)))
    conn.execute("INSERT INTO data_action_audit(action, resource_id, affected) VALUES (?, ?, ?)",
                 (action, resource_id, json.dumps(result.get("affected", {}))))
