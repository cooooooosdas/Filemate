# ruff: noqa: F811
"""Synthetic prerequisite, evidence priority and additive plan contracts."""

import importlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from filemate.course_graph.models import CourseGraphError
from filemate.tests.course_graph.test_api import api_server, graph_server  # noqa: F401
from filemate.tests.course_graph.test_learning_evidence import NOW, attempt
from filemate.tests.course_graph.test_learning_links import confirm as link
from filemate.tests.course_graph.test_learning_links import learning_context  # noqa: F401


def paths():
    return importlib.import_module('filemate.course_graph.learning_paths')


def options(context, **changes):
    return {'goal': '复习数据结构核心概念', 'concept_ids': [context[3]], 'chapter_id': None,
            'goal_id': None, 'daily_minutes': 20, 'days': 3, **changes}


def suggest(context, **changes):
    return paths().suggest_path(context[0], context[1], **options(context, **changes), now=NOW)


def create(context, **changes):
    store, cid, *_ = context
    opts = options(context, **changes)
    preview = paths().preview_path(store, cid, opts, now=NOW)
    return paths().confirm_path(store, cid, opts, preview['confirmation_token'], uuid4().hex, True, now=NOW)


def test_dependency_direction_and_cycle_refusal(learning_context):
    store, cid, _, nid, *_ = learning_context
    dfs = store._conn().execute("SELECT concept_id FROM kg_concepts WHERE label='DFS'").fetchone()[0]
    result = suggest(learning_context, concept_ids=[dfs])
    assert [t['concept_id'] for t in result['tasks']] == [nid, dfs]
    assert result['tasks'][0]['reasons']['relation_ids']
    with store._conn() as conn:
        conn.execute("UPDATE kg_relations SET type='depends_on',from_id=?,to_id=?", (dfs, nid))
    assert [t['concept_id'] for t in suggest(learning_context, concept_ids=[dfs])['tasks']] == [nid, dfs]
    with store._conn() as conn:
        conn.execute("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES('cycle',?,?,?,'prerequisite')",
                     (cid, dfs, nid))
        conn.execute('''INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,relation_id,
            excerpt,char_start,char_end) SELECT 'cycle-ref',course_id,source_id,source_revision,'cycle',
            excerpt,char_start,char_end FROM kg_evidence WHERE relation_id IS NOT NULL LIMIT 1''')
    with pytest.raises(CourseGraphError, match='dependency_cycle'):
        suggest(learning_context, concept_ids=[dfs])


def test_due_wrong_goal_priority_has_record_ids(learning_context):
    store, _, _, nid, *_ = learning_context
    link(learning_context)
    aid = attempt(learning_context, NOW - timedelta(days=1), False)
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET next_review_at=?', (NOW.isoformat(),))
    task = suggest(learning_context, concept_ids=None)['tasks'][0]
    assert task['concept_id'] == nid and task['kind'] == 'review'
    assert task['reasons']['wrong_ids'] and aid in task['reasons']['attempt_ids']
    assert task['reason'] and task['duration_minutes'] <= 20


def test_budget_and_seven_task_ceiling(learning_context):
    store, cid, _, original, *_ = learning_context
    with store._conn() as conn:
        for i in range(10):
            nid = f'scale-{i}'
            conn.execute('INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)', (nid, cid, f'概念{i}'))
            conn.execute('''INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,concept_id,
                excerpt,char_start,char_end) SELECT ?,course_id,source_id,source_revision,?,excerpt,char_start,char_end
                FROM kg_evidence WHERE concept_id=? LIMIT 1''', (f'proof-{i}', nid, original))
    result = suggest(learning_context, concept_ids=None, days=7, daily_minutes=5)
    assert len(result['tasks']) == 7 and result['omitted_count'] > 0
    assert all(t['duration_minutes'] <= 5 for t in result['tasks'])
    assert {t['day_index'] for t in result['tasks']} == set(range(7))
    with pytest.raises(CourseGraphError):
        suggest(learning_context, days=8)


def test_inactive_support_not_prerequisite_or_recommendation(learning_context):
    store, cid, sid, *_ = learning_context
    with store._conn() as conn:
        conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, sid))
    with pytest.raises(CourseGraphError, match='path_no_supported_concepts'):
        suggest(learning_context, concept_ids=None)


