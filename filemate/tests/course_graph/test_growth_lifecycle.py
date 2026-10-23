# ruff: noqa: F811
"""One synthetic student uses public HTTP from registration through backup recovery."""

from uuid import uuid4

from fastapi.testclient import TestClient

from filemate.tests.course_graph.test_api import ROOT, api_server, graph_server  # noqa: F401
from filemate.tests.course_graph.test_learning_api import confirmation, data, tenant
from filemate.tests.test_accounts import HEADERS, login, register


def publish_course(client, name, lessons):
    cid = data(client.post(ROOT, json={'name': name, 'request_key': uuid4().hex}))['course_id']
    sources = [data(client.post('/knowledge/import', files={
        'file': (f'合成原创-{i}.txt', text.encode('utf-8'), 'text/plain')}))['source_id'] for i, text in enumerate(lessons)]
    base = f'{ROOT}/{cid}'
    data(client.post(base + '/sources', json={'source_ids': sources, 'expected_revision': 0}))
    draft = data(client.post(base + '/drafts', json={'source_ids': sources, 'mode': 'local', 'request_key': uuid4().hex}))
    did = draft['draft_id']
    for sid in sources:
        draft = data(client.post(base + f'/drafts/{did}/sources/{sid}/extract', json={'mode': 'local', 'request_key': uuid4().hex}))
    choices = [{'item_id': item['item_id'], 'verdict': 'accept', 'semantic_checked': True}
               for source in draft['sources'] for item in source['payload']['nodes'] + source['payload']['edges']
               if item['validation'] != 'invalid']
    data(client.post(base + f'/drafts/{did}/decisions', json={'expected_digest': draft['revision_digest'], 'decisions': choices}))
    preview = data(client.post(base + f'/drafts/{did}/review-preview'))
    data(client.post(base + f'/drafts/{did}/confirm', json=confirmation(preview)))
    return cid, sources, data(client.get(base + '/concepts-page'))['items']


def test_registered_student_learning_assistant_and_recovery(api_server, monkeypatch):
    monkeypatch.setenv('FILEMATE_ENABLE_GRAPH_ASSISTANT', '1')
    with TestClient(api_server.app) as client, TestClient(api_server.app) as outsider:
        assert register(client).status_code == 200
        assert client.post('/api/auth/logout', headers=HEADERS, json={}).status_code == 200
        assert login(client).status_code == 200
        cid, sources, nodes = publish_course(client, '数据结构', [
            '树包含堆。堆：一种树形结构。堆应用于堆排序。',
            '堆：满足堆序性的树形结构。堆是堆排序的前置知识。'])
        other, _, _ = publish_course(client, 'Python基础', ['列表：有序可变的容器。元组：有序不可变的容器。'])
        base = f'{ROOT}/{cid}'
        assert outsider.get(base + '/learning/nodes').status_code == 404
        assert data(client.get(f'{ROOT}/{other}/learning/nodes'))['total'] > 0
        heaps = [node['id'] for node in nodes if node['label'] == '堆']
        assert len(heaps) == 2
        merge = {'concept_ids': heaps, 'target_id': heaps[0]}
        preview = data(client.post(base + '/merges/preview', json=merge))
        data(client.post(base + '/merges/confirm', json=merge | confirmation(preview)))
        nid = heaps[0]
        work = data(client.post(base + f'/concepts/{nid}/practice-drafts', json={
            'mode': 'local', 'count': 1, 'difficulty': 'simple', 'request_key': uuid4().hex}))
        assert work['status'] == 'ready'
        review = base + f"/learning/work/{work['work_id']}/review"
        decisions = {'decisions': [{'index': 0, 'verdict': 'accept'}]}
        preview = data(client.post(review + '/preview', json=decisions))
        receipt = data(client.post(review + '/confirm', json=decisions | confirmation(preview)))
        store = tenant(api_server, sources[0])
        question = store.get_artifact(receipt['artifact_id'])['content'][0]
        attempt = {'artifact_id': receipt['artifact_id'], 'question_index': 0, 'expected_question': question}
        assert data(client.post('/quiz/attempts', json=attempt | {'user_answer': '不会'}))['is_correct'] is False
        assert data(client.get('/wrongbook/page'))['total'] == 1
        assert data(client.post('/quiz/attempts', json=attempt | {'user_answer': question['answer']}))['is_correct'] is True
        evidence = data(client.get(base + f'/concepts/{nid}/learning'))
        assert evidence['counts']['attempts'] == 2 and evidence['status'] == 'needs_reinforcement'
        options = {'goal': '为课程考试复习堆', 'concept_ids': [nid], 'daily_minutes': 20, 'days': 3}
        preview = data(client.post(base + '/learning/path/preview', json=options))
        command = options | confirmation(preview)
        plan = data(client.post(base + '/learning/path/confirm', json=command))
        assert data(client.post(base + '/learning/path/confirm', json=command)) == plan
        for action in ('undo', 'restore'):
            route = base + f"/learning/operations/{plan['operation_id']}"
            p = data(client.post(route + '/preview', json={'action': action}))
            data(client.post(route + '/confirm', json={'action': action} | confirmation(p)))
        assert any(item['plan_id'] == plan['plan_id'] for item in data(client.get('/review/today'))['items'])
        data(client.patch(f"/study-plans/{plan['plan_id']}/days/0", json={'completed': True}))
        assert data(client.get(base + f'/concepts/{nid}/learning'))['counts']['attempts'] == 2
        answer = data(client.post(base + '/assistant/answer', json={
            'question': '如何复习堆？', 'concept_ids': [nid], 'mode': 'rule', 'request_key': uuid4().hex}))
        assert answer['status'] == 'ready' and answer['payload']['textbook_evidence']
        before = len(store.list_study_plans())
        agent = data(client.post(base + '/assistant/plan/preview', json=options))
        assert len(agent['tool_steps']) == 4 and len(agent['tasks']) <= 7
        assert len(store.list_study_plans()) == before
        raw = client.get('/api/privacy/export').content
        preview = data(client.get(f'/knowledge/sources/{sources[1]}/delete-preview'))
        data(client.request('DELETE', f'/knowledge/sources/{sources[1]}', json={
            'confirmed': True, 'confirmation_token': preview['confirmation_token']}))
        assert store.get_source(sources[1]) is None
        p = data(client.post('/api/privacy/restore-preview', files={'file': ('own.zip', raw, 'application/zip')}))
        assert data(client.post('/api/privacy/restore', json={
            'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}))['restored']
        assert store.get_source(sources[1]) is not None
        assert client.post(base + '/learning/path/confirm', json=options | confirmation(agent)).status_code == 409
        assert data(client.get(base + f"/learning/work/{answer['work_id']}"))['status'] == 'ready'
        assert store.get_schema_version() == 34
        assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_uncertain_quiz_retry_records_one_attempt(api_server):
    from filemate.tests.course_graph.test_learning_api import published
    with TestClient(api_server.app) as client:
        cid, sid, nid = published(client)
        base = f'{ROOT}/{cid}'
        work = data(client.post(base + f'/concepts/{nid}/practice-drafts', json={
            'mode': 'local', 'count': 1, 'difficulty': 'simple', 'request_key': uuid4().hex}))
        review = base + f"/learning/work/{work['work_id']}/review"
        decisions = {'decisions': [{'index': 0, 'verdict': 'accept'}]}
        p = data(client.post(review + '/preview', json=decisions))
        receipt = data(client.post(review + '/confirm', json=decisions | confirmation(p)))
        store = tenant(api_server, sid)
        question = store.get_artifact(receipt['artifact_id'])['content'][0]
        body = {'artifact_id': receipt['artifact_id'], 'question_index': 0, 'user_answer': '不会',
                'expected_question': question, 'request_key': uuid4().hex}
        first = data(client.post('/quiz/attempts', json=body))
        assert data(client.post('/quiz/attempts', json=body)) == first
        assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1
        assert client.post('/quiz/attempts', json=body | {'user_answer': question['answer']}).status_code == 409
        assert data(client.post('/quiz/attempts', json=body | {'request_key': uuid4().hex}))['attempt_id'] != first['attempt_id']
