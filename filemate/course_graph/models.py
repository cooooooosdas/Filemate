"""Course graph contracts and bounded identity normalization."""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ItemDecision(BaseModel):
    """Capture an explicit bounded human review decision."""

    model_config = ConfigDict(extra="forbid", strict=True)
    item_id: str = Field(min_length=1, max_length=80)
    verdict: Literal["accept", "reject", "revise"]
    label: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"\S")
    aliases: list[str] = Field(default_factory=list, max_length=20)
    relation: str | None = Field(default=None, max_length=30)
    from_label: str | None = Field(default=None, min_length=1, max_length=120)
    to_label: str | None = Field(default=None, min_length=1, max_length=120)
    semantic_checked: bool = False


class CourseGraphError(ValueError):
    """Expose a fixed code without supplier content."""

    def __init__(self, code: str, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def normalize_term(value: str) -> str:
    """Normalize whitespace and case while preserving term symbols."""
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def digest(value: Any) -> str:
    """Hash a canonical JSON representation."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def now_iso() -> str:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def request_key_valid(value: str) -> None:
    """Reject unbounded or ambiguous idempotency keys."""
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", value):
        raise CourseGraphError("invalid_request_key", 422)


def bounded_text(value: str, maximum: int) -> str:
    """Validate meaningful bounded input without coercion."""
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise CourseGraphError("invalid_text", 422)
    return value.strip()
