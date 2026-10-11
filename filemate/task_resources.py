"""现役学习任务和隔离评测的统一资源准入，不包含任务正文。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filemate.runtime_governance import GovernanceUnavailable, Scope, default_scope

logger = logging.getLogger(__name__)
PLAN_TYPES = frozenset({'study_plan', 'reverse_goal_plan'})
PROGRESS_FIELDS = frozenset({'status', 'completed', 'completed_at', 'updated_at', 'progress'})


def _bound_scope(db_path: Path | None) -> Scope:
    scope = default_scope()
    if scope.managed_db_path is not None:
        if db_path is not None and Path(db_path).resolve() != scope.managed_db_path:
            raise GovernanceUnavailable('资源操作与当前学习空间不一致，请重新登录')
    elif os.getenv('FILEMATE_ENV', 'development').lower() == 'production':
        raise GovernanceUnavailable('资源操作缺少可信数据库绑定，请重新登录')
    return scope


def task_inventory(content: Any) -> Counter[str]:
    """按任务内容计数，完成标记变化不会变成新任务。"""
    result: Counter[str] = Counter()
    if not isinstance(content, dict):
        return result

    def add(task: Any, day: Any = None) -> None:
        value = {key: item for key, item in task.items() if key not in PROGRESS_FIELDS} if isinstance(task, dict) else task
        identity = json.dumps([day, value], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        result[hashlib.sha256(identity.encode('utf-8')).hexdigest()] += 1

    tasks = content.get('tasks')
    if isinstance(tasks, list):
        for task in tasks:
            add(task)
    days = content.get('daily_plan')
    if isinstance(days, list):
        for index, day in enumerate(days):
            if isinstance(day, dict) and isinstance(day.get('tasks'), list):
                for task in day['tasks']:
                    add(task, [day.get('day', index + 1), day.get('date')])
    return result


def admit_tasks(db_path: Path, amount: int) -> None:
    if type(amount) is not int or amount < 0:
        raise ValueError('任务数量无效')
    if amount:
        scope = _bound_scope(db_path)
        scope.store.admit_resource(scope, 'tasks', amount)


def admit_plan(db_path: Path, artifact_type: str, content: Any, previous: Any = None) -> None:
    if artifact_type in PLAN_TYPES:
        admit_tasks(db_path, sum((task_inventory(content) - task_inventory(previous)).values()))


@contextmanager
def execution_budget(db_path: Path | None = None) -> Iterator[None]:
    scope = _bound_scope(db_path)
    lease = scope.store.admit_resource(scope, 'execution')
    error_code = None
    try:
        yield
    except BaseException as exc:
        error_code = type(exc).__name__
        raise
    finally:
        try:
            lease.finish('failed' if error_code else 'success', error_code)
        except GovernanceUnavailable:
            # 已完成的判题不重跑；保留未结算并发位，由维护重试。
            logger.warning('隔离评测准入记录等待结算')
