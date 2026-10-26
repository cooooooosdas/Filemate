"""Bounded review read models without executing model or grading work."""

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage
from filemate.wrongbook.engine import LOCAL_ZONE, parse_time
from filemate.wrongbook.models import Cause
from filemate.wrongbook.repository import ReviewRepository


class ReviewFilter(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str = Field(default='', max_length=160)
    source_id: str | None = Field(default=None, max_length=128)
    course_id: str | None = Field(default=None, max_length=128)
    knowledge_q: str = Field(default='', max_length=120)
    status: Literal['all', 'due', 'overdue', 'active', 'pending', 'criterion_met', 'legacy_completed', 'paused', 'history', 'invalid'] = 'all'
    cause: Cause | Literal['unconfirmed'] | None = None
    min_errors: int | None = Field(default=None, ge=0, le=1_000_000)
    max_errors: int | None = Field(default=None, ge=0, le=1_000_000)
    due_from: str | None = None
    due_to: str | None = None
    created_from: str | None = None
    created_to: str | None = None
    sort: Literal['due', 'updated', 'errors', 'created'] = 'due'
    direction: Literal['asc', 'desc'] = 'asc'
    reviewable_only: bool = False

    @model_validator(mode='after')
    def ranges(self):
        for prefix in ('due', 'created'):
            low, high = getattr(self, prefix + '_from'), getattr(self, prefix + '_to')
            for value in (low, high):
                if value is not None and (len(value) > 64 or parse_time(value) is None or datetime.fromisoformat(value).tzinfo is None):
                    raise ValueError('日期须为带时区的有效ISO时间')
            if low and high and parse_time(low) > parse_time(high):
                raise ValueError('日期区间相反')
        if self.min_errors is not None and self.max_errors is not None and self.min_errors > self.max_errors:
            raise ValueError('次数区间相反')
        return self


def _bounds(limit, offset):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 1_000_000:
        raise ValueError('分页范围无效')


def _object(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _stem_expression(conn: sqlite3.Connection) -> str:
    try:
        conn.execute("SELECT json_extract('{}','$.stem')")
    except sqlite3.OperationalError:
        return 'review_stem(w.question)'
    return """CASE WHEN json_valid(w.question) THEN CASE WHEN json_type(w.question)='object'
        THEN COALESCE(NULLIF(CAST(json_extract(w.question,'$.stem') AS TEXT),''),
                      CAST(json_extract(w.question,'$.question') AS TEXT),'')
        ELSE '' END ELSE '' END"""


class ReviewQueries:
    def __init__(self, storage: SQLiteStorage, *, clock: Callable[[], datetime] | None = None):
        self.storage = storage
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _configure(self, read):
        repo = ReviewRepository(read, clock=self.clock)
        conn = repo.time_connection()
        obj = lru_cache(maxsize=2048)(_object)

        def invalid(question, causes, tags):
            try:
                return int(not obj(question) or not isinstance(json.loads(causes), list) or not isinstance(json.loads(tags), list))
            except (ValueError, TypeError):
                return 1

        conn.create_function('review_stem', 1, lambda q: str(obj(q).get('stem') or obj(q).get('question') or ''), deterministic=True)
        conn.create_function('review_history', 1, lambda m: int(bool(obj(m).get('read_only_snapshot'))), deterministic=True)
        conn.create_function('review_bad', 3, invalid, deterministic=True)
        conn.create_function('review_cause', 3, lambda raw, old, cause: int(cause in (_list(raw) or []) or _list(raw) == [] and old == cause), deterministic=True)
        return conn, repo

    @staticmethod
    def _course_pairs(read, cid):
        from filemate.course_graph.models import CourseGraphError
        from filemate.course_graph.question_links import question_digest
        from filemate.course_graph.workspace_snapshot import read_workspace_snapshot

        try:
            snapshot = read_workspace_snapshot(read, cid)
        except CourseGraphError as exc:
            if exc.status_code == 404:
                return set()
            raise ValueError('课程映射暂不可核验') from exc
        pairs, artifacts = set(), {}
        for link in read._conn().execute('SELECT * FROM kg_question_links WHERE course_id=? AND active=1', (cid,)):
            source = snapshot.sources.get(link['source_id'])
            if link['concept_id'] not in snapshot.member_to_root or not source or not source['active']:
                continue
            aid = link['artifact_id']
            if aid not in artifacts:
                artifacts[aid] = read.get_artifact(aid)
            artifact = artifacts[aid]
            if not artifact or artifact.get('metadata', {}).get('read_only_snapshot') or artifact['source_id'] != link['source_id']:
                continue
            content, index = artifact['content'], link['question_index']
            try:
                if isinstance(content, list) and 0 <= index < len(content) and question_digest(content[index]) == link['question_digest']:
                    pairs.add((aid, index))
            except (ValueError, TypeError, KeyError):
                continue
        return pairs

    def _where(self, read, filters, conn, repo):
        now = repo.now()
        when = 'filemate_review_time(w.next_review_at)'
        history = 'review_history(a.metadata)'
        bad = f'(review_bad(w.question,w.error_causes,w.custom_tags)=1 OR {when} IS NULL)'
        active = "(w.scheduler_version='review-interval-v2' AND w.schedule_status='active' AND w.learning_status IN ('new','needs_review','provisional'))"
        legacy_done = "(w.scheduler_version!='review-interval-v2' AND w.mastered=1)"
        due = f"(w.schedule_status='active' AND (w.scheduler_version='review-interval-v2' OR w.mastered=0) AND {when}<=?)"
        conditions, params = ['1=1'], []
        status = filters.status
        if status in ('due', 'overdue'):
            if status == 'overdue':
                conditions.append(due.replace('<=?', '<?'))
                params.append(now.astimezone(LOCAL_ZONE).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            else:
                conditions.append(due)
                params.append(now.timestamp())
        elif status != 'all':
            conditions.append({'active': active, 'pending': "w.learning_status='pending_check'",
                'criterion_met': "(w.scheduler_version='review-interval-v2' AND w.learning_status='criterion_met')",
                'legacy_completed': legacy_done, 'paused': "w.schedule_status='paused'", 'history': f'{history}=1', 'invalid': bad}[status])
        if filters.reviewable_only:
            conditions.extend(["w.schedule_status='active'", f'NOT {legacy_done}', f'{history}=0', f'NOT {bad}'])
        for field in ('q', 'knowledge_q'):
            value = getattr(filters, field)
            if value:
                terms = [_stem_expression(conn), 'w.knowledge_label', "COALESCE(s.original_name,'')"] if field == 'q' else ['w.knowledge_label']
                conditions.append('(' + ' OR '.join(f'instr(lower({term}),lower(?))>0' for term in terms) + ')')
                params.extend([value] * len(terms))
        if filters.source_id:
            conditions.append('w.source_id=?'); params.append(filters.source_id)
        if filters.course_id:
            pairs = self._course_pairs(read, filters.course_id)
            conn.create_function('review_course_match', 2, lambda aid, index: int((aid, index) in pairs), deterministic=True)
            conditions.append('review_course_match(w.artifact_id,w.question_index)=1')
        if filters.cause:
            conditions.append('review_cause(w.error_causes,w.error_cause,?)=1'); params.append(filters.cause)
        for key, op in (('min_errors', '>='), ('max_errors', '<=')):
            if getattr(filters, key) is not None:
                conditions.append(f'w.error_count{op}?'); params.append(getattr(filters, key))
        for key in ('due_from', 'due_to', 'created_from', 'created_to'):
            value = getattr(filters, key)
            if value:
                column = 'next_review_at' if key.startswith('due_') else 'created_at'
                op = '>=' if key.endswith('from') else '<='
                conditions.append(f'filemate_review_time(w.{column}){op}?'); params.append(parse_time(value).timestamp())
        return ' AND '.join(conditions), params

    def page(self, filters: ReviewFilter, *, limit=30, offset=0):
        _bounds(limit, offset)
        filters = ReviewFilter.model_validate(filters)
        with self.storage.read_snapshot() as read:
            conn, repo = self._configure(read)
            where, params = self._where(read, filters, conn, repo)
            base = ' FROM wrong_questions w LEFT JOIN artifacts a ON a.artifact_id=w.artifact_id LEFT JOIN sources s ON s.source_id=w.source_id WHERE ' + where
            total = conn.execute('SELECT COUNT(*)' + base, params).fetchone()[0]
            sort = {'due': 'filemate_review_time(w.next_review_at)', 'updated': 'filemate_review_time(w.updated_at)',
                    'created': 'filemate_review_time(w.created_at)', 'errors': 'w.error_count'}[filters.sort]
            rows = conn.execute('SELECT w.*,s.original_name AS source_name,a.metadata AS artifact_metadata' + base +
                f' ORDER BY {sort} {filters.direction},w.wrong_id {filters.direction} LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
            items = []
            for raw in rows:
                row = dict(raw)
                question = _object(row.pop('question'))
                metadata = _object(row.pop('artifact_metadata'))
                row.pop('latest_answer', None)
                row.update(stem=str(question.get('stem') or question.get('question') or '')[:300],
                    question_type=str(question.get('question_type') or question.get('type') or ''),
                    question_digest=digest(question), read_only_snapshot=bool(metadata.get('read_only_snapshot')),
                    data_error=not question or parse_time(row['next_review_at']) is None or _list(row['error_causes']) is None or _list(row['custom_tags']) is None)
                row['error_causes'] = _list(row['error_causes']) or []
                row['custom_tags'] = _list(row['custom_tags']) or []
                items.append(row)
            return {'items': items, 'total': total, 'limit': limit, 'offset': offset,
                    'has_more': offset + len(items) < total, 'as_of': repo.now().isoformat()}

    def options(self, kind, *, q='', limit=30, offset=0):
        _bounds(limit, offset)
        if kind not in ('sources', 'courses') or not isinstance(q, str) or len(q) > 160:
            raise ValueError('筛选选项无效')
        with self.storage.read_snapshot() as read:
            conn = read._conn()
            if kind == 'sources':
                rows = conn.execute('''SELECT DISTINCT s.source_id AS id,s.original_name AS label FROM sources s
                    JOIN wrong_questions w ON w.source_id=s.source_id WHERE instr(lower(s.original_name),lower(?))>0 ORDER BY label,id''', (q,)).fetchall()
                items = [dict(row) for row in rows]
            else:
                rows = conn.execute('SELECT course_id AS id,name AS label FROM kg_courses WHERE instr(lower(name),lower(?))>0 ORDER BY name,course_id', (q,)).fetchall()
                wrongs = {(r[0], r[1]) for r in conn.execute('SELECT artifact_id,question_index FROM wrong_questions')}
                items = [dict(row) for row in rows if self._course_pairs(read, row['id']) & wrongs]
            return {'items': items[offset:offset + limit], 'total': len(items), 'limit': limit,
                    'offset': offset, 'has_more': offset + limit < len(items)}

    def receipt(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', key):
            raise ValueError('请求标识无效')
        row = self.storage._conn().execute('SELECT result FROM review_events WHERE request_key=?', (key,)).fetchone()
        if row is None:
            raise LookupError('暂未找到该操作回执')
        return json.loads(row['result'])


def _list(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, list) else None
    except (ValueError, TypeError):
        return None
