# ruff: noqa: F811
"""合成记录的日期边界、故障排除、报告持久化与全量导出。"""

from fastapi.testclient import TestClient

from filemate.tests.test_programming import complete
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_growth_report_period_evidence_pagination_and_snapshot(server_module):
    module, store = server_module
    from filemate.programming.repository import CodingRepository
    ac = complete(CodingRepository(store), 'AC', 'growth1')
    archived = complete(CodingRepository(store), 'WA', 'growth2')
    conn = store._conn()
    conn.execute("UPDATE coding_events SET created_at='2020-02-01T01:00:00+00:00' WHERE action='completed'")
    conn.execute('UPDATE coding_submissions SET active=0 WHERE submission_id=?', (archived['submission_id'],))
    conn.commit()
    aid = store.save_artifact(artifact_type='questions', content=[{'question_type': 'fill', 'stem': '合成课前提', 'answer': '有序'}])
    with TestClient(module.app) as client:
        for index in range(31):
            assert client.post('/quiz/attempts', json={'artifact_id': aid, 'question_index': 0, 'user_answer': '有序' if index < 20 else '错误'}).status_code == 200
        conn.execute("UPDATE quiz_attempts SET created_at='2020-02-01T01:00:00+00:00'")
        conn.execute("UPDATE quiz_attempts SET created_at='2020-01-31T18:00:00+00:00' WHERE rowid=(SELECT MIN(rowid) FROM quiz_attempts)")
        conn.commit()
        result = client.post('/api/growth/reports', json={'start_date': '2020-02-01', 'end_date': '2020-02-01'})
        assert result.status_code == 200
        report = result.json()['data']; m = report['metrics']; identifier = report['artifact_id']
        assert m['quiz_attempts'] == 31 and m['quiz_correct'] == 20
        assert m['quiz_accuracy'] == 64.52 and m['compiler_submissions'] == 1 and m['compiler_accepted'] == 1
        assert report['excluded_records']['coding'] == 1
        assert report['evidence_total'] == 32 and len(report['records']) == 20
        last = client.get(f'/api/growth/reports/{identifier}/evidence?offset=20').json()['data']
        assert last['total'] == 32 and len(last['items']) == 12
        exported = client.get(f'/api/growth/reports/{identifier}/export?format=json').json()
        assert len(exported['records']) == 32 and ac['submission_id'] in str(exported['records'])
        assert '记录依据' in client.get(f'/api/growth/reports/{identifier}/export').text
        assert client.patch(f'/knowledge/artifacts/{identifier}', json={'title': '伪造摘要', 'content': {}}).status_code == 409
        conn.execute('DELETE FROM quiz_attempts'); conn.commit()
        assert client.get(f'/api/growth/reports/{identifier}').json()['data']['metrics'] == m
        assert client.get('/api/growth/reports').json()['data'][0]['artifact_id'] == identifier
    reopened = type(store)(store.db_path)
    from filemate.portfolio.growth import GrowthRepository
    assert len(GrowthRepository(reopened).get(identifier)['records']) == 32
    reopened.close()


def test_growth_report_empty_invalid_records_and_disabled_module(server_module, monkeypatch):
    module, store = server_module
    with TestClient(module.app) as client:
        empty = client.post('/api/growth/reports', json={'start_date': '2020-01-01', 'end_date': '2020-01-01'}).json()['data']
        assert empty['status'] == 'pending_assessment' and empty['metrics']['quiz_accuracy'] is None and empty['metrics']['interview_model_score'] is None
        assert client.post('/api/growth/reports', json={'start_date': '2020-01-01', 'end_date': '2022-01-01'}).status_code == 422
        assert client.post('/api/growth/reports', json={'start_date': '2099-01-01', 'end_date': '2099-01-01'}).status_code == 422
        aid = store.save_artifact(artifact_type='questions', content=[{'stem': '缺少答案的损坏题目'}])
        conn = store._conn()
        conn.execute("INSERT INTO quiz_attempts(attempt_id,artifact_id,question_index,user_answer,is_correct,score,created_at) VALUES('injected-bad',?,0,'注入损坏记录',1,1,'2020-01-01T01:00:00+00:00')", (aid,)); conn.commit()
        report = client.post('/api/growth/reports', json={'start_date': '2020-01-01', 'end_date': '2020-01-01'}).json()['data']
        assert report['metrics']['quiz_attempts'] == 0 and report['excluded_records']['quiz'] == 1
        assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1
        assert client.get('/api/growth/reports/other-user').status_code == 404
        monkeypatch.setenv('FILEMATE_ENABLE_GROWTH_REPORT', '0')
        assert client.get('/api/growth/reports').status_code == 503
        assert client.get('/analytics/overview').status_code == 200


def test_repeated_correct_review_cannot_overflow_dates(server_module):
    module, store = server_module
    aid = store.save_artifact(artifact_type='questions', content=[{'question_type': 'fill', 'stem': '合成重复复练', 'answer': '有序'}])
    with TestClient(module.app) as client:
        request = {'artifact_id': aid, 'question_index': 0, 'user_answer': '错误'}
        assert client.post('/quiz/attempts', json=request).status_code == 200
        request['user_answer'] = '有序'
        for _ in range(50):
            assert client.post('/quiz/attempts', json=request).status_code == 200
    row = store._conn().execute('SELECT interval_days,ease_factor,correct_streak FROM wrong_questions WHERE artifact_id=?', (aid,)).fetchone()
    assert row['interval_days'] == 365 and row['ease_factor'] == 3.0 and row['correct_streak'] == 50
    assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 51


def test_growth_interview_fallback_and_semester_have_actual_time_basis(server_module):
    module, store = server_module
    interview = store.create_interview(target_role='合成岗位', scenario='practice', difficulty='normal', questions=['合成问题'])
    store.save_interview_turn(interview_id=interview['interview_id'], question_index=0, question='合成问题', answer='合成实际回答',
                              score=None, dimensions={}, feedback='未调用模型', scoring_mode='local_fallback')
    store._conn().execute("UPDATE interview_turns SET created_at='2020-02-01T01:00:00+00:00'"); store._conn().commit()
    from filemate.study.semester import ConfirmSemester, SemesterConfig, SemesterRepository, TaskUpdate
    from filemate.tests.test_p1_semester import CONFIG
    semester = SemesterRepository(store)
    config = SemesterConfig.model_validate(CONFIG)
    preview = semester.preview(config)
    semester.confirm(ConfirmSemester(config=config, confirmed=True, confirmation_token=preview['confirmation_token']))
    identifier = semester.read()['tasks'][0]['task_id']
    content = semester.update(identifier, TaskUpdate(revision=1, completed=True))
    content['tasks'][0]['completed_at'] = '2020-02-01T02:00:00+00:00'
    store.save_artifact(artifact_id='personal-semester-v1', artifact_type='semester', content=content)
    with TestClient(module.app) as client:
        report = client.post('/api/growth/reports', json={'start_date': '2020-02-01', 'end_date': '2020-02-01'}).json()['data']
        assert report['metrics']['interview_answers'] == 1 and report['metrics']['interview_scored_answers'] == 0
        assert report['metrics']['interview_model_score'] is None and report['metrics']['semester_completed_tasks'] == 1
        assert {row['kind'] for row in report['records']} == {'semester', 'interview'}
