# ruff: noqa: F811
"""Synthetic API / backup contracts for creation configuration."""

import pytest
from fastapi.testclient import TestClient

from filemate.interview_config import ConfigurationRepository, DraftContent
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.test_accounts import HEADERS, account_server, register  # noqa: F401
from filemate.tests.test_interview_coach_analysis import Provider
from filemate.tests.test_interview_coach_api import api  # noqa: F401
from filemate.tests.test_interview_coach_privacy import rewrite_backup


def test_canonical_start_and_legacy_requests(api):
    client, _ = api
    result = client.post('/interviews', json={'target_role': '开发', 'scenario': '技术面',
                         'configuration': {'category': 'technical', 'track': 'technical'}})
    assert result.status_code == 200, result.text
    session = result.json()['data']
    assert session['configuration']['origin'] == 'snapshot'
    assert session['configuration']['duration_minutes'] == 10
    assert session['configuration']['timing_active'] is False
    restored = client.get('/interviews/' + session['interview_id']).json()['data']
    assert restored['configuration'] == session['configuration']
    old = client.post('/interviews', json={'target_role': '开发', 'scenario': '英语面'})
    assert old.json()['data']['configuration']['language'] == 'en-US'


@pytest.mark.parametrize('configuration', [
    {'category': 'creator', 'track': 'knowledge'}, {'question_strategy': 'mixed'},
    {'category': 'technical', 'track': 'technical', 'language': 'en-US'},
    {'category': 'technical', 'track': 'technical'},
])
def test_unsupported_or_mismatched_start_has_no_session_side_effect(api, configuration):
    client, module = api
    before = module._storage._conn().execute('SELECT COUNT(*) FROM interview_sessions').fetchone()[0]
    response = client.post('/interviews', json={'target_role': '测试', 'scenario': '求职面试', 'configuration': configuration})
    assert response.status_code == 422
    assert module._storage._conn().execute('SELECT COUNT(*) FROM interview_sessions').fetchone()[0] == before


def test_draft_round_trip_conflict_and_shutdown(api, monkeypatch):
    client, _ = api
    assert client.get('/interview/configuration').json()['data']['draft']['revision'] == 0
    payload = {'content': {'target_role': '合成目标'}, 'expected_revision': 0, 'expected_token': None, 'request_key': 'draft-api-command01'}
    assert client.put('/interview/configuration/draft', json=payload).status_code == 200
    assert client.put('/interview/configuration/draft', json={key: value for key, value in payload.items() if key != 'expected_token'}).status_code == 422
    assert client.put('/interview/configuration/draft', json=payload).json()['data']['revision'] == 1
    assert client.put('/interview/configuration/draft', json={**payload, 'request_key': 'draft-api-command02'}).status_code == 409
    assert client.put('/interview/configuration/draft', json={**payload, 'content': {'external_consent': True}}).status_code == 422
    monkeypatch.setenv('FILEMATE_ENABLE_INTERVIEW_CONFIG', '0')
    assert client.get('/interview/configuration').json()['data']['enabled'] is False
    assert client.put('/interview/configuration/draft', json=payload).status_code == 503
    assert client.post('/interviews', json={'target_role': '旧版'}).status_code == 200
    assert client.post('/interviews', json={'target_role': '新版', 'configuration': {}}).status_code == 503


def test_account_drafts_are_separate(account_server):
    module = account_server
    with TestClient(module.app, headers=HEADERS) as alice, TestClient(module.app, headers=HEADERS) as bob:
        assert register(alice).status_code == 200
        assert register(bob, 'bob-synthetic@example.invalid').status_code == 200
        assert alice.put('/interview/configuration/draft', json={'content': {'target_role': 'Alice'},
                         'expected_revision': 0, 'expected_token': None, 'request_key': 'alice-draft-command'}).status_code == 200
        assert bob.get('/interview/configuration').json()['data']['draft']['content'] is None
        assert alice.get('/interview/configuration').json()['data']['draft']['content']['target_role'] == 'Alice'


def test_new_and_old_backup_restore_configuration_without_permissions(api, tmp_path):
    client, module = api
    session = client.post('/interviews', json={'target_role': '测试', 'configuration': {}}).json()['data']
    sid = session['interview_id']
    repo = ConfigurationRepository(module._storage)
    repo.save_draft(DraftContent(target_role='合成草稿'), 0, 'backup-draft-command')
    backup = PersonalBackup(module._storage, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    raw = backup.export()
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert module._storage.get_interview(sid)['configuration']['origin'] == 'snapshot'
    assert repo.read_draft()['content']['target_role'] == '合成草稿'
    assert not module._storage._conn().execute('SELECT external_consent FROM interview_coach_state').fetchone()[0]

    def old_content(content):
        content['schema_version'] = 27
        content['tables'].pop('interview_session_config')
        content['tables'].pop('interview_configuration_draft')

    old = rewrite_backup(backup, raw, old_content)
    preview = backup.preview(old)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert module._storage.get_interview(sid)['configuration']['origin'] == 'legacy'
    assert repo.read_draft()['revision'] == 0


def test_fixed_strategy_never_uses_ai_to_select_questions(api, monkeypatch):
    import filemate.llm_client as llm

    client, _ = api
    provider = Provider()
    monkeypatch.setenv('FILEMATE_INTERVIEW_LOCAL_ONLY', '0')
    monkeypatch.setattr(llm, 'LLMClient', lambda _: provider)
    monkeypatch.setattr(llm.LLMConfig, 'from_env', lambda: object())
    response = client.post('/interviews', json={'target_role': '测试', 'configuration': {},
                           'allow_external_analysis': True})
    assert response.status_code == 200, response.text
    assert provider.calls == []


@pytest.mark.parametrize('legacy_backup', [False, True])
def test_restore_never_revives_a_stale_draft_version(api, tmp_path, legacy_backup):
    _, module = api
    repo = ConfigurationRepository(module._storage)
    repo.save_draft(DraftContent(target_role='A'), 0, 'restore-draft-0001')
    backup = PersonalBackup(module._storage, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    raw = backup.export()
    stale = repo.save_draft(DraftContent(target_role='B'), 1, 'restore-draft-0002', 'restore-draft-0001')
    if legacy_backup:
        def old_content(content):
            content['schema_version'] = 27
            content['tables'].pop('interview_session_config')
            content['tables'].pop('interview_configuration_draft')
        raw = rewrite_backup(backup, raw, old_content)
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    current = repo.read_draft()
    saved = repo.save_draft(DraftContent(target_role='C'), current['revision'], 'restore-draft-0003', current['version_token'])
    with pytest.raises(ValueError, match='草稿'):
        repo.save_draft(DraftContent(target_role='stale'), stale['revision'], 'restore-draft-0004', stale['version_token'])
    assert repo.read_draft() == saved
