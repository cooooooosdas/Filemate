"""Read-only, bounded session choices with fresh evidence checks."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from filemate.execution.data_actions import digest
from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.wrongbook.engine import parse_time
from filemate.wrongbook.insights import PRIORITY_RULE_VERSION, priority_details
from filemate.wrongbook.models import Identity, StrictBody
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries
from filemate.wrongbook.repository import ReviewRepository

MAX_SESSION_ITEMS = 20
SESSION_RULE_VERSION = 'review2-session-v1'
STALE_PREVIEW = '预览题目、来源或排期已变化，请重新生成预览'


class SessionRef(StrictBody):
    wrong_id: Identity
    artifact_id: Identity
    source_id: Identity | None
    question_index: int = Field(ge=0, le=1_000_000)
    question_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    revision: int = Field(ge=1)
    next_review_at: str = Field(min_length=1, max_length=64)

    @field_validator('next_review_at')
    @classmethod
    def valid_time(cls, value):
        if parse_time(value) is None:
            raise ValueError('复习时间无效')
        return value


class SessionCheck(StrictBody):
    refs: Annotated[list[SessionRef], Field(min_length=1, max_length=MAX_SESSION_ITEMS)]
    filters: ReviewFilter = Field(default_factory=ReviewFilter)

    @model_validator(mode='after')
    def unique(self):
        if len({ref.wrong_id for ref in self.refs}) != len(self.refs):
            raise ValueError('预览题目不可重复')
        return self


def _reference(row: dict[str, Any]) -> dict[str, Any]:
    return SessionRef.model_validate({key: row[key] for key in SessionRef.model_fields}).model_dump()


class ReviewSessions:
    def __init__(self, storage: SQLiteStorage, *, clock: Callable[[], datetime] | None = None):
        self.storage = storage
        self.clock = clock

    def preview(self, filters: ReviewFilter, *, available_minutes: int,
                minutes_per_question: int = 4) -> dict[str, Any]:
        if type(available_minutes) is not int or not 0 <= available_minutes <= 1440:
            raise ValueError('可用时长须为0至1440的整数')
        if type(minutes_per_question) is not int or not 1 <= minutes_per_question <= 60:
            raise ValueError('单题预估须为1至60的整数')
        filters = ReviewFilter.model_validate(filters)
        size = min(MAX_SESSION_ITEMS, available_minutes // minutes_per_question)
        page = ReviewQueries(self.storage, clock=self.clock).page(filters, limit=max(1, size), eligible_only=True)
        as_of = parse_time(page['as_of'])
        items = [{'ref': _reference(row), 'stem': row['stem'], 'knowledge_label': row['knowledge_label'],
                  'priority': priority_details(row, now=as_of), 'estimated_minutes': minutes_per_question}
                 for row in page['items'][:size]]
        return {'status': 'preview_only', 'scope': 'filtered_eligible_due', 'as_of': page['as_of'],
                'day_zone': 'Asia/Shanghai', 'filters': filters.model_dump(exclude_none=True),
                'items': items, 'selected_count': len(items), 'eligible_count': page['total'],
                'deferred_count': page['total'] - len(items), 'estimated_minutes': len(items) * minutes_per_question,
                'available_minutes': available_minutes, 'minutes_per_question': minutes_per_question,
                'selection_limit': MAX_SESSION_ITEMS, 'rule_version': SESSION_RULE_VERSION,
                'priority_rule_version': PRIORITY_RULE_VERSION,
                'estimate_note': '仅为本次短练的时长预算，不代表完整复盘耗时；开始前仍需核验题目',
                'warning': '可用时长不足一题预估' if size == 0 and page['total'] else None}

    def check(self, refs: list[dict[str, Any]], *, filters: ReviewFilter | None = None) -> dict[str, Any]:
        command = SessionCheck.model_validate({'refs': refs, 'filters': filters or ReviewFilter()})
        as_of = ReviewRepository(self.storage, clock=self.clock).now()
        with self.storage.read_snapshot() as read:
            page = ReviewQueries(read)._snapshot_page(read, command.filters, as_of=as_of,
                limit=MAX_SESSION_ITEMS, eligible_only=True, wrong_ids=[ref.wrong_id for ref in command.refs])
            found = {row['wrong_id']: row for row in page['items']}
            if len(found) != len(command.refs):
                raise QuestionRevisionConflict(STALE_PREVIEW)
            artifacts = {}
            for ref in command.refs:
                row = found[ref.wrong_id]
                if _reference(row) != ref.model_dump():
                    raise QuestionRevisionConflict(STALE_PREVIEW)
                if ref.artifact_id not in artifacts:
                    try:
                        artifacts[ref.artifact_id] = read.get_artifact(ref.artifact_id)
                    except (ValueError, TypeError):
                        raise QuestionRevisionConflict(STALE_PREVIEW) from None
                artifact = artifacts[ref.artifact_id]
                content = artifact.get('content') if artifact else None
                metadata = artifact.get('metadata') if artifact else None
                if (not artifact or artifact['artifact_type'] != 'questions'
                        or artifact['source_id'] != ref.source_id or not isinstance(metadata, dict)
                        or metadata.get('read_only_snapshot') or not isinstance(content, list)
                        or ref.question_index >= len(content)):
                    raise QuestionRevisionConflict(STALE_PREVIEW)
                try:
                    if digest(content[ref.question_index]) != ref.question_digest:
                        raise QuestionRevisionConflict(STALE_PREVIEW)
                except (ValueError, TypeError):
                    raise QuestionRevisionConflict(STALE_PREVIEW) from None
        return {'status': 'ready', 'refs': [ref.model_dump() for ref in command.refs],
                'as_of': as_of.isoformat(), 'rule_version': SESSION_RULE_VERSION}
