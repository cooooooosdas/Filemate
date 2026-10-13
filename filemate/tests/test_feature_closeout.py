# ruff: noqa: F811
"""合成资料回归：专项面试授权、真实证据推荐与可读取的文档导出。"""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PyPDF2 import PdfReader

from filemate.portfolio.document_export import document_docx, document_pdf
from filemate.programming.recommendations import recommend_problems
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.understanding.interview import InterviewEvaluator
from filemate.understanding.interview_practice import grounded_followup


@pytest.mark.parametrize('scenario', ['技术面', '算法面', 'HR面', '压力面', '英语面'])
def test_specialist_interview_persists_actual_followup_without_model(server_module, scenario):
    module, store = server_module
    answer = 'I built a synthetic course project and tested it.' if scenario == '英语面' else '我实现了合成课程项目的接口并测试边界。'
    with TestClient(module.app) as client:
        created = client.post('/interviews', json={
            'target_role': '合成测试方向', 'scenario': scenario, 'difficulty': '入门',
        })
        assert created.status_code == 200
        session = created.json()['data']
        assert len(session['questions']) == 5
        updated = client.post(f"/interviews/{session['interview_id']}/answers", json={
            'answer': answer,
        })
        assert updated.status_code == 200
        next_question = updated.json()['data']['current_question']
        assert answer in next_question
        assert ('one concrete example' if scenario == '英语面' else '一个具体例子') in next_question
        assert store.get_interview(session['interview_id'])['questions'][1] == next_question
        assert store.get_interview(session['interview_id'])['question_ids'][1] is None
        assert client.get('/interview/practice/memories').json()['data'] == []


