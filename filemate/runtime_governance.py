"""跨请求持久化模型准入、用量与脱敏审计，不随个人业务备份恢复。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import psutil

from filemate.llm_client.exceptions import LLMAPIError
from filemate.llm_client.models.response import safe_request_id, validated_usage

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 1
SCHEMA_TABLES = frozenset({'resource_schema_migrations', 'resource_daily', 'ai_attempts'})
DAY_TIMEZONE = timezone(timedelta(hours=8))
GLOBAL_OWNER = '__global__'
OwnerKind = Literal['account', 'guest', 'local']

_SCHEMA = (
    "CREATE TABLE resource_schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)",
    """CREATE TABLE resource_daily(
        owner_hash TEXT NOT NULL, day TEXT NOT NULL,
        attempts INTEGER NOT NULL CHECK(attempts>=0),
        budget_units INTEGER NOT NULL CHECK(budget_units>=0),
        PRIMARY KEY(owner_hash, day))""",
    """CREATE TABLE ai_attempts(
        attempt_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, owner_hash TEXT NOT NULL,
        day TEXT NOT NULL, operation TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
        started_at REAL NOT NULL, finished_at REAL, duration_ms INTEGER,
        status TEXT NOT NULL CHECK(status IN ('inflight','success','failed','abandoned')),
        error_code TEXT, request_id TEXT, budget_units INTEGER NOT NULL CHECK(budget_units>=0),
        prompt_tokens INTEGER CHECK(prompt_tokens>=0), completion_tokens INTEGER CHECK(completion_tokens>=0),
        total_tokens INTEGER CHECK(total_tokens>=0),
        pid INTEGER NOT NULL, process_started_at REAL NOT NULL)""",
    "CREATE INDEX ai_attempts_owner_time ON ai_attempts(owner_hash, started_at DESC, attempt_id)",
    "CREATE INDEX ai_attempts_status_owner ON ai_attempts(status, owner_hash)",
    "CREATE INDEX ai_attempts_retention ON ai_attempts(finished_at)",
)


class GovernanceUnavailable(LLMAPIError):
    """治理账本故障时拒绝新的外部调用，但不阻止读取和删除业务数据。"""


class BudgetExceeded(LLMAPIError):
    """累计或并发预算不足，调用尚未发往供应商。"""


@dataclass(frozen=True)
class Limits:
    attempts: int
    budget_units: int
    concurrent: int


@dataclass(frozen=True)
class Policy:
    account: Limits = Limits(300, 2_000_000, 4)
    guest: Limits = Limits(60, 250_000, 4)
    local: Limits = Limits(1000, 10_000_000, 4)
    global_limits: Limits = Limits(3000, 20_000_000, 16)
    retention_days: int = 30

    def __post_init__(self) -> None:
        for limits in (self.account, self.guest, self.local, self.global_limits):
            for value, maximum in ((limits.attempts, 100_000),
                                   (limits.budget_units, 1_000_000_000),
                                   (limits.concurrent, 64)):
                if type(value) is not int or not 1 <= value <= maximum:
                    raise ValueError('模型预算配置必须为范围内的正整数')
        if type(self.retention_days) is not int or not 1 <= self.retention_days <= 90:
            raise ValueError('模型审计保留天数必须为1至90天')

    @classmethod
    def from_env(cls) -> Policy:
        default = cls()
        configured = {}
        for name in ('account', 'guest', 'local', 'global'):
            limits = default.global_limits if name == 'global' else getattr(default, name)
            values = [int(os.getenv(f'FILEMATE_AI_{name.upper()}_{field}', str(value)))
                      for field, value in (('DAILY_ATTEMPTS', limits.attempts),
                                           ('DAILY_BUDGET_UNITS', limits.budget_units),
                                           ('CONCURRENT', limits.concurrent))]
            configured['global_limits' if name == 'global' else name] = Limits(*values)
        return cls(**configured, retention_days=int(os.getenv('FILEMATE_AI_RETENTION_DAYS', '30')))


def owner_digest(owner: str) -> str:
    if owner != 'local' and not re.fullmatch(r'u_[0-9a-f]{32}', owner):
        raise ValueError('模型用量必须绑定服务端解析的学习空间')
    return hashlib.sha256(owner.encode('utf-8')).hexdigest()


def _label(value: Any, secret: str = '') -> str:
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,96}', value)
            or (secret and secret in value)):
        return 'unavailable'
    return value


def _alive(pid: int, born: float) -> bool:
    """仅回收已退出的执行进程，避免慢响应超时后仍存活却释放并发位。"""
    try:
        process = psutil.Process(pid)
        return process.create_time() == born and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


@dataclass(frozen=True)
class Scope:
    store: BudgetStore
    owner_hash: str
    kind: OwnerKind
    operation: str
    trace_id: str


CURRENT_SCOPE: ContextVar[Scope | None] = ContextVar('filemate_resource_scope', default=None)


@contextmanager
def resource_scope(store: BudgetStore, owner: str, kind: OwnerKind,
                   operation: str = 'model.local') -> Iterator[Scope]:
    if kind not in {'account', 'guest', 'local'} or (owner == 'local') != (kind == 'local'):
        raise ValueError('学习空间与模型预算类型不一致')
    scope = Scope(store, owner_digest(owner), kind, _label(operation), uuid.uuid4().hex)
    token = CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        CURRENT_SCOPE.reset(token)


def default_scope() -> Scope:
    scope = CURRENT_SCOPE.get()
    if scope is not None:
        return scope
    if os.getenv('FILEMATE_ENV', 'development').lower() == 'production':
        raise GovernanceUnavailable('模型请求缺少可信学习空间，请重新登录后重试')
    root = Path(os.getenv('FILEMATE_DATA_DIR', str(Path(__file__).resolve().parent.parent / '.filemate-data')))
    # 本地脚本也执行预算，不通过缺失HTTP上下文绕过限制。
    store = _default_store(root / 'control' / 'resource-governance.db')
    return Scope(store, owner_digest('local'), 'local', 'model.local', uuid.uuid4().hex)


_DEFAULT_LOCK = threading.Lock()
_DEFAULT: BudgetStore | None = None


def _default_store(path: Path) -> BudgetStore:
    global _DEFAULT
    with _DEFAULT_LOCK:
        policy = Policy.from_env()
        if _DEFAULT is None or _DEFAULT.path != path.resolve() or _DEFAULT.policy != policy:
            _DEFAULT = BudgetStore(path, policy)
        return _DEFAULT


class BudgetStore:
    """独立控制数据库以原子事务约束同主机的多进程调用。"""

    def __init__(self, path: Path, policy: Policy | None = None) -> None:
        self.path = Path(path).resolve()
        self.policy = policy or Policy.from_env()
        self._pending: dict[str, dict[str, Any]] = {}
        self._pending_lock = threading.RLock()
        self._init_lock = threading.Lock()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            self.initialize()
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA busy_timeout=5000')
            with connection:
                yield connection
        except (sqlite3.Error, OSError) as exc:
            logger.warning('模型治理账本暂不可用: %s', type(exc).__name__)
            raise GovernanceUnavailable('模型用量记录暂不可用，请稍后重试') from exc
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        with self._init_lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('BEGIN IMMEDIATE')
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if not tables:
                    for statement in _SCHEMA:
                        connection.execute(statement)
                    connection.execute('INSERT INTO resource_schema_migrations VALUES (?,?)',
                                       (SCHEMA_VERSION, time.time()))
                elif tables != SCHEMA_TABLES or connection.execute(
                        'SELECT version FROM resource_schema_migrations').fetchall() != [(SCHEMA_VERSION,)]:
                    raise GovernanceUnavailable('模型治理账本版本不兼容，请联系维护者')
            self.path.chmod(0o600)

    @staticmethod
    def _day(now: float) -> str:
        return datetime.fromtimestamp(now, DAY_TIMEZONE).date().isoformat()

    @staticmethod
    def _cleanup(connection: sqlite3.Connection, now: float, retention_days: int) -> None:
        for row in connection.execute(
                "SELECT DISTINCT pid,process_started_at FROM ai_attempts WHERE status='inflight'").fetchall():
            if not _alive(row['pid'], row['process_started_at']):
                connection.execute("""UPDATE ai_attempts SET status='abandoned',
                    error_code='process_exit',finished_at=?,duration_ms=CAST((?-started_at)*1000 AS INTEGER)
                    WHERE status='inflight' AND pid=? AND process_started_at=?""",
                                   (now, now, row['pid'], row['process_started_at']))
        cutoff = now - retention_days * 86400
        connection.execute("DELETE FROM ai_attempts WHERE status!='inflight' AND finished_at<?", (cutoff,))
        connection.execute('DELETE FROM resource_daily WHERE day<?', (BudgetStore._day(cutoff),))

    def reserve(self, scope: Scope, *, provider: str, model: str, budget_units: int,
                secret: str = '') -> Attempt:
        if scope.store is not self or type(budget_units) is not int or budget_units < 0:
            raise ValueError('模型准入参数无效')
        self.flush_pending()
        now = time.time()
        day, identifier = self._day(now), uuid.uuid4().hex
        pid = os.getpid()
        born = psutil.Process(pid).create_time()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._cleanup(connection, now, self.policy.retention_days)
            for owner, limits in ((scope.owner_hash, getattr(self.policy, scope.kind)),
                                  (GLOBAL_OWNER, self.policy.global_limits)):
                row = connection.execute('SELECT attempts,budget_units FROM resource_daily WHERE owner_hash=? AND day=?',
                                         (owner, day)).fetchone()
                attempts, units = tuple(row) if row else (0, 0)
                if attempts + 1 > limits.attempts or units + budget_units > limits.budget_units:
                    raise BudgetExceeded('今日模型调用额度已用完，请明日再试或联系维护者')
                inflight = connection.execute(
                    "SELECT COUNT(*) FROM ai_attempts WHERE status='inflight'" +
                    ('' if owner == GLOBAL_OWNER else ' AND owner_hash=?'),
                    () if owner == GLOBAL_OWNER else (owner,)).fetchone()[0]
                if inflight >= limits.concurrent:
                    raise BudgetExceeded('模型调用正在处理其他请求，请稍后重试')
            for owner in (scope.owner_hash, GLOBAL_OWNER):
                connection.execute("""INSERT INTO resource_daily VALUES (?,?,1,?)
                    ON CONFLICT(owner_hash,day) DO UPDATE SET attempts=attempts+1,budget_units=budget_units+excluded.budget_units""",
                                   (owner, day, budget_units))
            connection.execute("""INSERT INTO ai_attempts(attempt_id,trace_id,owner_hash,day,operation,
                provider,model,started_at,status,budget_units,pid,process_started_at)
                VALUES (?,?,?,?,?,?,?,?,'inflight',?,?,?)""",
                               (identifier, scope.trace_id, scope.owner_hash, day, scope.operation,
                                _label(provider, secret), _label(model, secret), now, budget_units, pid, born))
        return Attempt(self, identifier, scope.owner_hash, secret)

    def _settle(self, identifier: str, payload: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM ai_attempts WHERE attempt_id=?', (identifier,)).fetchone()
            if not row or row['status'] != 'inflight':
                return
            usage = payload['usage']
            known_total = usage.get('total_tokens')
            if 'prompt_tokens' in usage and 'completion_tokens' in usage:
                known_total = max(known_total or 0, usage['prompt_tokens'] + usage['completion_tokens'])
            # 未知用量保留预留值；它是准入预算单位，不能显示为真实token或费用。
            units = max(known_total or 0, row['budget_units'])
            for owner in (row['owner_hash'], GLOBAL_OWNER):
                connection.execute('UPDATE resource_daily SET budget_units=budget_units+? WHERE owner_hash=? AND day=?',
                                   (units - row['budget_units'], owner, row['day']))
            connection.execute("""UPDATE ai_attempts SET status=?,error_code=?,request_id=?,finished_at=?,
                duration_ms=?,budget_units=?,prompt_tokens=?,completion_tokens=?,total_tokens=?
                WHERE attempt_id=? AND status='inflight'""",
                               (payload['status'], payload['error_code'], payload['request_id'],
                                payload['finished_at'], max(0, round((payload['finished_at'] - row['started_at']) * 1000)),
                                units, usage.get('prompt_tokens'), usage.get('completion_tokens'),
                                usage.get('total_tokens'), identifier))

    def settle(self, identifier: str, payload: dict[str, Any]) -> None:
        with self._pending_lock:
            self._pending[identifier] = payload
            # 未结算记录保留并发位，待账本恢复；不在故障期间继续发出外部调用。
            self._settle(identifier, payload)
            self._pending.pop(identifier, None)

    def flush_pending(self) -> None:
        with self._pending_lock:
            for identifier, payload in list(self._pending.items()):
                self._settle(identifier, payload)
                self._pending.pop(identifier, None)

    def maintain(self) -> None:
        self.flush_pending()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._cleanup(connection, time.time(), self.policy.retention_days)

    def purge_owner_hash(self, digest: str) -> None:
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('模型用量删除标识无效')
        with self._pending_lock, self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            # 匿名全站累计仍保留，避免注册/注销反复重置公共资源额度。
            connection.execute('DELETE FROM ai_attempts WHERE owner_hash=?', (digest,))
            connection.execute('DELETE FROM resource_daily WHERE owner_hash=?', (digest,))
            for identifier, payload in list(self._pending.items()):
                if payload['owner_hash'] == digest:
                    self._pending.pop(identifier, None)

    def owner_hashes(self) -> list[str]:
        with self._connection() as connection:
            return [row[0] for row in connection.execute(
                'SELECT owner_hash FROM ai_attempts UNION SELECT owner_hash FROM resource_daily WHERE owner_hash!=?',
                (GLOBAL_OWNER,))]

    def view(self, scope: Scope, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if scope.store is not self or type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('模型用量查询参数无效')
        self.flush_pending()
        now, limits = time.time(), getattr(self.policy, scope.kind)
        day = self._day(now)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._cleanup(connection, now, self.policy.retention_days)
            daily = connection.execute('SELECT attempts,budget_units FROM resource_daily WHERE owner_hash=? AND day=?',
                                       (scope.owner_hash, day)).fetchone()
            rows = connection.execute("""SELECT attempt_id,trace_id,operation,provider,model,started_at,
                finished_at,duration_ms,status,error_code,request_id,budget_units,prompt_tokens,
                completion_tokens,total_tokens FROM ai_attempts WHERE owner_hash=?
                ORDER BY started_at DESC,attempt_id DESC LIMIT ? OFFSET ?""",
                                      (scope.owner_hash, limit, offset)).fetchall()
            count = connection.execute('SELECT COUNT(*) FROM ai_attempts WHERE owner_hash=?', (scope.owner_hash,)).fetchone()[0]
            reported = dict(connection.execute("""SELECT SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,SUM(total_tokens) AS total_tokens
                FROM ai_attempts WHERE owner_hash=? AND day=?""", (scope.owner_hash, day)).fetchone())
            reported_counts = dict(connection.execute("""SELECT COUNT(prompt_tokens) AS prompt_tokens,
                COUNT(completion_tokens) AS completion_tokens,COUNT(total_tokens) AS total_tokens
                FROM ai_attempts WHERE owner_hash=? AND day=?""", (scope.owner_hash, day)).fetchone())
            coverage = connection.execute('SELECT applied_at FROM resource_schema_migrations WHERE version=?', (SCHEMA_VERSION,)).fetchone()[0]
        reset = datetime.fromisoformat(day).replace(tzinfo=DAY_TIMEZONE) + timedelta(days=1)
        return {'available': True, 'day': day, 'timezone': 'UTC+08:00', 'reset_at': reset.isoformat(),
                'coverage_started_at': coverage, 'retention_days': self.policy.retention_days,
                'daily': {'attempts': daily['attempts'] if daily else 0,
                          'budget_units': daily['budget_units'] if daily else 0,
                          'limits': {'attempts': limits.attempts, 'budget_units': limits.budget_units,
                                     'concurrent': limits.concurrent}, 'reported_tokens': reported,
                          'reported_field_counts': reported_counts},
                'cost': {'status': 'not_available', 'amount': None, 'currency': None},
                'total': count, 'limit': limit, 'offset': offset, 'items': [dict(row) for row in rows]}

    def export(self, scope: Scope) -> dict[str, Any]:
        summary = self.view(scope, 1)
        summary.pop('limit')
        summary.pop('offset')
        summary['items'] = []
        size = 0
        with self._connection() as connection:
            for row in connection.execute("""SELECT attempt_id,trace_id,operation,provider,model,started_at,
                finished_at,duration_ms,status,error_code,request_id,budget_units,prompt_tokens,
                completion_tokens,total_tokens FROM ai_attempts WHERE owner_hash=?
                ORDER BY started_at DESC,attempt_id DESC""", (scope.owner_hash,)):
                record = dict(row)
                size += len(json.dumps(record).encode('utf-8'))
                if size > 32 * 1024 * 1024:
                    raise GovernanceUnavailable('模型审计导出超过32MB，请按页导出用量记录')
                summary['items'].append(record)
        summary['total'] = len(summary['items'])
        return summary


@dataclass
class Attempt:
    store: BudgetStore
    identifier: str
    owner_hash: str
    secret: str = field(repr=False)
    finished: bool = False

    def finish(self, *, status: Literal['success', 'failed'], usage: Any = None,
               request_id: Any = None, error_code: str | None = None) -> None:
        if self.finished:
            return
        safe_id = safe_request_id(request_id)
        if self.secret and safe_id and self.secret in safe_id:
            safe_id = None
        payload = {'status': status, 'usage': validated_usage(usage), 'request_id': safe_id,
                   'error_code': _label(error_code) if error_code else None, 'finished_at': time.time(),
                   'owner_hash': self.owner_hash}
        self.finished = True
        self.secret = ''
        self.store.settle(self.identifier, payload)


def input_budget_units(messages: list[dict[str, str]], max_tokens: int) -> int:
    """保守准入单位并非供应商tokenizer计数，失败调用也不退款以防无限重试。"""
    return len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + max_tokens + 128 * len(messages)
