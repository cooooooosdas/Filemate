# ruff: noqa: F811
"""Real tenant HTTP and explicit cross-course navigation contracts using synthetic data."""

import importlib
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.repository import CourseGraphRepository
from filemate.llm_client import LLMClient
from filemate.llm_client.request_credentials import REQUEST_API_KEY, is_model_request
from filemate.tests.course_graph.test_api import ROOT, api_server, graph_server, setup  # noqa: F401
from filemate.tests.course_graph.test_learning_evidence import NOW
from filemate.tests.course_graph.test_learning_links import learning_context  # noqa: F401


def data(response):
    assert response.status_code == 200, response.text
    return response.json()['data']


def confirmation(preview):
    return {'confirmed': True, 'confirmation_token': preview['confirmation_token'], 'request_key': uuid4().hex}


def published(client):
    cid, sid, did, route = setup(client)
    draft = data(client.post(route, json={'mode': 'local', 'request_key': uuid4().hex}))
    decisions = [{'item_id': item['item_id'], 'verdict': 'accept', 'semantic_checked': True}
                 for source in draft['sources'] for item in source['payload']['nodes'] + source['payload']['edges']
                 if item['validation'] != 'invalid']
    path = f'{ROOT}/{cid}/drafts/{did}'
    data(client.post(path + '/decisions', json={'expected_digest': draft['revision_digest'], 'decisions': decisions}))
    preview = data(client.post(path + '/review-preview'))
    data(client.post(path + '/confirm', json=confirmation(preview)))
    nid = data(client.get(f'{ROOT}/{cid}/concepts-page'))['items'][0]['id']
    return cid, sid, nid


def tenant(api_server, sid):
    return next(store for store in api_server._tenant_storages.values() if store.get_source(sid))


def test_learning_routes_tenant_flags_validation_and_redacted_storage_failure(api_server, monkeypatch):
    with TestClient(api_server.app) as alice, TestClient(api_server.app) as bob:
        cid, _, nid = published(alice)
        routes = [f'{ROOT}/{cid}/learning/nodes', f'{ROOT}/{cid}/concepts/{nid}/learning',
                  f'{ROOT}/{cid}/concepts/{nid}/question-candidates', f'{ROOT}/{cid}/concepts/{nid}/related-courses']
        for path in routes:
            response = alice.get(path)
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            assert bob.get(path).status_code == 404
            assert alice.get(path + '?unexpected=x').status_code == 422
            assert alice.get(path + '?limit=1&limit=2').status_code == 422
        monkeypatch.setenv('FILEMATE_ENABLE_COURSE_GRAPH', '0')
        assert all(alice.get(path).status_code == 503 for path in routes)
        assert alice.get('/api/knowledge-graph').status_code == 200
        monkeypatch.setenv('FILEMATE_ENABLE_COURSE_GRAPH', '1')
        module = importlib.import_module('filemate.course_graph.learning_evidence')

        def fail(*args, **kwargs):
            raise sqlite3.OperationalError('private-db-path-and-secret')

        monkeypatch.setattr(module, 'list_learning_nodes', fail)
        response = alice.get(routes[0])
        assert response.status_code == 503 and 'private-db-path-and-secret' not in response.text


