# ruff: noqa: F811
"""Synthetic records exercise conservative training windows and course isolation."""

import importlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from filemate.tests.course_graph.test_fusion import change, merge, pair  # noqa: F401
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401

NOW = datetime(2026, 10, 23, 4, tzinfo=timezone.utc)


def module():
    return importlib.import_module('filemate.course_graph.learning_evidence')


def state(context):
    store, cid, _, nid, *_ = context
    return module().node_learning_evidence(store, cid, nid, now=NOW)


def attempt(context, when, correct=True, aid=None, index=0):
    store, _, _, _, original, *_ = context
    result = store.record_quiz_attempt(artifact_id=aid or original, question_index=index,
        user_answer='后进先出' if correct else '不知道', is_correct=correct,
        score=1 if correct else 0, feedback='合成工程记录')
    with store._conn() as conn:
        conn.execute('UPDATE quiz_attempts SET created_at=? WHERE attempt_id=?',
                     (when.isoformat() if isinstance(when, datetime) else when, result['attempt_id']))
        if not correct:
            conn.execute('UPDATE wrong_questions SET updated_at=? WHERE artifact_id=? AND question_index=?',
                         (when.isoformat() if isinstance(when, datetime) else when, aid or original, index))
    return result['attempt_id']


def three_questions(context):
    store, _cid, sid, _nid, _, question = context
    result = []
    for i in range(3):
        aid = store.save_artifact(artifact_type='questions', source_id=sid,
            content=[{**question, 'stem': f'栈的第{i + 1}个练习：____。'}])
        from filemate.course_graph.question_links import question_digest
        item = [{'artifact_id': aid, 'question_index': 0,
                 'question_digest': question_digest(store.get_artifact(aid)['content'][0])}]
        confirm(context, item, key=f'learning_link_test_{i:02}')
        result.append(aid)
    return result


def test_empty_once_and_stable_windows(learning_context):
    assert state(learning_context)['status'] == 'no_evidence'
    aids = three_questions(learning_context)
    attempt(learning_context, NOW - timedelta(days=3), aid=aids[0])
    first = state(learning_context)
    assert first['status'] == 'practiced' and first['counts']['attempts'] == 1
    attempt(learning_context, NOW - timedelta(days=2), aid=aids[1])
    attempt(learning_context, NOW - timedelta(days=1), aid=aids[2])
    stable = state(learning_context)
    assert stable['status'] == 'recently_stable'
    assert stable['counts']['correct_questions_30d'] == 3
    assert stable['counts']['correct_days_30d'] == 3
    assert stable['rule_version'] == 'course-training-v1'
    assert 'mastery_rate' not in stable


def test_recent_wrong_and_due_override_stable(learning_context):
    aids = three_questions(learning_context)
    for i, aid in enumerate(aids):
        attempt(learning_context, NOW - timedelta(days=i + 1), aid=aid)
    aid = aids[0]
    wrong_id = attempt(learning_context, NOW - timedelta(days=7), False, aid)
    with learning_context[0]._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='2099-01-01T00:00:00+00:00'")
    result = state(learning_context)
    assert result['status'] == 'needs_reinforcement' and result['counts']['wrong_attempts_7d'] == 1
    assert wrong_id in result['reasons']['recent_wrong_attempt_ids']
    with learning_context[0]._conn() as conn:
        conn.execute('UPDATE quiz_attempts SET created_at=? WHERE attempt_id=?',
                     ((NOW - timedelta(days=8)).isoformat(), wrong_id))
        conn.execute('UPDATE wrong_questions SET next_review_at=?', (NOW.isoformat(),))
    result = state(learning_context)
    assert result['status'] == 'needs_reinforcement' and len(result['reasons']['due_wrong_ids']) == 1
    with learning_context[0]._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='bad-date'")
    assert state(learning_context)['status'] == 'recently_stable'


def test_future_invalid_and_revised_attempts_excluded(learning_context):
    store, _, _, _, aid, question = learning_context
    confirm(learning_context)
    attempt(learning_context, NOW + timedelta(seconds=1))
    attempt(learning_context, 'not-a-date')
    old = attempt(learning_context, NOW - timedelta(days=2))
    result = state(learning_context)
    assert result['counts']['attempts'] == 1 and result['excluded_count'] == 2
    store.update_artifact(aid, title='修改题目', content=[{**question, 'answer': '后入先出'}])
    store.update_artifact(aid, title='恢复原文字', content=[question])
    confirm(learning_context, key='learning_relink_0001')
    result = state(learning_context)
    assert result['counts']['attempts'] == 0
    assert old not in [a['attempt_id'] for a in result['attempts']['items']]
    assert result['excluded_count'] == 3


