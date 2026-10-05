# ruff: noqa: F811
"""简历事实持久化、模型故障和导出合同，模型替身仅用于故障注入。"""

import json

import pytest
from fastapi.testclient import TestClient

from filemate.portfolio.resume import Profile, ResumeRepository, ResumeRequest
from filemate.tests.test_server_persistence import server_module  # noqa: F401

FACTS = {"revision": 0, "name": "合成测试学生", "school": "合成大学", "email": "synthetic@example.test",
         "skills": ["C++"], "projects": [{"project_id": "original", "title": "合成课程项目", "role": "开发", "description": "实现并测试原创算法，不代表真实研究数据"}]}


def test_resume_profile_generate_export_and_reopen(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        assert client.get('/api/resume/profile').json()['data'] is None
        profile = client.put('/api/resume/profile', json=FACTS).json()['data']
        assert profile['revision'] == 1
        assert client.put('/api/resume/profile', json=FACTS).status_code == 409
        resume = client.post('/api/resume/generate', json={'profile_revision': 1}).json()['data']
        assert resume['profile'] == profile and resume['mode'] == 'local'
        identifier = resume['artifact_id']
        assert client.get('/api/resume').json()['data'][0]['artifact_id'] == identifier
        assert client.get(f'/api/resume/{identifier}/export').text == resume['markdown']
        exported = client.get(f'/api/resume/{identifier}/export?format=json').json()
        assert exported['profile_revision'] == 1 and exported['profile']['projects'][0]['description'] == FACTS['projects'][0]['description']
        assert client.patch(f'/knowledge/artifacts/{identifier}', json={'title': '绕过事实', 'content': {}}).status_code == 409
        assert client.patch('/knowledge/artifacts/personal-resume-profile-v1', json={'title': '绕过修订', 'content': {}}).status_code == 409
        assert client.get('/api/resume/not-owned').status_code == 404
    reopened = type(store)(store.db_path)
    assert ResumeRepository(reopened).get(identifier)['markdown'] == resume['markdown']
    reopened.close()


@pytest.mark.parametrize('response', [{'selected_fact_ids': ['education', 'invented-degree']}, {'selected_fact_ids': ['education', 'education']}, {'selected_fact_ids': ['education'], 'invented_text': '获奖十次'}, {'selected_fact_ids': ['skill-0']}])
def test_resume_refuses_fabricated_selection(server_module, monkeypatch, response):
    module, store = server_module
    from filemate.llm_client import LLMClient
    monkeypatch.setattr(LLMClient, '__init__', lambda self, config: None)
    def structured(self, **kwargs):
        payload = json.loads(kwargs['messages'][0]['content'])
        assert 'name' not in payload and 'email' not in payload and 'phone' not in payload
        assert 'synthetic@example.test' not in json.dumps(payload)
        assert kwargs['timeout'] == 45 and kwargs['retry'] == 1
        return response
    monkeypatch.setattr(LLMClient, 'call_structured', structured)
    with TestClient(module.app) as client:
        assert client.put('/api/resume/profile', json=FACTS).status_code == 200
        assert client.post('/api/resume/generate', json={'profile_revision': 1, 'mode': 'llm'}).status_code == 422
        assert client.post('/api/resume/generate', json={'profile_revision': 1, 'mode': 'llm', 'allow_external_model': True}).status_code == 409
        assert client.get('/api/resume').json()['data'] == []
    assert ResumeRepository(store).profile().revision == 1


def test_resume_model_failure_and_concurrent_edit_keep_original(server_module, monkeypatch):
    module, store = server_module
    repo = ResumeRepository(store)
    repo.save_profile(Profile.model_validate(FACTS))
    original = repo.generate(ResumeRequest(profile_revision=1))
    from filemate.llm_client import LLMClient
    monkeypatch.setattr(LLMClient, '__init__', lambda self, config: None)
    def fail(self, **kwargs):
        raise RuntimeError('injected model outage with secret that must not reach client')
    monkeypatch.setattr(LLMClient, 'call_structured', fail)
    with TestClient(module.app) as client:
        failure = client.post('/api/resume/generate', json={'profile_revision': 1, 'mode': 'llm', 'allow_external_model': True})
        assert failure.status_code == 502 and 'secret' not in failure.text
        assert client.get('/api/resume').json()['data'][0]['artifact_id'] == original['artifact_id']
    class ConcurrentModel:
        def call_structured(self, **kwargs):
            repo.save_profile(repo.profile())
            return {'selected_fact_ids': ['education']}
    with pytest.raises(ValueError, match='生成期间'):
        repo.generate(ResumeRequest(profile_revision=1, mode='llm', allow_external_model=True), ConcurrentModel())
    assert len(repo.list()) == 1


def test_resume_invalid_links_corruption_and_module_switch(server_module, monkeypatch):
    module, store = server_module
    with TestClient(module.app) as client:
        body = json.loads(json.dumps(FACTS))
        body['projects'][0]['submission_id'] = 'another-user-code'
        assert client.put('/api/resume/profile', json=body).status_code == 409
        assert client.get('/api/resume/profile').json()['data'] is None
        assert client.put('/api/resume/profile', json=FACTS).status_code == 200
        aid = client.post('/api/resume/generate', json={'profile_revision': 1}).json()['data']['artifact_id']
        content = store.get_artifact(aid)['content']
        content['selected_fact_ids'] = ['education', 'skill-999999']
        store.save_artifact(artifact_id=aid, artifact_type='resume', content=content)
        assert client.get(f'/api/resume/{aid}').status_code == 409
        assert store.get_artifact(aid)['content'] == content
        monkeypatch.setenv('FILEMATE_ENABLE_RESUME', '0')
        assert client.get('/api/resume').status_code == 503
        assert client.get('/knowledge/sources').status_code == 200
