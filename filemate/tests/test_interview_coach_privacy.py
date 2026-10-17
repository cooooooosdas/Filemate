"""Synthetic version erasure and restore contracts; no real user data."""
import hashlib
import hmac
import io
import json
import zipfile

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachRepository
from filemate.interview_coach.service import CoachAnalysisService
from filemate.interview_review.repository import ReviewRepository
from filemate.operations.personal_backup import PersonalBackup, _json
from filemate.tests.test_interview_coach_analysis import ANSWER, Provider, authorize, command


@pytest.fixture
def context(tmp_path):
    store=SQLiteStorage(tmp_path/'filemate.db');store.init_schema()
    sid=store.create_interview(target_role='合成方向',scenario='技术面',difficulty='标准',questions=['介绍项目','第二题'])['interview_id']
    repo=CoachRepository(store)
    repo.submit(sid,SubmitAnswer(answer=ANSWER,question_index=0,request_key='privacy_first001',expected_revision=0))
    backup=PersonalBackup(store,'local',tmp_path/'inbox',tmp_path/'archive')
    yield store,repo,sid,backup
    store.close()


def second(repo,sid):
    state=repo.snapshot(sid)
    return repo.submit(sid,SubmitAnswer(answer=ANSWER+'，第二版',question_index=0,request_key='privacy_second01',expected_revision=state.revision,expected_attempt_id=state.current_attempt.attempt_id)).snapshot


def test_delete_preview_changes_after_reanswer_and_repeat_delete_is_safe(context):
    store,repo,sid,_=context;review=ReviewRepository(store)
    review.generate(sid);old=review.delete_preview(sid)
    second(repo,sid);review.generate(sid)
    with pytest.raises(ValueError):review.delete(sid,old['confirmation_token'])
    preview=review.delete_preview(sid)
    assert preview['answer_attempts']==2 and preview['reports']==2
    assert 'analysis_runs' in preview and preview['coach_actions']==2
    assert review.delete(sid,preview['confirmation_token'])['deleted']
    assert review.delete(sid,preview['confirmation_token'])['deleted']
    for table in ['interview_answer_attempts','interview_coach_state','interview_coach_questions','interview_coach_analysis_runs','interview_coach_actions']:
        assert store._conn().execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
    assert store._conn().execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='interview_report'").fetchone()[0]==0


def test_clear_erases_all_versions_and_keeps_raw_answers(context):
    store,repo,sid,_=context;p=Provider()
    CoachAnalysisService(store,lambda:p).analyze(sid,command(authorize(repo,sid,p)))
    ReviewRepository(store).generate(sid);second(repo,sid)
    ReviewRepository(store).generate(sid)
    ReviewRepository(store).clear(sid)
    history=repo.list_attempts(sid,repo.snapshot(sid).current_attempt.turn_id)['items']
    assert [a['answer'] for a in history]==[ANSWER+'，第二版',ANSWER]
    assert all(a['score'] is None and a['evaluation']=={} and a['visual_metrics']=={} for a in history)
    assert store._conn().execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='interview_report'").fetchone()[0]==0
    assert store.get_learning_analytics()['average_interview_score'] is None


def test_export_restore_preserves_history_but_never_replays_analysis(context):
    store,repo,sid,backup=context;p=Provider();state=second(repo,sid)
    state=authorize(repo,sid,p)
    run=repo.claim_analysis(sid,command(state),provider_identity=state.provider_identity,model='fixture')['run']
    before=repo.list_attempts(sid,state.current_attempt.turn_id)['items']
    raw=backup.export()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        content=json.loads(z.read('personal-data.json'))
        assert len(content['tables']['interview_answer_attempts'])==2
        assert not {'accounts','account_sessions'} & content['tables'].keys()
    store._conn().execute("UPDATE interview_coach_analysis_runs SET status='failed'");store._conn().commit()
    preview=backup.preview(raw);backup.restore(preview['backup_id'],preview['confirmation_token'])
    restored=repo.snapshot(sid)
    assert restored.external_consent is False
    assert store._conn().execute('SELECT status FROM interview_coach_analysis_runs WHERE run_id=?',(run['run_id'],)).fetchone()[0]=='interrupted'
    after=repo.list_attempts(sid,state.current_attempt.turn_id)['items']
    assert [(a['answer'],a['created_at']) for a in after]==[(a['answer'],a['created_at']) for a in before]
    assert p.calls==[]


