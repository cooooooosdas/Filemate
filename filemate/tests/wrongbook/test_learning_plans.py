"""Incremental plans use real bounded evidence and never rewrite existing goals."""
# ruff: noqa: F811

import copy
from datetime import timedelta

import pytest

from filemate.execution.storage import QuestionRevisionConflict
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.tests.wrongbook.conftest import answer_payload, review_store  # noqa: F401
from filemate.tests.wrongbook.test_analysis_adoption import commands, supported
from filemate.tests.wrongbook.test_analysis_repository import analysis_case  # noqa: F401
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.repository import ReviewRepository


def selection(api, fixture, goal_id=None):
    result = api.suggestions(fixture['ref']['wrong_id'], goal_id)
    first = result['items'][0]
    return {'expected_revision': fixture['review_state']['revision'], 'attempt_id': fixture['attempt']['attempt_id'],
        'goal_id': goal_id, 'start_date': result['start_date'], 'tasks': [{k: first[k] for k in
            ('action_id', 'title', 'instructions', 'duration_minutes', 'day_offset')}]}


def test_one_error_only_proposes_small_action_and_never_rewrites_goal(review_store):
    store, _, _, _, clock = review_store
    answer = ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store))
    api = commands(store, clock)
    assert hasattr(api, 'suggestions'), '缺少真实证据驱动的增量建议'
    items = api.suggestions(answer['wrong_id'])['items']
    assert len(items) == 1 and items[0]['duration_minutes'] <= 15
    basis = items[0]['basis']
    assert basis['wrong_id'] == answer['wrong_id'] and basis['trusted_total'] == 1
    assert basis['attempt_ids'] == [answer['attempt_id']] and basis['window_days'] == 30
    assert basis['rule_version']
    ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store, key='synthetic-repeat-wrong-0001'))
    repeated = api.suggestions(answer['wrong_id'])['items']
    assert 1 < len(repeated) <= 7
    assert repeated[0]['basis']['trusted_incorrect'] == 2
    assert store._conn().execute('SELECT COUNT(*) FROM study_plans').fetchone()[0] == 0


def test_preview_edits_confirm_and_replay_add_exactly_one_plan(analysis_case):
    store, clock, context = analysis_case
    sid = store._conn().execute('SELECT source_id FROM wrong_questions').fetchone()[0]
    goal = store.save_artifact(artifact_type='reverse_goal_plan', source_id=sid,
        content={'title': '原目标', 'tasks': [{'title': '原任务', 'status': 'completed'}]})
    old_content = {'title': '原计划', 'daily_minutes': 20, 'exam_date': '2026-12-01', 'daily_plan': []}
    old_aid = store.save_artifact(artifact_type='study_plan', source_id=sid, content=old_content)
    old_pid = store.create_study_plan(artifact_id=old_aid, source_id=sid, plan=old_content)['plan_id']
    with store._conn() as conn:
        conn.execute("UPDATE study_plans SET completed_days='[0]' WHERE plan_id=?", (old_pid,))
    before_goal, before_plan = store.get_artifact(goal), store.get_study_plan(old_pid)
    api, wid = commands(store, clock), context['ref']['wrong_id']
    assert hasattr(api, 'preview_plan'), '缺少可编辑增量计划预览'
    body = selection(api, context, goal)
    preview = api.preview_plan(wid, body)
    assert len(store.list_study_plans()) == 1
    edited = copy.deepcopy(body)
    edited['tasks'][0]['title'] = '用户编辑的明确行动'
    with pytest.raises(QuestionRevisionConflict):
        api.confirm_plan(wid, edited, preview['confirmation_token'], 'synthetic-edited-token-0001', True)
    preview = api.preview_plan(wid, edited)
    receipt = api.confirm_plan(wid, edited, preview['confirmation_token'], 'synthetic-plan-confirm-0001', True)
    assert api.confirm_plan(wid, edited, preview['confirmation_token'], 'synthetic-plan-confirm-0002', True) == receipt
    assert len(store.list_study_plans()) == 2
    new_plan = store.get_study_plan(receipt['plan_id'])
    assert new_plan['plan_data']['daily_plan'][0]['focus'] == '用户编辑的明确行动'
    assert new_plan['completed_days'] == []
    assert store.get_artifact(goal) == before_goal and store.get_study_plan(old_pid) == before_plan
    assert store._conn().execute("SELECT COUNT(*) FROM review_events WHERE action='learning_plan_confirm'").fetchone()[0] == 1


@pytest.mark.parametrize('change', ['completed', 'edited', None])
def test_undo_only_removes_created_unmodified_uncompleted_plan(analysis_case, change):
    store, clock, context = analysis_case
    api, wid = commands(store, clock), context['ref']['wrong_id']
    assert hasattr(api, 'preview_plan'), '缺少增量计划撤销'
    body = selection(api, context)
    preview = api.preview_plan(wid, body)
    receipt = api.confirm_plan(wid, body, preview['confirmation_token'], 'synthetic-plan-to-undo-0001', True)
    undo = api.preview_undo(wid, receipt['review_event_id'])
    if change:
        with store._conn() as conn:
            if change == 'completed':
                conn.execute("UPDATE study_plans SET completed_days='[0]' WHERE plan_id=?", (receipt['plan_id'],))
            else:
                conn.execute("UPDATE study_plans SET title='用户已编辑' WHERE plan_id=?", (receipt['plan_id'],))
        with pytest.raises(QuestionRevisionConflict):
            api.confirm_undo(wid, receipt['review_event_id'], undo['confirmation_token'], 'synthetic-plan-undo-0001', True)
        assert store.get_study_plan(receipt['plan_id']) is not None
    else:
        result = api.confirm_undo(wid, receipt['review_event_id'], undo['confirmation_token'], 'synthetic-plan-undo-0001', True)
        assert api.confirm_undo(wid, receipt['review_event_id'], undo['confirmation_token'], 'synthetic-plan-undo-0001', True) == result
        assert store.get_study_plan(receipt['plan_id']) is None
    assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['goal', 'source', 'attempt'])