def test_interview_memory_requires_grant_and_forget_is_confirmed_idempotent(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        old = client.post('/interviews', json={
            'target_role': '合成测试方向', 'scenario': '技术面', 'remember_for_future': True,
        }).json()['data']
        answer = '我用真实测试记录验证了合成接口。'
        client.post(f"/interviews/{old['interview_id']}/answers", json={'answer': answer})
        memories = client.get('/interview/practice/memories').json()['data']
        assert len(memories) == 1 and memories[0]['answer_count'] == 1
        assert answer not in json.dumps(memories, ensure_ascii=False)
        identifier = memories[0]['memory_id']
        request = {'target_role': '合成测试方向', 'scenario': '项目面', 'project_name': '合成作品',
                   'project_details': '我负责课程项目的输入验证。', 'memory_id': identifier}
        current = client.post('/interviews', json=request).json()['data']
        reserved = current['questions'][1]
        assert answer in reserved and '合成作品' in current['questions'][0]
        updated = client.post(f"/interviews/{current['interview_id']}/answers", json={
            'answer': '我负责输入验证。',
        }).json()['data']
        assert updated['current_question'] == reserved
        path = f'/interview/practice/memories/{identifier}'
        preview = client.get(path + '/forget-preview').json()['data']
        assert client.request('DELETE', path, json={}).status_code == 422
        assert client.request('DELETE', path, json={'confirmed': True, 'confirmation_token': 'bad'}).status_code == 409
        confirmation = {'confirmed': True, 'confirmation_token': preview['confirmation_token']}
        for _ in range(2):
            assert client.request('DELETE', path, json=confirmation).status_code == 200
        assert client.get('/interview/practice/memories').json()['data'] == []
        assert client.post('/interviews', json=request).status_code == 409
        assert store.get_interview(old['interview_id'])['turns'][0]['answer'] == answer
        assert store.get_interview(current['interview_id'])['questions'][1] == reserved
        count = store._conn().execute("SELECT COUNT(*) FROM interview_review_events WHERE action='practice_memory_forgotten'").fetchone()[0]
        assert count == 1


def test_project_mode_rejects_missing_facts_and_does_not_create_resume_profile(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        assert client.post('/interviews', json={'target_role': '测试', 'scenario': '项目面'}).status_code == 422
        assert client.get('/api/resume/profile').json()['data'] is None
    assert store.list_agent_runs() == []


def test_followup_never_quotes_model_invention_as_user_evidence():
    answer = '我完成了输入验证。'
    question = grounded_followup(answer, '技术面', 1, {
        'areas': {'completeness': {'status': 'partial', 'evidence': '我获得了十次奖项。'}},
    })
    assert answer in question and '十次奖项' not in question


def test_english_speech_records_words_without_uncalibrated_fluency_score():
    result = InterviewEvaluator(None).evaluate('Introduce yourself.', 'I tested the code.', '', {
        'duration_seconds': 30, 'filler_count': 0, 'long_pause_count': 0,
        'source': 'speech_recognition', 'markers': [],
    }, speech_language='en-US')
    assert result['fluency']['words_per_minute'] == 8
    assert 'reference_score' not in result['fluency']
    assert '流畅性' not in result['dimensions'] and result['score'] is None


def test_recommendation_uses_valid_evidence_and_respects_mastery():
    wrong = {'problem_id': 'array-sum', 'mastered': False, 'error_count': 1,
             'correct_streak': 0, 'latest_error_id': 'actual-1', 'latest_submission_id': 'actual-1'}
    record = {'problem_id': 'array-sum', 'submission_id': 'actual-1', 'active': True,
              'status': 'completed', 'result': {'verdict': 'WA'}}
    recommended = recommend_problems([record], {'wrongbook': [wrong]})
    assert recommended[0]['problem_id'] == 'array-sum'
    assert recommended[0]['basis_submission_ids'] == ['actual-1']
    cold = recommend_problems([{**record, 'active': False}], {})
    assert all(not row['basis_submission_ids'] for row in cold)
    assert all('不据此判断' in row['reason'] for row in cold)
    mastered = recommend_problems([record], {'wrongbook': [{**wrong, 'mastered': True}]})
    assert mastered[0]['problem_id'] != 'array-sum'


def test_pdf_and_docx_preserve_chinese_and_treat_markup_as_plain_text():
    markdown = '# 合成简历\n## 实际项目\n我完成输入验证。<img src="https://example.invalid/pixel">\n' + '\n'.join(['合成课程记录，不代表真实学习效果。'] * 150)
    pdf = document_pdf(markdown, title='合成简历')
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) > 1
    text = ''.join(page.extract_text() for page in reader.pages)
    assert '合成简历' in text and '<img src=' in text and '真实学习效果' in text
    docx = document_docx(markdown, title='合成简历')
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        xml = archive.read('word/document.xml').decode()
        assert '合成简历' in xml and '&lt;img' in xml
        assert 'TargetMode="External"' not in archive.read('word/_rels/document.xml.rels').decode()


@pytest.mark.parametrize('exporter', [document_pdf, document_docx])
@pytest.mark.parametrize('content', ['汉' * 700000, '\n' * 20001], ids=['byte-limit', 'paragraph-limit'])
def test_document_export_rejects_oversized_inputs(exporter, content):
    with pytest.raises(ValueError):
        exporter(content, title='合成测试')


def test_resume_and_growth_download_routes_return_readable_files(server_module):
    module, _ = server_module
    with TestClient(module.app) as client:
        client.put('/api/resume/profile', json={'revision': 0, 'name': '合成学生', 'school': '合成大学'})
        resume = client.post('/api/resume/generate', json={'profile_revision': 1}).json()['data']['artifact_id']
        growth = client.post('/api/growth/reports', json={'start_date': '2020-01-01', 'end_date': '2020-01-01'}).json()['data']['artifact_id']
        for path in [f'/api/resume/{resume}/export', f'/api/growth/reports/{growth}/export']:
            response = client.get(path + '?format=pdf')
            assert response.status_code == 200 and response.headers['content-type'] == 'application/pdf'
            assert len(PdfReader(io.BytesIO(response.content)).pages) >= 1
        word = client.get(f'/api/resume/{resume}/export?format=docx')
        assert word.status_code == 200 and zipfile.is_zipfile(io.BytesIO(word.content))
        assert client.get('/api/resume/other-space/export?format=pdf').status_code == 404
