"""Stable projections of existing actions, never a second completion store."""

from urllib.parse import urlencode

from filemate.execution.data_actions import digest
from filemate.wrongbook.engine import parse_time

from .models import EvidenceSnapshot, TaskProjection, TaskView

GOAL_ESTIMATES = {'import-source': 5, 'review-source': 15, 'baseline-quiz': 20,
                  'explain-wrong-aloud': 12, 'build-study-plan': 10, 'baseline-interview': 15,
                  'review-evidence': 5}


def review_key(wrong_id: str, due: str) -> str | None:
    value = parse_time(due)
    return f'review:{wrong_id}:{digest(value.isoformat())[:24]}:independent_review' if value else None


def project_tasks(snapshot: EvidenceSnapshot) -> TaskProjection:
    scope, facts = snapshot.scope, snapshot.facts
    pending, completed, unavailable, overlaps = [], [], [], []
    actions = {}
    total = 0

    def add(task):
        nonlocal total
        total += 1
        if task.action_key and task.action_key in actions:
            actions[task.action_key].origin_refs.extend(task.origin_refs)
            return
        if len(pending) + len(completed) >= 200:
            return
        if task.action_key:
            actions[task.action_key] = task
        (completed if task.status == 'completed' else pending).append(task)

    def view(tid, kind, title, origin, route, **values):
        return TaskView(task_id=tid, kind=kind, title=str(title)[:160], goal_id=scope.goal_id,
                        course_id=scope.course_id, origin_refs=[origin], evidence_refs=[origin],
                        route=route, reason='依据原功能保存的任务与学习记录；不代表能力达标', **values)

    for row in facts['reviews']:
        wid = row['wrong_id']
        key = review_key(wid, row['next_review_at'])
        if row['data_error'] or row['read_only_snapshot'] or key is None:
            unavailable.append({'kind': 'review', 'id': wid, 'reason': 'invalid_or_historical_evidence'})
            continue
        done = row['learning_status'] == 'criterion_met' or (row['scheduler_version'] != 'review-interval-v2' and row['mastered'] == 1)
        eligibility = 'eligible'
        if row['schedule_status'] != 'active':
            eligibility = 'paused'
        elif row['learning_status'] == 'pending_check':
            eligibility = 'pending_check'
        elif parse_time(row['next_review_at']) > snapshot.as_of:
            eligibility = 'not_due'
        ref = {'kind': 'review', 'id': wid, 'cycle': key}
        add(view(key, 'review', '独立复练一道错题', ref, '/wrongbook?' + urlencode({'wrong_id': wid}),
                 source_id=row['source_id'], due_date=row['next_review_at'], estimated_minutes=10,
                 estimate_source='rule_default', action_key=key, eligibility=eligibility,
                 recorded_errors=max(0, row['error_count']) if type(row['error_count']) is int else 0,
                 status='completed' if done else 'pending', completion_ref=ref if done else None))
    for row in facts['goal']['tasks']:
        template = row.get('task_id')
        if not isinstance(template, str) or not template or len(template) > 128:
            unavailable.append({'kind': 'goal', 'id': scope.goal_id, 'reason': 'invalid_task'})
            continue
        origin = {'kind': 'goal', 'id': scope.goal_id, 'template_id': template}
        tid = f'goal:{scope.goal_id}:{template}'
        action = None
        if row.get('action') == 'independent_review' and row.get('focus_wrong_id') and row.get('next_review_at'):
            action = review_key(row['focus_wrong_id'], row['next_review_at'])
        minutes = row.get('duration_minutes', GOAL_ESTIMATES.get(template))
        if type(minutes) is not int or not 1 <= minutes <= 240:
            minutes = None
        done = row.get('status') == 'completed'
        add(view(tid, 'goal', row.get('title', template), origin,
                 '/goals?' + urlencode({'goal_id': scope.goal_id, 'task_id': template}),
                 source_id=facts['goal'].get('source_id'), due_date=row.get('due_date') or facts['goal'].get('deadline'),
                 estimated_minutes=minutes, estimate_source=('domain_estimate' if 'duration_minutes' in row else 'rule_default') if minutes else None,
                 action_key=action, status='completed' if done else 'pending', completion_ref=origin if done else None))
    for plan in facts['plans']:
        for day in plan['days']:
            tid = f"plan:{plan['plan_id']}:{day['day_index']}"
            ref = {'kind': 'plan', 'id': plan['plan_id'], 'day_index': day['day_index']}
            done = day['completed']
            minutes = day.get('duration_minutes')
            if type(minutes) is not int or not 1 <= minutes <= 240:
                minutes = None
            add(view(tid, 'plan', f"学习计划第{day['day']}天", ref,
                     '/study-plan?' + urlencode({'plan_id': plan['plan_id'], 'day': day['day']}),
                     source_id=plan['source_id'], due_date=day.get('date') or plan.get('exam_date'),
                     estimated_minutes=minutes, estimate_source='domain_estimate' if minutes else None,
                     status='completed' if done else 'pending', completion_ref=ref if done else None,
                     eligibility='eligible' if plan['status'] != 'archived' else 'archived'))
    for row in facts['semester']:
        if not row.get('task_id'):
            continue
        ref = {'kind': 'semester', 'id': row['artifact_id'], 'task_id': row['task_id']}
        done = row.get('completed') is True
        minutes = row.get('minutes')
        if type(minutes) is not int or not 1 <= minutes <= 240:
            minutes = None
        add(view(f"semester:{row['artifact_id']}:{row['task_id']}", 'semester', row.get('title', '学期任务'), ref,
                 '/semester?' + urlencode({'task_id': row['task_id']}), due_date=row.get('due_date'),
                 estimated_minutes=minutes, estimate_source='domain_estimate' if minutes else None,
                 status='completed' if done else 'pending', completion_ref=ref if done else None))
    if facts['reviews'] and facts['plans']:
        overlaps.append({'kinds': ['review', 'plan'], 'reason': 'composite_day_not_deduplicated'})
    return TaskProjection(tasks=pending, completed=completed, unavailable=unavailable[:100], overlaps=overlaps,
                          coverage={'candidate_origins': total, 'returned': len(pending) + len(completed),
                                    'truncated': total > len(pending) + len(completed), 'evidence': snapshot.coverage})