def test_personal_restore_rejects_live_analysis_before_changes(context):
    _store,repo,sid,backup=context;p=Provider();state=authorize(repo,sid,p)
    repo.claim_analysis(sid,command(state),provider_identity=state.provider_identity,model='fixture')
    raw=backup.export();preview=backup.preview(raw)
    with pytest.raises(ValueError,match='任务|分析'):backup.restore(preview['backup_id'],preview['confirmation_token'])
    assert repo.snapshot(sid).external_consent


def rewrite_backup(backup,raw,change):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:files={name:z.read(name) for name in z.namelist()}
    content=json.loads(files['personal-data.json']);change(content);files['personal-data.json']=_json(content)
    manifest=json.loads(files['manifest.json']);manifest.pop('signature');manifest['files']={name:hashlib.sha256(value).hexdigest() for name,value in files.items() if name!='manifest.json'}
    manifest['signature']=hmac.new(backup._key(),_json(manifest),hashlib.sha256).hexdigest();files['manifest.json']=_json(manifest)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    return stream.getvalue()


def test_restore_schema26_backfills_and_corruption_rolls_back(context):
    store,repo,sid,backup=context
    def old(data):
        data['schema_version']=26
        for name in list(data['tables']):
            if name.startswith('interview_coach_') or name=='interview_answer_attempts':del data['tables'][name]
    raw=rewrite_backup(backup,backup.export(),old)
    preview=backup.preview(raw);backup.restore(preview['backup_id'],preview['confirmation_token'])
    assert repo.snapshot(sid).current_attempt is None  # old sequential workflow is on its next question
    assert store._conn().execute('SELECT answer FROM interview_answer_attempts').fetchone()[0]==ANSWER
    bad=rewrite_backup(backup,backup.export(),lambda d:d['tables']['interview_answer_attempts'][0].update(turn_id='missing'))
    preview=backup.preview(bad)
    with pytest.raises(ValueError,match='关系'):backup.restore(preview['backup_id'],preview['confirmation_token'])
    assert store._conn().execute('SELECT answer FROM interview_answer_attempts').fetchone()[0]==ANSWER


def test_admin_restore_normalizes_after_hash_verification(context,tmp_path,monkeypatch):
    from filemate.operations import backup as admin
    store,repo,sid,_=context;p=Provider();state=authorize(repo,sid,p)
    repo.claim_analysis(sid,command(state),provider_identity=state.provider_identity,model='fixture')
    # The managed admin root must not contain the sibling restore output.
    managed=tmp_path/'managed';managed.mkdir()
    with __import__('sqlite3').connect(managed/'filemate.db') as copied:
        store._conn().backup(copied)
    copied.close()
    (managed/'identity.secret').write_bytes(b'synthetic-only-identity-key-00000000000')
    monkeypatch.delenv('FILEMATE_IDENTITY_SECRET',raising=False)
    snapshot=tmp_path/'snapshot';plan=admin.plan_backup(managed);admin.create_backup(managed,snapshot,plan['confirmation'],quiesced=True)
    target=tmp_path/'restored';plan=admin.plan_restore(snapshot,target);result=admin.restore_backup(snapshot,target,plan['confirmation'])
    assert result['normalized_coach_databases']==1 and result['activated'] is False
    restored=SQLiteStorage(target/'filemate.db');restored.init_schema()
    assert CoachRepository(restored).snapshot(sid).external_consent is False
    assert restored._conn().execute('SELECT status FROM interview_coach_analysis_runs').fetchone()[0]=='interrupted'
    assert admin.verify_backup(snapshot)['passed']
    restored.close()


def test_admin_normalization_leaves_schema26_bytes_unmodified(tmp_path):
    from filemate.interview_coach.repository import normalize_restored_coach
    from filemate.tests.test_interview_coach_storage import legacy_db
    path=tmp_path/'legacy.db';legacy_db(path)
    original=path.read_bytes()
    import sqlite3
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    with conn:
        conn.execute('BEGIN IMMEDIATE');normalize_restored_coach(conn)
    conn.close()
    assert path.read_bytes()==original
    store=SQLiteStorage(path);store.init_schema()
    assert store._conn().execute('SELECT COUNT(*) FROM interview_answer_attempts').fetchone()[0]==1
    store.close()