def test_stale_goal_source_or_attempt_invalidates_preview(analysis_case, review_store, change):
    store, clock, context = analysis_case
    sid = review_store[1]
    goal = store.save_artifact(artifact_type='reverse_goal_plan', source_id=sid, content={'title': '目标'})
    api, wid = commands(store, clock), context['ref']['wrong_id']
    assert hasattr(api, 'preview_plan'), '缺少全证据绑定预览'
    body = selection(api, context, goal)
    preview = api.preview_plan(wid, body)
    if change == 'goal':
        store.update_artifact(goal, title='用户更新', content={'title': '用户更新'})
    elif change == 'source':
        with store._conn() as conn:
            conn.execute("UPDATE sources SET raw_text='更新后的原文' WHERE source_id=?", (sid,))
    else:
        ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store, key='synthetic-new-plan-answer-0001'))
    with pytest.raises(QuestionRevisionConflict):
        api.confirm_plan(wid, body, preview['confirmation_token'], 'synthetic-stale-plan-0001', True)
    assert not store.list_study_plans()


def test_adoption_undo_restores_only_diagnosis(analysis_case):
    store, clock, context = analysis_case
    aid, revision = supported(analysis_case)
    api, wid = commands(store, clock), context['ref']['wrong_id']
    body = {'selected_causes': ['concept_gap'], 'expected_revision': revision}
    preview = api.preview_adoption(wid, aid, body)
    receipt = api.confirm_adoption(wid, aid, body, preview['confirmation_token'], 'synthetic-adoption-undo-0001', True)
    assert hasattr(api, 'preview_undo'), '错因采纳缺少独立撤销预览'
    undo = api.preview_undo(wid, receipt['review_event_id'])
    api.confirm_undo(wid, receipt['review_event_id'], undo['confirmation_token'], 'synthetic-adoption-undo-0002', True)
    row = ReviewRepository(store).detail(wid)
    assert row['error_causes'] == ['memory_gap'] and row['error_cause_note'] == '保留人工备注'
    assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1


def test_current_attempt_after_question_edit_is_valid_context(review_store):
    store, _, aid, questions, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    repo.submit(answer_payload(review_store))
    new_questions = [{**questions[0], 'stem': '新版本的栈次序'}, *questions[1:]]
    store.update_artifact(aid, title='新版本', content=new_questions)
    clock[0] += timedelta(days=1)
    answer = repo.submit({**answer_payload(review_store, key='synthetic-edited-question-0001'), 'expected_question': new_questions[0]})
    assert ReviewLearningContext(store, lambda: clock[0]).build(answer['wrong_id'], answer['attempt_id'])['attempt']['attempt_id'] == answer['attempt_id']


def test_pending_or_revealed_answers_are_not_trusted_denominators(review_store):
    store, _, _, _, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    pending = repo.submit(answer_payload(review_store, index=1, answer='合成主观回答'))
    api = commands(store, clock)
    assert len(api.suggestions(pending['wrong_id'])['items']) == 1
    basis = api.suggestions(pending['wrong_id'])['items'][0]['basis']
    assert basis['trusted_total'] == 0 and basis['pending_total'] == 1
    wrong = repo.submit(answer_payload(review_store, key='synthetic-independent-first-0001'))
    repo.submit(answer_payload(review_store, key='synthetic-assisted-answer-0001', answer_revealed=True))
    basis = api.suggestions(wrong['wrong_id'])['items'][0]['basis']
    assert basis['trusted_total'] == 1 and basis['trusted_incorrect'] == 1
    clock[0] += timedelta(days=2)
    assert len(api.suggestions(wrong['wrong_id'])['items']) > 1


def test_plan_http_preview_confirm_and_undo_work_without_ai(server_module, monkeypatch):
    from fastapi.testclient import TestClient

    from filemate.tests.wrongbook.test_api import seed

    module, store = server_module
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '0')
    answer = ReviewRepository(store).submit(seed(store))
    path = '/wrongbook/v2/'+answer['wrong_id']
    with TestClient(module.app) as client:
        context = client.get(path+'/learning-context?attempt_id='+answer['attempt_id']).json()['data']
        from datetime import datetime

        from filemate.wrongbook.engine import LOCAL_ZONE
        body = {'expected_revision': context['review_state']['revision'], 'attempt_id': answer['attempt_id'],
            'start_date': datetime.now(LOCAL_ZONE).date().isoformat(), 'tasks': [{k: context['next_actions'][0][k]
                for k in ('action_id', 'title', 'instructions', 'duration_minutes', 'day_offset')}]}
        response = client.post(path+'/learning-plan-preview', json=body)
        assert response.status_code == 200, response.text
        preview = response.json()['data']
        response = client.post(path+'/learning-plan-confirm', json={**body,
            'confirmation_token': preview['confirmation_token'], 'request_key': 'synthetic-http-plan-0001', 'confirmed': True})
        assert response.status_code == 200, response.text
        receipt = response.json()['data']
        undo_path = path+'/learning-operations/'+receipt['review_event_id']
        response = client.post(undo_path+'/undo-preview', json={})
        assert response.status_code == 200, response.text
        result = client.post(undo_path+'/undo-confirm', json={'confirmation_token': response.json()['data']['confirmation_token'],
            'request_key': 'synthetic-http-plan-undo-0001', 'confirmed': True})
        assert result.status_code == 200, result.text
        assert store.get_study_plan(receipt['plan_id']) is None