def test_real_http_practice_review_quiz_and_plan_chain(api_server):
    with TestClient(api_server.app) as client:
        cid, sid, nid = published(client)
        base = f'{ROOT}/{cid}'
        work = data(client.post(base + f'/concepts/{nid}/practice-drafts', json={
            'difficulty': 'simple', 'count': 1, 'mode': 'local', 'request_key': uuid4().hex}))
        assert work['status'] == 'ready'
        review = base + f"/learning/work/{work['work_id']}/review"
        body = {'decisions': [{'index': 0, 'verdict': 'accept'}]}
        preview = data(client.post(review + '/preview', json=body))
        receipt = data(client.post(review + '/confirm', json=body | confirmation(preview)))
        store = tenant(api_server, sid)
        question = store.get_artifact(receipt['artifact_id'])['content'][0]
        data(client.post('/quiz/attempts', json={'artifact_id': receipt['artifact_id'], 'question_index': 0,
                                               'user_answer': '合成错误回答', 'expected_question': question}))
        evidence = data(client.get(base + f'/concepts/{nid}/learning'))
        assert evidence['status'] == 'needs_reinforcement' and evidence['counts']['attempts'] == 1
        options = {'goal': '复习当前概念', 'concept_ids': [nid], 'daily_minutes': 20, 'days': 2}
        preview = data(client.post(base + '/learning/path/preview', json=options))
        plan = data(client.post(base + '/learning/path/confirm', json=options | confirmation(preview)))
        assert data(client.get('/study-plans/' + plan['plan_id']))['plan_id'] == plan['plan_id']
        assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_no_read_triggers_model_or_mutation(api_server, monkeypatch):
    with TestClient(api_server.app) as client:
        cid, sid, nid = published(client)
        base = f'{ROOT}/{cid}'
        work = data(client.post(base + f'/concepts/{nid}/practice-drafts', json={
            'difficulty': 'simple', 'count': 1, 'mode': 'local', 'request_key': uuid4().hex}))
        store = tenant(api_server, sid)

        def snapshot():
            return {t: [tuple(r) for r in store._conn().execute(f'SELECT * FROM {t} ORDER BY rowid')]
                    for t in ('kg_question_links', 'kg_learning_work', 'kg_changes', 'study_plans', 'data_action_previews')}

        before = snapshot()
        def fail(*args, **kwargs):
            pytest.fail('A read must never call a model')
        monkeypatch.setattr(LLMClient, 'call_structured', fail)
        for route in ('/learning/nodes', f'/concepts/{nid}/learning', f'/concepts/{nid}/question-candidates',
                      f'/learning/work/{work["work_id"]}', f'/concepts/{nid}/related-courses'):
            data(client.get(base + route))
        assert snapshot() == before


def test_browser_credentials_only_exact_model_post_and_consent(api_server, monkeypatch):
    calls = []
    def generated(self, **kwargs):
        calls.append(REQUEST_API_KEY.get())
        context = json.loads(kwargs['messages'][0]['content'])
        quote = context['quotes'][0]
        return {'questions': [{'question_type': 'fill', 'stem': '请填入概念：____', 'answer': context['label'],
                               'citation_ids': [quote['evidence_id']]}]}
    monkeypatch.setattr(LLMClient, 'call_structured', generated)
    with TestClient(api_server.app) as client:
        cid, _, nid = published(client)
        route = f'{ROOT}/{cid}/concepts/{nid}/practice-drafts'
        headers = {'Origin': api_server.CORS_ORIGINS[0], 'X-FileMate-Action': 'model',
                   'X-FileMate-LLM-Key': 'sk-synthetic-only'}
        body = {'difficulty': 'simple', 'count': 1, 'mode': 'llm', 'request_key': uuid4().hex}
        assert client.post(route, headers=headers, json=body).status_code == 422
        result = data(client.post(route, headers=headers, json=body | {'allow_external_model': True}))
        assert result['status'] == 'ready' and calls == ['sk-synthetic-only']
        assert REQUEST_API_KEY.get() == ''
        for method, path in [('GET', route), ('POST', route + '/oops'),
                             ('POST', f'{ROOT}/{cid}/learning/path/confirm')]:
            assert not is_model_request(method, path)
            assert client.request(method, path, headers=headers).status_code == 403
        assert client.post(route, headers=headers, json=body | {'mode': 'local'}).status_code == 403


def cross_context(context):
    store, cid, sid, nid, *_ = context
    repo = CourseGraphRepository(store)
    other = repo.create_course('第二门课程', uuid4().hex)['course_id']
    repo.attach_sources(other, [sid], None, 0)
    with store._conn() as conn:
        conn.execute("INSERT INTO kg_concepts(concept_id,course_id,label) VALUES('other-concept',?,'另一课概念')", (other,))
    return store, cid, nid, other, 'other-concept'


