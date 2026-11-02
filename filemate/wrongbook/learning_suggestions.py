"""Compute bounded next actions from actual versioned training evidence."""

from datetime import timedelta

from filemate.execution.data_actions import digest
from filemate.study.knowledge_graph import _after_question_revision
from filemate.wrongbook.engine import parse_time
from filemate.wrongbook.evidence import trusted_attempt

PLAN_RULE_VERSION = 'review-learning-actions-v1'


def build_suggestions(read, detail, now, quotes):
    """Keep suggestions distinct from grades and avoid expanding a single error."""
    if detail['read_only_snapshot'] or detail.get('data_error'):
        return []
    artifact = read.get_artifact(detail['artifact_id'])
    counts = {'trusted_total': 0, 'trusted_incorrect': 0, 'pending_total': 0, 'total': 0}
    ids = []
    cutoff = now-timedelta(days=30)
    for raw in read._conn().execute('''SELECT rowid AS evidence_sequence,attempt_id,created_at,is_correct,score,
            judgement_status,judgement_method,rule_version,answer_revealed,question_digest
            FROM quiz_attempts WHERE artifact_id=? AND question_index=? ORDER BY created_at DESC,rowid DESC''',
            (detail['artifact_id'], detail['question_index'])):
        row = dict(raw)
        moment = parse_time(row['created_at'])
        if (moment is None or not cutoff <= moment <= now or not _after_question_revision(row, artifact)
                or row['question_digest'] not in {'', detail['question_digest']}):
            continue
        counts['total'] += 1
        if len(ids) < 30:
            ids.append(row['attempt_id'])
        trusted = trusted_attempt(row)
        counts['trusted_total'] += int(trusted)
        counts['trusted_incorrect'] += int(trusted and row['is_correct'] == 0)
        counts['pending_total'] += int(not trusted)
    due = parse_time(detail['next_review_at'])
    overdue = max(0, (now-due).days) if due and detail['schedule_status'] == 'active' else 0
    causes = detail['error_causes'] if detail['error_cause_source'] == 'user' else []
    basis = {'wrong_id': detail['wrong_id'], 'attempt_ids': ids, 'attempts_omitted': max(0, counts['total']-len(ids)),
        'window_days': 30, **counts, 'overdue_days': overdue, 'confirmed_causes': causes, 'rule_version': PLAN_RULE_VERSION}
    stem = str(detail['question'].get('stem') or detail['question'].get('question') or '这道题')[:50]
    route = '/wrongbook?focus='+detail['wrong_id']
    definitions = [('review', '复盘一次原答', f'先独立解释“{stem}”，再核对原答与已确认的依据。', 10)]
    if counts['trusted_incorrect'] >= 2 or overdue >= 1 or causes:
        if quotes:
            definitions.append(('read:'+quotes[0]['evidence_id'], '回到资料核对依据', '阅读此题的已核验连续片段，用自己的话写出定义与边界。', 10))
        definitions.append(('practice', '再做一次独立练习', '遮住参考答案独立作答，提交后核对；任务勾选不代表答对。', 15))
        for cause in causes:
            definitions.append(('cause:'+cause, '围绕已确认错因做检查', '按你确认的错因逐步检查原回答，记录下一次可以执行的检查步骤。', 10))
    return [{'action_id': digest([PLAN_RULE_VERSION, detail['wrong_id'], key]), 'kind': key.split(':')[0],
        'title': title, 'instructions': instructions, 'duration_minutes': minutes, 'day_offset': i,
        'basis': basis, 'route': route} for i, (key, title, instructions, minutes) in enumerate(definitions[:7])]
