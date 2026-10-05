# ruff: noqa: F811
"""永久删除编程源码及其派生产物的真实存储合同。"""

from fastapi.testclient import TestClient

from filemate.programming.repository import CodingRepository
from filemate.tests.test_programming import complete, create
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_coding_delete_erases_artifact_feedback_reports_and_unlinks_profile(server_module):
    module, store = server_module
    repo = CodingRepository(store)
    row = complete(repo, 'AC', 'delete-original')
    identifier = row['submission_id']
    from filemate.portfolio.resume import Profile, ResumeRepository, ResumeRequest
    from filemate.tests.test_p1_resume import FACTS
    facts = Profile.model_validate(FACTS); facts.projects[0].submission_id = identifier
    resumes = ResumeRepository(store); resumes.save_profile(facts)
    document = resumes.generate(ResumeRequest(profile_revision=1))
    from datetime import datetime

    from filemate.portfolio.growth import REPORT_ZONE, GrowthRepository, ReportRequest
    today = datetime.now(REPORT_ZONE).date()
    report = GrowthRepository(store).generate(ReportRequest(start_date=today, end_date=today))
    assert any(record['record_id'] == identifier for record in report['records'])
    with TestClient(module.app) as client:
        preview = client.get(f'/api/programming/submissions/{identifier}/delete-preview').json()['data']
        assert preview['related_reports'] == 2 and preview['profile_links'] == 1
        assert client.delete(f'/api/programming/submissions/{identifier}').status_code == 422
        request = {'confirmed': True, 'confirmation_token': preview['confirmation_token']}
        deleted = client.request('DELETE', f'/api/programming/submissions/{identifier}', json=request)
        assert deleted.status_code == 200
        assert client.request('DELETE', f'/api/programming/submissions/{identifier}', json=request).json()['data'] == deleted.json()['data']
        assert client.get(f'/api/programming/submissions/{identifier}').status_code == 404
    assert store.get_artifact(row['artifact_id']) is None
    assert store.get_artifact(document['artifact_id']) is None and store.get_artifact(report['artifact_id']) is None
    assert repo.list() == [] and store._conn().execute('SELECT COUNT(*) FROM coding_events').fetchone()[0] == 0
    profile = resumes.profile(); assert profile.revision == 2 and profile.projects[0].submission_id is None
    audit = store._conn().execute("SELECT * FROM data_action_audit WHERE action='coding_delete'").fetchall()
    assert len(audit) == 1 and 'int main' not in str(dict(audit[0]))


def test_coding_delete_requires_fresh_owned_preview_and_finished_task(server_module):
    module, store = server_module
    repo = CodingRepository(store); queued = create(repo, 'queued-delete')
    completed = complete(repo, 'WA', 'changed-delete'); identifier = completed['submission_id']
    with TestClient(module.app) as client:
        assert client.get(f"/api/programming/submissions/{queued['submission_id']}/delete-preview").status_code == 409
        preview = client.get(f'/api/programming/submissions/{identifier}/delete-preview').json()['data']
        repo.update(identifier, payload={'notes': '预览后新增的合成笔记'}, event='notes_saved')
        assert client.request('DELETE', f'/api/programming/submissions/{identifier}', json={'confirmed': True, 'confirmation_token': preview['confirmation_token']}).status_code == 409
        assert client.request('DELETE', '/api/programming/submissions/not-owned', json={'confirmed': True, 'confirmation_token': preview['confirmation_token']}).status_code == 404
    assert repo.get(identifier)['notes'] == '预览后新增的合成笔记'
