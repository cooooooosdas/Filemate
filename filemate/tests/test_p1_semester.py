# ruff: noqa: F811
"""学期编排的预览确认、课程权限、持久进度与历史保存。"""

from copy import deepcopy

from fastapi.testclient import TestClient

from filemate.tests.test_server_persistence import server_module  # noqa: F401

CONFIG = {'revision': 0, 'title': '合成秋季学期', 'start_date': '2026-09-01', 'end_date': '2026-09-28', 'courses': [
    {'course_id': 'algorithms', 'title': '合成算法课程', 'objective': '实现并复习本周课程算法', 'weekly_minutes': 90, 'weekday': 4, 'exam_date': '2026-09-28'}]}


def test_semester_preview_confirm_progress_revision_history(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        assert client.get('/api/semester').json()['data'] is None
        preview = client.post('/api/semester/preview', json=CONFIG).json()['data']
        assert preview['week_count'] == 4 and preview['task_count'] == 5
        assert client.get('/api/semester').json()['data'] is None
        request = {'config': CONFIG, 'confirmed': True, 'confirmation_token': preview['confirmation_token']}
        assert client.post('/api/semester/confirm', json={**request, 'confirmed': False}).status_code == 422
        receipt = client.post('/api/semester/confirm', json=request).json()['data']
        assert receipt['revision'] == 1
        assert client.post('/api/semester/confirm', json=request).json()['data'] == receipt
        state = client.get('/api/semester').json()['data']
        assert len(state['tasks']) == 5
        identifier = state['tasks'][0]['task_id']
        changed = client.patch(f'/api/semester/tasks/{identifier}', json={'revision': 1, 'completed': True}).json()['data']
        assert changed['config']['revision'] == 2 and changed['tasks'][0]['completed_at']
        assert client.patch(f'/api/semester/tasks/{identifier}', json={'revision': 1, 'completed': False}).status_code == 409
        assert client.patch(f'/api/semester/tasks/{identifier}', json={'revision': 2, 'completed': True}).json()['data'] == changed
        new = deepcopy(CONFIG); new.update(revision=2, title='第二版学期')
        p = client.post('/api/semester/preview', json=new).json()['data']
        assert p['previous_completed'] == 1
        assert client.post('/api/semester/confirm', json={'config': new, 'confirmed': True, 'confirmation_token': p['confirmation_token']}).status_code == 200
        assert not any(task['completed'] for task in client.get('/api/semester').json()['data']['tasks'])
        assert client.patch('/knowledge/artifacts/personal-semester-v1', json={'title': '绕过确认', 'content': {}}).status_code == 409
    history = store._conn().execute("SELECT content FROM artifacts WHERE artifact_type='semester_history'").fetchall()
    assert len(history) == 1 and 'completed_at' in history[0][0]
    reopened = type(store)(store.db_path)
    from filemate.study.semester import SemesterRepository
    assert SemesterRepository(reopened).read()['config']['title'] == '第二版学期'
    reopened.close()


def test_semester_rejects_invalid_dates_foreign_sources_and_changed_preview(server_module, monkeypatch):
    module, _store = server_module
    with TestClient(module.app) as client:
        wrong = deepcopy(CONFIG); wrong['end_date'] = '2028-01-01'
        assert client.post('/api/semester/preview', json=wrong).status_code == 422
        wrong = deepcopy(CONFIG); wrong['courses'][0]['exam_date'] = '2027-01-01'
        assert client.post('/api/semester/preview', json=wrong).status_code == 422
        wrong = deepcopy(CONFIG); wrong['courses'][0]['source_id'] = 'not-current-user'
        assert client.post('/api/semester/preview', json=wrong).status_code == 409
        preview = client.post('/api/semester/preview', json=CONFIG).json()['data']
        wrong = deepcopy(CONFIG); wrong['courses'][0]['objective'] = '更换计划'
        assert client.post('/api/semester/confirm', json={'config': wrong, 'confirmed': True, 'confirmation_token': preview['confirmation_token']}).status_code == 409
        assert client.get('/api/semester').json()['data'] is None
        monkeypatch.setenv('FILEMATE_ENABLE_SEMESTER', '0')
        assert client.get('/api/semester').status_code == 503
        assert client.get('/study-plans').status_code == 200
