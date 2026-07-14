"""ProcessingSession：单个文件从入队到完成的完整状态记录。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class ProcessingSession:
    """一个文件 = 一个 session。"""

    session_id: str
    source_path: str = ""
    status: SessionStatus = SessionStatus.PENDING
    category: str = ""
    confidence: float = 0.0
    suggested_name: str = ""
    entities: dict = field(default_factory=dict)
    milestones: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat)

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