def test_confirm_stale_evidence_refused(learning_context):
    store, cid, *_ = learning_context
    link(learning_context)
    opts = options(learning_context)
    token = paths().preview_path(store, cid, opts, now=NOW)['confirmation_token']
    attempt(learning_context, NOW - timedelta(minutes=1))
    with pytest.raises(CourseGraphError):
        paths().confirm_path(store, cid, opts, token, 'path_confirm_00001', True, now=NOW)
    assert store.list_study_plans() == []


def test_existing_manual_plan_unchanged_and_duplicate_single_new_plan(learning_context):
    store, cid, sid, *_ = learning_context
    manual = {'title': '我的手工计划', 'daily_minutes': 15, 'daily_plan': [{'tasks': ['自己安排']} ]}
    aid = store.save_artifact(artifact_type='study_plan', source_id=sid, content=manual)
    saved = store.create_study_plan(artifact_id=aid, source_id=sid, plan=manual)
    opts = options(learning_context)
    token = paths().preview_path(store, cid, opts, now=NOW)['confirmation_token']
    args = (store, cid, opts, token, 'path_confirm_00001', True)
    receipt = paths().confirm_path(*args, now=NOW)
    assert paths().confirm_path(*args, now=NOW) == receipt
    assert paths().confirm_path(store, cid, opts, token, 'path_confirm_00002', True, now=NOW) == receipt
    assert store.get_study_plan(saved['plan_id']) == saved
    assert len(store.list_study_plans()) == 2
    assert len(store.get_study_plan(receipt['plan_id'])['plan_data']['daily_plan']) <= 3
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_undo_restore_keeps_completed_days_and_detects_user_edit(learning_context):
    store, cid, *_ = learning_context
    receipt = create(learning_context)
    store.set_study_plan_day(receipt['plan_id'], 0, True)
    commands = importlib.import_module('filemate.course_graph.learning_commands')
    for action in ('undo', 'restore'):
        preview = commands.preview_learning_transition(store, cid, receipt['operation_id'], action)
        commands.transition_learning_operation(store, cid, receipt['operation_id'], action,
            preview['confirmation_token'], uuid4().hex, True)
        saved = store.get_study_plan(receipt['plan_id'])
        assert saved['completed_days'] == [0]
        assert saved['status'] == ('archived' if action == 'undo' else 'completed')
    artifact = store.get_artifact(receipt['artifact_id'])
    store.update_artifact(receipt['artifact_id'], title='用户改写', content=artifact['content'])
    with pytest.raises(CourseGraphError, match='operation_conflict'):
        commands.preview_learning_transition(store, cid, receipt['operation_id'], 'undo')


def test_goal_identity_and_version_are_bound(learning_context):
    store, cid, _, nid, *_ = learning_context
    other = store.save_source(original_name='不属于本课', source_path='other.txt', raw_text='另课')
    gid = store.save_artifact(artifact_type='reverse_goal_plan', source_id=other,
        content={'title': '另一门课目标', 'tasks': []})
    with pytest.raises(CourseGraphError, match='goal_not_in_course'):
        suggest(learning_context, goal_id=gid)
    gid = store.save_artifact(artifact_type='reverse_goal_plan', content={'title': '本周复习', 'tasks': []})
    opts = options(learning_context, goal_id=gid, concept_ids=[nid])
    token = paths().preview_path(store, cid, opts, now=NOW)['confirmation_token']
    store.update_artifact(gid, title='新目标', content={'title': '改了', 'tasks': []})
    with pytest.raises(CourseGraphError):
        paths().confirm_path(store, cid, opts, token, uuid4().hex, True, now=NOW)


def test_today_links_plan_and_completion_is_separate_evidence(learning_context, api_server, monkeypatch):
    store, cid, *_ = learning_context
    receipt = create(learning_context)
    monkeypatch.setattr(api_server, '_storage', store)
    with TestClient(api_server.app) as client:
        response = client.get('/review/today')
        assert response.status_code == 200, response.text
        items = response.json()['data']['items']
        task = next(t for t in items if t['plan_id'] == receipt['plan_id'])
        assert task['route'] == f"/study-plan?plan={receipt['plan_id']}"
        assert client.patch(f"/study-plans/{receipt['plan_id']}/days/0", json={'completed': True}).status_code == 200
    from filemate.course_graph.learning_evidence import node_learning_evidence
    evidence = node_learning_evidence(store, cid, learning_context[3], now=NOW)
    assert evidence['status'] == 'no_evidence' and evidence['counts']['attempts'] == 0
    assert evidence['counts']['completed_plan_days'] == 1
    stored = json.dumps(store.get_study_plan(receipt['plan_id']))
    assert 'mastery_rate' not in stored
