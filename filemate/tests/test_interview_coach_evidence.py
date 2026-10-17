"""Current-answer evidence and historical artifact boundaries."""

import json

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import AdvanceCommand, SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository
from filemate.interview_coach.service import CoachAnalysisService
from filemate.interview_review.repository import ReviewRepository
from filemate.tests.test_interview_coach_analysis import (
    ANSWER,
    Provider,
    authorize,
    command,
    payload,
)


@pytest.fixture
def context(tmp_path):
    store = SQLiteStorage(tmp_path / 'evidence.db')
    store.init_schema()
    source = store.save_source(original_name='合成课程', source_path='synthetic.txt', raw_text='原理')
    run = store.create_agent_run(task_type='interview_session', goal='合成训练', selected_agents=[], context_refs={'source_id': source})
    sid = store.create_interview(target_role='开发', scenario='技术面', difficulty='标准', questions=['介绍项目','第二题'], agent_run_id=run['run_id'])['interview_id']
    repo = CoachRepository(store)
    repo.submit(sid, SubmitAnswer(answer=ANSWER, question_index=0, request_key='evidence_answer1', expected_revision=0))
    yield store, repo, sid, source
    store.close()


def reanswer(repo, sid):
    state = repo.snapshot(sid)
    return repo.submit(sid, SubmitAnswer(answer=ANSWER + '，这是修改后的回答', question_index=0,
        request_key='evidence_answer2', expected_revision=state.revision, expected_attempt_id=state.current_attempt.attempt_id)).snapshot


def test_failed_last_excluded_and_historical_report_never_overwritten(context):
    store, repo, sid, _ = context
    provider = Provider()
    first = CoachAnalysisService(store, lambda: provider).analyze(sid, command(authorize(repo,sid,provider))).snapshot
    old = ReviewRepository(store).generate(sid)
    state = reanswer(repo,sid)
    provider.failure = RuntimeError('synthetic failure')
    with pytest.raises(CoachError):
        CoachAnalysisService(store, lambda: provider).analyze(sid, command(state, 'evidence_analyze2'))
    report = ReviewRepository(store).generate(sid)
    assert (report['assessed'],report['overall_score']) == (0,None)
    assert report['turns'][0]['attempt_id'] == state.current_attempt.attempt_id
    assert store.get_learning_analytics()['evidence_profile']['metrics']['interview']['sample_count'] == 0
    assert repo.list_attempts(sid,first.current_attempt.turn_id)['items'][1]['score'] == 80
    assert store.get_artifact(old['artifact_id'])['content'] == old
    assert report['artifact_id'] != old['artifact_id']


def test_source_lineage_unassessed_is_not_placeholder_zero_but_valid_zero_counts(context):
    store, repo, sid, source = context
    stage = next(v for v in store.get_source_lineage(source)['stages'] if v['key']=='interview')
    assert '均分' not in stage['secondary']
    assert '待分析' in stage['secondary']
    provider = Provider()
    zero = payload() | {'score':0}
    provider.call = lambda **kwargs: json.dumps(zero,ensure_ascii=False)
    CoachAnalysisService(store, lambda: provider).analyze(sid, command(authorize(repo,sid,provider)))
    stage = next(v for v in store.get_source_lineage(source)['stages'] if v['key']=='interview')
    assert '均分 0' in stage['secondary']


def test_bad_current_json_preserves_other_answers_and_raw_text(context):
    store, repo, sid, _ = context
    state=repo.snapshot(sid)
    repo.advance(sid,AdvanceCommand(from_index=0,expected_attempt_id=state.current_attempt.attempt_id,
                  expected_revision=state.revision,request_key='evidence_advance'))
    state=repo.snapshot(sid)
    repo.submit(sid,SubmitAnswer(answer='第二题健康原文',question_index=1,request_key='evidence_second2',expected_revision=state.revision))
    conn=store._conn()
    conn.execute("UPDATE interview_turns SET dimensions='{broken' WHERE interview_id=? AND question_index=0",(sid,))
    conn.commit()
    current=store.get_interview(sid)
    assert current['turns'][0]['answer'] == ANSWER
    assert current['turns'][0]['score'] is None
    assert current['turns'][0]['analysis_data_error'] is True
    assert current['turns'][1]['answer'] == '第二题健康原文'
    assert conn.execute('SELECT dimensions FROM interview_turns WHERE question_index=0').fetchone()[0]=='{broken'


