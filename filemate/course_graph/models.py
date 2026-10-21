"""Course graph contracts and bounded identity normalization."""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


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