def test_cross_link_navigation_only_cannot_change_evidence_or_plan(learning_context):
    from filemate.course_graph.learning_evidence import learning_snapshot
    cross = importlib.import_module('filemate.course_graph.cross_links')
    store, cid, nid, other, other_node = cross_context(learning_context)
    before = learning_snapshot(store, cid, now=NOW)
    preview = cross.preview_cross_link(store, cid, nid, other, other_node)
    receipt = cross.confirm_cross_link(store, cid, nid, other, other_node, True, 'related',
                                      preview['confirmation_token'], uuid4().hex, True)
    assert learning_snapshot(store, cid, now=NOW) == before
    assert store.list_study_plans() == []
    items = cross.list_cross_links(store, cid, nid)['items']
    assert items[0]['link_id'] == receipt['link_id'] and items[0]['affects_learning'] is False
    assert 'course=' + other in items[0]['route']
    assert cross.list_cross_links(store, other, other_node)['total'] == 1
    with pytest.raises(CourseGraphError):
        cross.preview_cross_link(store, cid, nid, other, other_node, relation='prerequisite')


def test_reversed_pair_idempotent_and_revoke_undo(learning_context):
    cross = importlib.import_module('filemate.course_graph.cross_links')
    store, cid, nid, other, other_node = cross_context(learning_context)
    receipts = []
    for c, n, target, tn in [(cid, nid, other, other_node), (other, other_node, cid, nid)]:
        preview = cross.preview_cross_link(store, c, n, target, tn)
        receipts.append(cross.confirm_cross_link(store, c, n, target, tn, True, 'related',
            preview['confirmation_token'], uuid4().hex, True))
    assert receipts[0]['link_id'] == receipts[1]['link_id']
    assert store._conn().execute('SELECT COUNT(*) FROM kg_cross_links').fetchone()[0] == 1
    preview = cross.preview_cross_link(store, cid, nid, other, other_node, active=False)
    revoked = cross.confirm_cross_link(store, cid, nid, other, other_node, False, 'related',
                                       preview['confirmation_token'], uuid4().hex, True)
    assert cross.list_cross_links(store, cid, nid)['total'] == 0
    from filemate.course_graph.learning_commands import (
        preview_learning_transition,
        transition_learning_operation,
    )
    token = preview_learning_transition(store, cid, revoked['operation_id'], 'undo')['confirmation_token']
    transition_learning_operation(store, cid, revoked['operation_id'], 'undo', token, uuid4().hex, True)
    assert cross.list_cross_links(store, cid, nid)['total'] == 1


def test_cross_link_endpoints_belong_to_current_tenant(api_server):
    with TestClient(api_server.app) as alice, TestClient(api_server.app) as bob:
        cid, _, nid = published(alice)
        other, _, target = published(bob)
        route = f'{ROOT}/{cid}/concepts/{nid}/related-courses/preview'
        assert alice.post(route, json={'other_course_id': other, 'other_concept_id': target}).status_code == 404
        assert bob.post(route, json={'other_course_id': other, 'other_concept_id': target}).status_code == 404


def test_failed_confirm_does_not_partial_write(api_server):
    with TestClient(api_server.app) as client:
        cid, sid, nid = published(client)
        store = tenant(api_server, sid)
        base = f'{ROOT}/{cid}/learning/path'
        body = {'goal': '合成目标', 'concept_ids': [nid], 'days': 1, 'daily_minutes': 20}
        preview = data(client.post(base + '/preview', json=body))
        before = store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
        with store._conn() as conn:
            conn.execute("""CREATE TRIGGER synthetic_failure BEFORE INSERT ON study_plans
                BEGIN SELECT RAISE(ABORT,'secret-database-path'); END""")
        response = client.post(base + '/confirm', json=body | confirmation(preview))
        assert response.status_code == 503 and 'secret-database-path' not in response.text
        assert store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == before
        assert store._conn().execute('SELECT COUNT(*) FROM study_plans').fetchone()[0] == 0