def test_history_comparison_and_read_position_do_not_change_report_input(context):
    from filemate.interview_coach.repository import attempt_comparison

    store, repo, sid, _ = context
    provider=Provider()
    state=CoachAnalysisService(store,lambda:provider).analyze(sid,command(authorize(repo,sid,provider))).snapshot
    state=reanswer(repo,sid)
    comparison=attempt_comparison(store._conn(),state.current_attempt.turn_id)
    assert comparison['scores_comparable'] is False
    assert comparison['first']['answer']==ANSWER
    assert comparison['last']['answer']==ANSWER+'，这是修改后的回答'
    report=ReviewRepository(store).generate(sid)
    repo.advance(sid,AdvanceCommand(from_index=0,expected_attempt_id=state.current_attempt.attempt_id,
                 expected_revision=state.revision,request_key='evidence_advance'))
    repo.list_attempts(sid,state.current_attempt.turn_id,limit=1)
    assert ReviewRepository(store).report(sid)==report


def test_corrupt_current_cache_cannot_leave_score_in_coach_snapshot(context):
    store, repo, sid, _ = context
    provider=Provider()
    CoachAnalysisService(store,lambda:provider).analyze(sid,command(authorize(repo,sid,provider)))
    store._conn().execute("UPDATE interview_turns SET content_analysis='{broken' WHERE interview_id=?",(sid,))
    store._conn().commit()
    state=repo.snapshot(sid)
    assert state.current_attempt.score is None
    assert state.current_attempt.data_error is True
    assert state.current_attempt.answer==ANSWER


@pytest.mark.parametrize('malformed',[[],None,False,'broken',42])
def test_nested_corrupt_run_json_keeps_read_and_privacy_available(context,malformed):
    store,repo,sid,_=context;p=Provider()
    CoachAnalysisService(store,lambda:p).analyze(sid,command(authorize(repo,sid,p)))
    raw=json.dumps({'score':80,'content_analysis':malformed})
    store._conn().execute('UPDATE interview_coach_analysis_runs SET evaluation=?',(raw,));store._conn().commit()
    state=repo.snapshot(sid)
    assert state.current_attempt.answer==ANSWER and state.current_attempt.score is None
    assert state.current_attempt.data_error
    assert repo.list_attempts(sid,state.current_attempt.turn_id)['items'][0]['score'] is None
    review=ReviewRepository(store);assert review.delete_preview(sid)['answer_attempts']==1
    assert store._conn().execute('SELECT evaluation FROM interview_coach_analysis_runs').fetchone()[0]==raw
    review.clear(sid);assert repo.snapshot(sid).current_attempt.answer==ANSWER


@pytest.mark.parametrize('scenario,text,field',[('技术面','我验证了索引的性能边界','chars_per_minute'),('英语面','I measured the baseline and checked the result','words_per_minute')])
def test_coach_report_retains_server_calculated_speech_metrics(tmp_path,scenario,text,field):
    store=SQLiteStorage(tmp_path/'fluency.db');store.init_schema()
    sid=store.create_interview(target_role='训练',scenario=scenario,difficulty='标准',questions=['Explain'])['interview_id']
    repo=CoachRepository(store)
    first=repo.submit(sid,SubmitAnswer(answer=text,question_index=0,request_key='speech_first_001',expected_revision=0,fluency_metrics={'duration_seconds':10})).snapshot
    report=ReviewRepository(store).generate(sid);assert report['expression'][field]>0
    second=repo.submit(sid,SubmitAnswer(answer=text+' test',question_index=0,request_key='speech_second001',expected_revision=first.revision,expected_attempt_id=first.current_attempt.attempt_id,fluency_metrics={'duration_seconds':20})).snapshot
    assert ReviewRepository(store).generate(sid)['expression'][field]>0
    assert second.current_attempt.fluency_metrics[field]>0
    store.close()