def test_shanghai_midnight_is_distinct_day(learning_context):
    aids = three_questions(learning_context)
    for aid, when in zip(aids, [NOW.replace(hour=15) - timedelta(days=1),
                              NOW.replace(hour=16) - timedelta(days=1), NOW - timedelta(hours=1)]):
        attempt(learning_context, when, aid=aid)
    result = state(learning_context)
    assert result['counts']['correct_days_30d'] == 2 and result['status'] == 'recently_stable'


def test_merged_members_deduplicate_attempt_and_undo_split(pair):
    context, ids = pair
    store, _, cid, sid = context
    aid = store.save_artifact(artifact_type='questions', source_id=sid,
        content=[{'question_type': 'fill', 'stem': '栈____', 'answer': '后进先出'}])
    contexts = [(store, cid, sid, nid, aid, {}) for nid in ids]
    for i, item in enumerate(contexts):
        confirm(item, key=f'merged_link_test_{i:02}')
    identifier = attempt(contexts[0], NOW - timedelta(days=1))
    receipt = merge(pair)
    result = state(contexts[0])
    assert result['counts']['attempts'] == 1
    assert [a['attempt_id'] for a in result['attempts']['items']] == [identifier]
    change(context, receipt['operation_id'], 'undo', 'undo_learning_merge_01')
    assert all(state(item)['counts']['attempts'] == 1 for item in contexts)


def test_removed_source_retains_history_but_not_active_support(learning_context):
    store, cid, sid, *_ = learning_context
    confirm(learning_context)
    identifier = attempt(learning_context, NOW - timedelta(days=1))
    with store._conn() as conn:
        conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, sid))
    result = state(learning_context)
    assert result['active_support'] is False and result['counts']['attempts'] == 1
    assert result['attempts']['items'][0]['attempt_id'] == identifier
    assert result['question_refs']['items'][0]['source_available'] is False


def test_plan_completion_never_creates_correct_attempt(learning_context):
    store, cid, sid, nid, *_ = learning_context
    plan = {'title': '合成计划', 'daily_minutes': 20, 'daily_plan': [{'tasks': ['读栈']}]}
    aid = store.save_artifact(artifact_type='study_plan', source_id=sid, content=plan)
    saved = store.create_study_plan(artifact_id=aid, source_id=sid, plan=plan)
    with store._conn() as conn:
        conn.execute('INSERT INTO kg_course_plan_links VALUES(?,?,?,0)', (saved['plan_id'], cid, nid))
        conn.execute("UPDATE study_plans SET completed_days='[0]',status='completed'")
    result = state(learning_context)
    assert result['counts']['attempts'] == 0 and result['status'] == 'no_evidence'
    assert result['plans']['items'][0]['completed'] is True


def test_query_count_does_not_grow_per_concept(learning_context, monkeypatch):
    store, cid, *_ = learning_context
    confirm(learning_context)
    original, statements = store.read_snapshot, []

    @contextmanager
    def traced():
        with original() as read:
            read._conn().set_trace_callback(statements.append)
            yield read

    monkeypatch.setattr(store, 'read_snapshot', traced)
    counts = []
    for size in (100, 1000):
        with store._conn() as conn:
            conn.executemany('INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)',
                [(uuid4().hex, cid, f'合成规模{i}') for i in range(size)])
        statements.clear()
        result = module().learning_snapshot(store, cid, now=NOW)
        counts.append(len(statements))
        assert len(result['nodes']) >= size
    assert counts[0] == counts[1] and counts[0] < 30


def test_paginated_records_and_strict_status(learning_context):
    confirm(learning_context)
    for i in range(4):
        attempt(learning_context, NOW - timedelta(minutes=i))
    store, cid, _, nid, *_ = learning_context
    result = module().node_learning_evidence(store, cid, nid, now=NOW, offset=2, limit=2)
    assert result['attempts']['total'] == 4 and len(result['attempts']['items']) == 2
    assert 'user_answer' not in result['attempts']['items'][0]
    with pytest.raises(ValueError):
        module().list_learning_nodes(store, cid, now=NOW, status='mastered')
