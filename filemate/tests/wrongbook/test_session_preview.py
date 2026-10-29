# ruff: noqa: F811
"""Budget previews and readiness checks cannot create learning evidence."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.tests.wrongbook.test_insights import seed_due
from filemate.wrongbook.queries import ReviewFilter


def sessions(store, clock=None):
    return importlib.import_module('filemate.wrongbook.session_preview').ReviewSessions(store, clock=clock)


def service(fixture, count=65):
    store, _read = seed_due(fixture, count)
    return sessions(store, clock=lambda: fixture[-1][0])


@pytest.mark.parametrize('available,per', [(True, 4), (9.5, 4), (-1, 4), (1441, 4),
                                         (9, True), (9, 0), (9, 61), (9, 4.5)])
def test_budget_requires_real_bounded_integers(review_store, available, per):
    subject = service(review_store, 1)
    with pytest.raises(ValueError):
        subject.preview(ReviewFilter(), available_minutes=available, minutes_per_question=per)


@pytest.mark.parametrize('budget,selected,estimated', [(0, 0, 0), (3, 0, 0), (9, 2, 8), (1440, 20, 80)])
def test_preview_is_bounded_full_scope_and_read_only(review_store, budget, selected, estimated):
    subject = service(review_store)
    store = review_store[0]
    before = tuple(store._conn().iterdump())
    result = subject.preview(ReviewFilter(sort='recommended'), available_minutes=budget)
    assert result['status'] == 'preview_only'
    assert result['eligible_count'] == 65 and result['deferred_count'] == 65 - selected
    assert (result['selected_count'], result['estimated_minutes']) == (selected, estimated)
    assert result['available_minutes'] == budget and len(result['items']) == selected
    assert result['scope'] == 'filtered_eligible_due' and result['day_zone'] == 'Asia/Shanghai'
    for item in result['items']:
        assert {'wrong_id', 'artifact_id', 'source_id', 'question_index', 'question_digest', 'revision', 'next_review_at'} == set(item['ref'])
        assert not {'answer', 'analysis', 'question', 'latest_answer'} & item.keys()
    if selected:
        refs = [item['ref'] for item in result['items']]
        for _ in range(2):
            checked = subject.check(refs, filters=ReviewFilter.model_validate(result['filters']))
            assert checked['status'] == 'ready' and checked['refs'] == refs
    assert tuple(store._conn().iterdump()) == before


def test_default_due_order_and_filters_remain_authoritative(review_store):
    subject = service(review_store)
    result = subject.preview(ReviewFilter(), available_minutes=12)
    assert result['filters']['sort'] == 'due'
    expected = [row['wrong_id'] for row in review_store[0]._conn().execute('SELECT wrong_id FROM wrong_questions ORDER BY wrong_id LIMIT 3')]
    assert [item['ref']['wrong_id'] for item in result['items']] == expected
    narrowed = subject.preview(ReviewFilter(q='知识点00064'), available_minutes=12)
    assert narrowed['eligible_count'] == 1 and narrowed['selected_count'] == 1
    refs = [item['ref'] for item in narrowed['items']]
    with pytest.raises(QuestionRevisionConflict):
        subject.check(refs, filters=ReviewFilter(q='不存在的筛选'))


@pytest.mark.parametrize('change', ['pause', 'revision', 'due', 'replace', 'delete', 'history', 'bad_metadata'])
def test_changed_preview_is_rejected_without_partial_start(review_store, change):
    subject = service(review_store, 3)
    store = review_store[0]
    result = subject.preview(ReviewFilter(), available_minutes=12)
    refs = [item['ref'] for item in result['items']]
    ref = refs[1]
    with store._conn() as conn:
        if change == 'pause':
            conn.execute("UPDATE wrong_questions SET schedule_status='paused' WHERE wrong_id=?", (ref['wrong_id'],))
        elif change == 'revision':
            conn.execute('UPDATE wrong_questions SET revision=revision+1 WHERE wrong_id=?', (ref['wrong_id'],))
        elif change == 'due':
            conn.execute("UPDATE wrong_questions SET next_review_at='2026-10-25T00:00:01Z' WHERE wrong_id=?", (ref['wrong_id'],))
        elif change == 'replace':
            conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps([{'question_type': 'fill', 'stem': '新版本', 'answer': '新答案'}] * 3), ref['artifact_id']))
        elif change == 'delete':
            conn.execute('DELETE FROM sources WHERE source_id=?', (ref['source_id'],))
        else:
            conn.execute('UPDATE artifacts SET metadata=? WHERE artifact_id=?', ('[]' if change == 'bad_metadata' else '{"read_only_snapshot":true}', ref['artifact_id']))
    before = tuple(store._conn().iterdump())
    with pytest.raises(QuestionRevisionConflict, match='预览'):
        subject.check(refs)
    assert tuple(store._conn().iterdump()) == before


def test_missing_foreign_and_duplicate_references_fail_closed(review_store, tmp_path):
    subject = service(review_store, 1)
    refs = [item['ref'] for item in subject.preview(ReviewFilter(), available_minutes=4)['items']]
    foreign = SQLiteStorage(tmp_path / 'other.db')
    foreign.init_schema()
    try:
        with pytest.raises(QuestionRevisionConflict):
            sessions(foreign, clock=lambda: review_store[-1][0]).check(refs)
        with pytest.raises(ValueError):
            subject.check(refs * 2)
        with pytest.raises(ValueError):
            subject.check([{**refs[0], 'revision': True}])
        with pytest.raises(ValueError):
            subject.check([])
        with pytest.raises(ValueError):
            subject.check(refs * 21)
    finally:
        foreign.close()


@pytest.mark.parametrize('params', [
    'available_minutes=9.5', 'available_minutes=true', 'available_minutes=-1',
    'available_minutes=1441', 'available_minutes=9&minutes_per_question=0',
    'available_minutes=9&now=2026-10-25', 'available_minutes=9&user_id=other',
    'available_minutes=9&available_minutes=8', 'available_minutes=9&limit=30',
])
def test_http_rejects_invalid_or_unknown_preview_arguments(server_module, monkeypatch, params):
    module, _store = server_module
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    with TestClient(module.app) as client:
        result = client.get('/wrongbook/v2/session-preview?' + params)
        assert result.status_code == 422


def test_http_flags_body_limits_origin_and_safe_database_failure(server_module, monkeypatch):
    module, store = server_module
    from filemate.tests.wrongbook.test_workspace_reads import many
    many(store, 1)
    with TestClient(module.app) as client:
        monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '0')
        assert client.get('/wrongbook/v2/session-preview?available_minutes=4').status_code == 503
        assert client.post('/wrongbook/v2/session-check', json={'refs': []}).status_code == 503
        assert client.get('/wrongbook/v2/page').status_code == 200
        monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
        preview = client.get('/wrongbook/v2/session-preview?available_minutes=4&sort=recommended')
        assert preview.status_code == 200, preview.text
        assert preview.headers['cache-control'] == 'no-store'
        refs = [item['ref'] for item in preview.json()['data']['items']]
        checked = client.post('/wrongbook/v2/session-check', json={'refs': refs})
        assert checked.status_code == 200 and checked.json()['data']['status'] == 'ready'
        assert checked.headers['cache-control'] == 'no-store'
        assert client.post('/wrongbook/v2/session-check', json={'refs': refs, 'user_id': 'secret-must-not-echo'}).status_code == 422
        assert client.post('/wrongbook/v2/session-check', headers={'Origin': 'https://evil.example'}, json={'refs': refs}).status_code == 403
        assert client.post('/wrongbook/v2/session-check', json={'refs': refs, 'pad': 'x' * 70_000}).status_code == 413
        import sqlite3
        def fail(*args, **kwargs):
            raise sqlite3.OperationalError('secret-database-location')
        monkeypatch.setattr(importlib.import_module('filemate.wrongbook.session_preview').ReviewSessions, 'preview', fail)
        unavailable = client.get('/wrongbook/v2/session-preview?available_minutes=4')
        assert unavailable.status_code == 503 and 'secret-database-location' not in unavailable.text
