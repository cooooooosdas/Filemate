"""Bounded stored goal metadata for choosing an explicit learning scope."""

from datetime import date
from typing import Any

from filemate.execution.storage import SQLiteStorage

from .models import GoalChoice, GoalOptionsPage, GoalOptionsRequest
from .snapshot_queries import object_json


def display_label(value: Any, limit: int, fallback: str) -> str:
    """Keep display metadata bounded without changing the stored record."""
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else fallback


def read_goal_options(storage: SQLiteStorage, request: GoalOptionsRequest) -> GoalOptionsPage:
    """Read one metadata page in the caller's existing isolated storage."""
    needle = request.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    label = "coalesce(nullif(trim(title),''),'未命名目标')"
    where = f"artifact_type=? AND {label} LIKE ? ESCAPE '\\'"
    params = ('reverse_goal_plan', '%' + needle + '%')
    with storage.read_snapshot() as read:
        conn = read._conn()
        total = conn.execute(f'SELECT count(*) FROM artifacts WHERE {where}', params).fetchone()[0]
        rows = conn.execute(f'''SELECT artifact_id,substr({label},1,160) AS title,source_id,
            CASE WHEN length(CAST(content AS BLOB))<=1048576 THEN content END AS content
            FROM artifacts WHERE {where} ORDER BY updated_at DESC,artifact_id LIMIT 30 OFFSET ?''',
            (*params, request.offset))
        items = []
        for row in rows:
            goal = object_json(row['content'])
            valid = goal is not None and isinstance(goal.get('tasks', []), list)
            goal = goal or {}
            goal_type = goal.get('goal_type')
            if goal_type not in (None, 'exam', 'competition', 'job', 'postgraduate', 'custom'):
                goal_type, valid = None, False
            deadline = goal.get('deadline')
            if deadline is not None:
                try:
                    if not isinstance(deadline, str) or date.fromisoformat(deadline).isoformat() != deadline:
                        raise ValueError('invalid_deadline')
                except ValueError:
                    deadline, valid = None, False
            items.append(GoalChoice(goal_id=row['artifact_id'], title=row['title'], source_id=row['source_id'],
                                    goal_type=goal_type, deadline=deadline, valid=valid))
        return GoalOptionsPage(items=items, total=total, offset=request.offset)
