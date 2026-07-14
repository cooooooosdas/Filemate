"""ProcessingSession：单个文件从入队到完成的完整状态记录。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    """Session 状态机：pending → processing → done → confirmed/skipped/expired | failed。"""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    FAILED = "failed"


# 合法状态转移（按 核心框架架构 §3.2）
_VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.PENDING: {SessionStatus.PROCESSING, SessionStatus.SKIPPED},
    SessionStatus.PROCESSING: {SessionStatus.DONE, SessionStatus.FAILED},
    SessionStatus.DONE: {SessionStatus.CONFIRMED, SessionStatus.SKIPPED, SessionStatus.EXPIRED},
    SessionStatus.FAILED: {SessionStatus.PROCESSING},  # 允许重试
    SessionStatus.CONFIRMED: set(),
    SessionStatus.SKIPPED: set(),
    SessionStatus.EXPIRED: set(),
}


@dataclass
class ProcessingSession:
    """一个文件 = 一个 session，贯穿全生命周期。"""

    session_id: str
    source_path: str = ""
    status: SessionStatus = SessionStatus.PENDING
    category: str = ""
    confidence: float = 0.0
    suggested_name: str = ""
    entities: dict = field(default_factory=dict)
    milestones: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------

    def transition(self, new_status: SessionStatus) -> None:
        """按状态机规则跳转。非法跳转抛 ValueError。"""
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"状态转换非法: {self.status.value} -> {new_status.value}，"
                f"允许的下一步: {sorted(v.value for v in allowed)}"
            )
        self.status = new_status
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def is_terminal(self) -> bool:
        """是否已进入终态（不能再转移）。"""
        return not _VALID_TRANSITIONS.get(self.status, set())

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_path": self.source_path,
            "status": self.status.value,
            "category": self.category,
            "confidence": self.confidence,
            "suggested_name": self.suggested_name,
            "entities": self.entities,
            "milestones": self.milestones,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProcessingSession:
        raw_status = d.get("status", "pending")
        try:
            status = SessionStatus(raw_status)
        except ValueError:
            status = SessionStatus.PENDING
        return cls(
            session_id=d["session_id"],
            source_path=d.get("source_path", ""),
            status=status,
            category=d.get("category", ""),
            confidence=d.get("confidence", 0.0),
            suggested_name=d.get("suggested_name", ""),
            entities=d.get("entities") or {},
            milestones=d.get("milestones") or [],
            error=d.get("error", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )
