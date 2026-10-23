# ruff: noqa: F811
"""Original synthetic documents through registered accounts and real ASGI routes."""
import io
import json
import zipfile
from uuid import uuid4

from fastapi.testclient import TestClient

from filemate.tests.course_graph.test_api import ROOT, api_server, graph_server  # noqa: F401
from filemate.tests.test_accounts import HEADERS, login, register
from scripts.acceptance.course_graph_fixture import DOCUMENTS


def data(response):
    assert response.status_code == 200, response.text
    return response.json()['data']


def confirmation(preview):
    return {'confirmed': True, 'confirmation_token': preview['confirmation_token'], 'request_key': uuid4().hex}


def test_registered_account_workspace_backup_lifecycle(api_server, monkeypatch):
    with TestClient(api_server.app) as client, TestClient(api_server.app) as other:
        assert register(client).status_code == 200
        assert client.post('/api/auth/logout', headers=HEADERS, json={}).status_code == 200
        assert login(client).status_code == 200
        assert register(other, email='other@example.invalid').status_code == 200
        sources = [data(client.post('/knowledge/import', files={'file': (name, text.encode('utf-8'), 'text/plain')}))['source_id'] for name, text in DOCUMENTS.items()]
        courses = []
        for name, ids in [('数据结构', sources[:2]), ('Python', sources[2:])]:
            cid = data(client.post(ROOT, json={'name': name, 'request_key': uuid4().hex}))['course_id']; courses.append(cid)
            chapter = str(uuid4())
            data(client.put(f'{ROOT}/{cid}/chapters/{chapter}', json={'title': '基础概念', 'expected_revision': 0}))
            revision = data(client.get(f'{ROOT}/{cid}'))['revision']
            data(client.post(f'{ROOT}/{cid}/sources', json={'source_ids': ids, 'chapter_id': chapter, 'expected_revision': revision}))
            draft = data(client.post(f'{ROOT}/{cid}/drafts', json={'source_ids': ids, 'mode': 'local', 'request_key': uuid4().hex}))
            did = draft['draft_id']
            for sid in ids:
                draft = data(client.post(f'{ROOT}/{cid}/drafts/{did}/sources/{sid}/extract', json={'mode': 'local', 'request_key': uuid4().hex}))
            choices = [{'item_id': item['item_id'], 'verdict': 'accept', 'semantic_checked': True} for source in draft['sources'] for item in source['payload']['nodes']+source['payload']['edges'] if item['validation'] != 'invalid']
            data(client.post(f'{ROOT}/{cid}/drafts/{did}/decisions', json={'expected_digest': draft['revision_digest'], 'decisions': choices}))
            preview = data(client.post(f'{ROOT}/{cid}/drafts/{did}/review-preview'))
            data(client.post(f'{ROOT}/{cid}/drafts/{did}/confirm', json=confirmation(preview)))
            assert other.get(f'{ROOT}/{cid}/workspace').status_code == 404
        cid = courses[0]; path = f'{ROOT}/{cid}'
        nodes = data(client.get(path+'/concepts-page'))['items']
        ids = [n['id'] for n in nodes if n['label'] == '栈']
        assert len(ids) == 2
        body = {'concept_ids': ids, 'target_id': ids[0]}
        preview = data(client.post(path+'/merges/preview', json=body))
        merged = data(client.post(path+'/merges/confirm', json=body | confirmation(preview)))
        for action in ('undo', 'restore'):
            p = data(client.post(path+f"/operations/{merged['operation_id']}/preview", json={'action': action}))
            data(client.post(path+f"/operations/{merged['operation_id']}/{action}", json=confirmation(p)))
        detail = data(client.get(path+f'/workspace/concepts/{ids[1]}'))
        assert detail['resolved_id'] == ids[0] and detail['node']['source_count'] == 2
        for ref in detail['source_refs']:
            cite = data(client.get(path+f"/concepts/{ids[1]}/source-evidence/{ref['evidence_id']}"))
            assert cite['quote'] == ref['excerpt'] and cite['graph_digest'] == detail['graph_digest']
        assert data(client.get(f'{ROOT}/{courses[1]}/concepts-page'))['total'] == 2
        # 使用持久合成题目和真实作答接口建立历史，不伪造学习效果。
        store = next(s for s in api_server._tenant_storages.values() if s.get_source(sources[0]))
        aid = store.save_artifact(source_id=sources[0], artifact_type='questions', content=[{'question_type': 'fill', 'stem': '栈顺序', 'answer': '后进先出'}])
        data(client.post('/quiz/attempts', json={'artifact_id': aid, 'question_index': 0, 'user_answer': '错误'}))
        raw = client.get('/api/privacy/export').content
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            tables = json.loads(archive.read('personal-data.json'))['tables']
        assert len(tables['quiz_attempts']) == 1
        before = data(client.get(path+'/workspace'))['graph_digest']
        removal = data(client.get(path+f'/sources/{sources[0]}/remove-preview'))
        data(client.post(path+f'/sources/{sources[0]}/remove', json=confirmation(removal)))
        assert data(client.get(path+'/workspace'))['graph_digest'] != before
        assert data(client.get(path+f'/workspace/concepts/{ids[0]}'))['node']['source_count'] == 1
        assert store._conn().execute('SELECT count(*) FROM quiz_attempts').fetchone()[0] == 1
        p = data(client.post('/api/privacy/restore-preview', files={'file': ('synthetic.zip', raw, 'application/zip')}))
        restored = data(client.post('/api/privacy/restore', json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}))
        assert restored['restored']
        assert data(client.get(path+f'/workspace/concepts/{ids[0]}'))['node']['source_count'] == 2
        assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
        assert store._conn().execute('SELECT count(*) FROM quiz_attempts').fetchone()[0] == 1
        monkeypatch.setenv('FILEMATE_ENABLE_COURSE_GRAPH', '0')
        assert client.get(path+'/workspace').status_code == 503
        assert client.get('/api/knowledge-graph').status_code == 200
