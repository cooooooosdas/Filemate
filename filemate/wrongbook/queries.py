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
from filemate.wrongbook.insights import (
    ERROR_WEIGHT,
    MAX_ERRORS,
    MAX_OVERDUE_DAYS,
    OVERDUE_WEIGHT,
    PRIORITY_RULE_VERSION,
    USER_CAUSE_WEIGHT,
    priority_details,
    review_day,
)
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
    sort: Literal['due', 'updated', 'errors', 'created', 'recommended'] = 'due'
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


def _has_json1(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT json_extract('{}','$.stem') FROM json_each('[0]')")
    except sqlite3.OperationalError:
        return False
    return True


def _stem_expression(conn: sqlite3.Connection) -> str:
    if not _has_json1(conn):
        return 'review_stem(w.question)'
    return """CASE WHEN json_valid(w.question) THEN CASE WHEN json_type(w.question)='object'
        THEN COALESCE(NULLIF(CAST(json_extract(w.question,'$.stem') AS TEXT),''),
                      CAST(json_extract(w.question,'$.question') AS TEXT),'')
        ELSE '' END ELSE '' END"""


def _bad_expression(conn: sqlite3.Connection) -> str:
    if not _has_json1(conn):
        return 'review_bad(w.question,w.error_causes,w.custom_tags)'
    return """CASE WHEN json_valid(w.question) AND json_valid(w.error_causes) AND json_valid(w.custom_tags)
        THEN CASE WHEN json_type(w.question)='object' AND json(w.question)!='{}'
            AND json_type(w.error_causes)='array' AND json_type(w.custom_tags)='array'
            THEN 0 ELSE 1 END ELSE 1 END"""


def _history_expression(conn: sqlite3.Connection) -> str:
    if not _has_json1(conn):
        return 'review_history(a.metadata)'
    return """CASE WHEN json_valid(a.metadata) THEN CASE
        WHEN json_type(a.metadata,'$.read_only_snapshot') IS NULL THEN 0
        WHEN json_type(a.metadata,'$.read_only_snapshot')='true' THEN 1
        WHEN json_type(a.metadata,'$.read_only_snapshot') IN ('false','null') THEN 0
        ELSE review_history(a.metadata) END ELSE review_history(a.metadata) END"""


def _strict_json(raw):
    def invalid_constant(value):
        raise ValueError('non-finite JSON')
    return json.loads(raw, parse_constant=invalid_constant)


def _metadata_valid(raw):
    try:
        return int(isinstance(_strict_json(raw or '{}'), dict))
    except (ValueError, TypeError):
        return 0


def _metadata_expression(conn: sqlite3.Connection) -> str:
    if not _has_json1(conn):
        return 'review_metadata(a.metadata)'
    return """CASE WHEN a.metadata IS NULL OR a.metadata='' THEN 1
        WHEN json_valid(a.metadata) THEN json_type(a.metadata)='object' ELSE 0 END"""


def _text_conditions(filters: ReviewFilter, conn: sqlite3.Connection) -> tuple[list[str], list]:
    conditions, params = [], []
    for field in ('q', 'knowledge_q'):
        value = getattr(filters, field)
        if value:
            terms = ["COALESCE(s.original_name,'')", 'w.knowledge_label', _stem_expression(conn)] if field == 'q' else ['w.knowledge_label']
            conditions.append('(' + ' OR '.join(f'instr(lower({term}),lower(?))>0' for term in terms) + ')')
            params.extend([value] * len(terms))
    if filters.source_id:
        conditions.append('w.source_id=?')
        params.append(filters.source_id)
    return conditions, params


def _time_relation(conn: sqlite3.Connection, wrong_ids: list[str] | None, filters: ReviewFilter) -> str:
    """Convert distinct dates once within the caller's current read snapshot."""
    sql = 'SELECT w.next_review_at FROM wrong_questions w'
    if filters.q:
        sql += ' LEFT JOIN sources s ON s.source_id=w.source_id'
    conditions, params = _text_conditions(filters, conn)
    conditions.insert(0, "typeof(w.next_review_at)='text'")
    if wrong_ids is not None:
        conditions.append('w.wrong_id IN (' + ','.join('?' for _ in wrong_ids) + ')')
        params.extend(wrong_ids)
    raw_dates = conn.execute('SELECT json_group_array(next_review_at) FROM (' + sql + ' WHERE ' +
                             ' AND '.join(conditions) + ' GROUP BY w.next_review_at)', params).fetchone()[0]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    dates = {}
    for raw in json.loads(raw_dates):
        parsed = parse_time(raw)
        if parsed is None:
            continue
        try:
            day = parsed.astimezone(LOCAL_ZONE).date().toordinal()
        except (ValueError, OverflowError):
            day = None
        # Older JSON1 decoders truncate embedded NUL characters in object keys.
        dates[raw.encode('utf-8').hex().upper()] = [(parsed - epoch).total_seconds(), day]
    return json.dumps(dates, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


class ReviewQueries:
    def __init__(self, storage: SQLiteStorage, *, clock: Callable[[], datetime] | None = None):
        self.storage = storage
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _configure(self, read, as_of=None):
        repo = ReviewRepository(read, clock=(lambda: as_of) if as_of is not None else self.clock)
        conn = repo.time_connection()
        obj = lru_cache(maxsize=128)(_object)
        arrays = lru_cache(maxsize=128)(_strict_json)

        def invalid(question, causes, tags):
            try:
                value = _strict_json(question)
                return int(not isinstance(value, dict) or not value or not isinstance(arrays(causes), list) or not isinstance(arrays(tags), list))
            except (ValueError, TypeError):
                return 1

        conn.create_function('review_stem', 1, lambda q: str(obj(q).get('stem') or obj(q).get('question') or ''), deterministic=True)
        conn.create_function('review_history', 1, lambda m: int(bool(obj(m).get('read_only_snapshot'))), deterministic=True)
        conn.create_function('review_bad', 3, invalid, deterministic=True)
        conn.create_function('review_cause', 3, lambda raw, old, cause: int(cause in (_list(raw) or []) or _list(raw) == [] and old == cause), deterministic=True)
        conn.create_function('review_local_day', 1, lru_cache(maxsize=2048)(review_day), deterministic=True)
        conn.create_function('review_metadata', 1, lru_cache(maxsize=128)(_metadata_valid), deterministic=True)
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

    def _where(self, read, filters, conn, repo, *, when='filemate_review_time(w.next_review_at)'):
        now = repo.now()
        history = _history_expression(conn)
        bad = f'({_bad_expression(conn)}=1 OR {when} IS NULL)'
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
        text_conditions, text_params = _text_conditions(filters, conn)
        conditions.extend(text_conditions)
        params.extend(text_params)
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
                expression = when if column == 'next_review_at' else f'filemate_review_time(w.{column})'
                conditions.append(f'{expression}{op}?'); params.append(parse_time(value).timestamp())
        return ' AND '.join(conditions), params

    def page(self, filters: ReviewFilter, *, limit=30, offset=0, eligible_only=False):
        as_of = ReviewRepository(self.storage, clock=self.clock).now()
        with self.storage.read_snapshot() as read:
            return self._snapshot_page(read, filters, as_of=as_of, limit=limit, offset=offset, eligible_only=eligible_only)

    def page_in_snapshot(self, read, filters: ReviewFilter, *, as_of: datetime,
                         source_ids: tuple[str, ...], limit=100, offset=0, eligible_only=False):
        """Apply an authorized bounded source scope before counting or paging."""
        if len(source_ids) > 20 or len(set(source_ids)) != len(source_ids):
            raise ValueError('invalid_source_scope')
        return self._snapshot_page(read, filters, as_of=as_of, limit=limit, offset=offset,
                                   eligible_only=eligible_only, source_ids=source_ids)

    def _snapshot_page(self, read, filters: ReviewFilter, *, as_of: datetime, limit=30, offset=0,
                       eligible_only=False, wrong_ids: list[str] | None = None,
                       source_ids: tuple[str, ...] | None = None):
        _bounds(limit, offset)
        filters = ReviewFilter.model_validate(filters)
        recommended = filters.sort == 'recommended'
        if recommended or eligible_only:
            filters = filters.model_copy(update={'reviewable_only': True})
        if wrong_ids is not None and not 1 <= len(wrong_ids) <= 20:
            raise ValueError('核验题目数量无效')
        conn, repo = self._configure(read, as_of)
        prefix, time_join = '', ''
        time_params = []
        when, day = 'filemate_review_time(w.next_review_at)', 'review_local_day(w.next_review_at)'
        if recommended or eligible_only or filters.sort == 'due':
            key_match = 'rt.raw IS w.next_review_at'
            if _has_json1(conn):
                # TEXT affinity and grouping let SQLite index this snapshot-local relation.
                prefix = """WITH review_times AS (SELECT CAST(key AS TEXT) AS raw,
                    json_extract(value,'$[0]') AS due, json_extract(value,'$[1]') AS local_day
                    FROM json_each(?) GROUP BY key) """
                time_params = [_time_relation(conn, wrong_ids, filters)]
                key_match = "typeof(w.next_review_at)='text' AND rt.raw IS hex(w.next_review_at)"
            elif recommended or eligible_only:
                prefix = """WITH review_times AS (SELECT next_review_at AS raw,
                    filemate_review_time(next_review_at) AS due,
                    review_local_day(next_review_at) AS local_day FROM wrong_questions GROUP BY next_review_at) """
            if prefix:
                join = 'JOIN' if recommended or eligible_only else 'LEFT JOIN'
                time_join = f' {join} review_times rt ON {key_match}'
                when, day = 'rt.due', 'rt.local_day'
        where, params = self._where(read, filters, conn, repo, when=when)
        if source_ids is not None:
            where += ' AND w.source_id IN (' + ','.join('?' for _ in source_ids) + ')' if source_ids else ' AND 0=1'
            params.extend(source_ids)
        if recommended or eligible_only:
            where += f""" AND {when}<=?
                AND {day} IS NOT NULL
                AND typeof(w.error_count)='integer' AND w.error_count>=0
                AND {_metadata_expression(conn)}=1
                AND a.artifact_type='questions' AND a.source_id IS w.source_id
                AND (w.source_id IS NULL OR s.source_id IS NOT NULL)"""
            params.append(as_of.timestamp())
        if wrong_ids is not None:
            where += ' AND w.wrong_id IN (' + ','.join('?' for _ in wrong_ids) + ')'
            params.extend(wrong_ids)
        base = ' FROM wrong_questions w' + time_join + ' LEFT JOIN artifacts a ON a.artifact_id=w.artifact_id LEFT JOIN sources s ON s.source_id=w.source_id WHERE ' + where
        total = conn.execute(prefix + 'SELECT COUNT(*)' + base, [*time_params, *params]).fetchone()[0]
        projection, sort_params = '', []
        if recommended:
            projection = f""", MIN({MAX_OVERDUE_DAYS}, MAX(0, ?-{day}))*{OVERDUE_WEIGHT}
                +MIN({MAX_ERRORS},w.error_count)*{ERROR_WEIGHT}
                +CASE WHEN w.error_cause_source='user' THEN {USER_CAUSE_WEIGHT} ELSE 0 END AS _rank_score"""
            sort_params = [review_day(as_of.isoformat())]
            order = f'_rank_score DESC,{when} ASC,w.wrong_id ASC'
        else:
            sort = {'due': when, 'updated': 'filemate_review_time(w.updated_at)',
                    'created': 'filemate_review_time(w.created_at)', 'errors': 'w.error_count'}[filters.sort]
            order = f'{sort} {filters.direction},w.wrong_id {filters.direction}'
        rows = conn.execute(prefix + 'SELECT w.*,s.original_name AS source_name,a.metadata AS artifact_metadata' + projection + base +
            f' ORDER BY {order} LIMIT ? OFFSET ?', [*time_params, *sort_params, *params, limit, offset]).fetchall()
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
            if recommended:
                row['priority'] = priority_details(row, now=as_of)
                if row.pop('_rank_score') != row['priority']['priority_score']:
                    raise ValueError('推荐依据暂不可核验')
            items.append(row)
        result = {'items': items, 'total': total, 'limit': limit, 'offset': offset,
                  'has_more': offset + len(items) < total, 'as_of': as_of.isoformat()}
        if recommended:
            result.update(priority_rule_version=PRIORITY_RULE_VERSION,
                          recommendation_scope='filtered_eligible_due', day_zone='Asia/Shanghai',
                          priority_rule_note='队列启发式排序，非掌握率或学习效果评价')
        return result

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
        row = self.storage._conn().execute('''SELECT e.result,q.artifact_id,q.question_index,q.question_digest
            FROM review_events e LEFT JOIN quiz_attempts q ON q.attempt_id=e.attempt_id
            WHERE e.request_key=?''', (key,)).fetchone()
        if row is None:
            raise LookupError('暂未找到该操作回执')
        result = json.loads(row['result'])
        if result.get('attempt_id'):
            if row['artifact_id'] is None:
                raise LookupError('作答证据已不存在，暂不能核验该回执')
            result.update(artifact_id=row['artifact_id'], question_index=row['question_index'],
                          question_digest=row['question_digest'])
        return result


def _list(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, list) else None
    except (ValueError, TypeError):
        return None
