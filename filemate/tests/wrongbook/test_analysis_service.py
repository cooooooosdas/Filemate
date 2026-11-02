"""One explicitly authorized call and literal evidence validation."""
# ruff: noqa: F811

import copy
import importlib
from datetime import timedelta

import pytest

from filemate.execution.storage import QuestionRevisionConflict
from filemate.llm_client import LLMConfig
from filemate.tests.wrongbook.test_analysis_repository import analysis_case  # noqa: F401
from filemate.wrongbook.learning_context import ReviewLearningContext


def output():
    return {'kind': 'insufficient_evidence', 'possible_causes': [], 'uncertainties': ['缺少可核验的教材片段'],
        'smallest_action': '补充原始资料', 'targeted_practice_suggestion': '独立重答原题',
        'schedule_suggestion': '按原复习安排', 'reasons': ['资料不足以判断错因']}


def service(case, runner):
    assert importlib.util.find_spec('filemate.wrongbook.analysis'), '缺少单次复盘服务'
    store, clock, _ = case
    return importlib.import_module('filemate.wrongbook.analysis').ReviewAnalysisService(store,
        lambda: LLMConfig(api_key='synthetic-only-never-real'), runner, lambda: clock[0])


def command(context):
    return {'attempt_id': context['attempt']['attempt_id'], 'input_digest': context['input_digest'],
        'request_key': 'synthetic-service-analysis-0001', 'allow_external_model': True}


class Runner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, config, scope, **kwargs):
        self.calls.append((config, scope, kwargs))
        if callable(self.result):
            return self.result()
        return {'output': self.result, 'usage': None}


@pytest.mark.parametrize('invalid', [False, True])
def test_one_call_and_no_automatic_repair(analysis_case, invalid):
    store, _, context = analysis_case
    result = {'untrusted': '坏结构'} if invalid else output()
    runner = Runner(result)
    api = service(analysis_case, runner)
    view = api.analyze(context['ref']['wrong_id'], command(context))
    assert view['status'] == ('failed' if invalid else 'ready')
    if invalid:
        assert view['error_code'] == 'invalid_output' and view['result'] is None
    assert len(runner.calls) == 1
    assert runner.calls[0][2]['deadline'] > 0
    again = api.analyze(context['ref']['wrong_id'], command(context))
    assert again['analysis_id'] == view['analysis_id'] and len(runner.calls) == 1
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_review_analyses').fetchone()[0] == 1


@pytest.mark.parametrize('corrupt', ['answer', 'source', 'duplicates', 'duplicate_answer', 'unsupported_statistic', 'extra'])
def test_causes_require_literal_answer_and_whitelisted_source_refs(analysis_case, corrupt):
    store, clock, old = analysis_case
    sid = store._conn().execute('SELECT source_id FROM wrong_questions').fetchone()[0]
    with store._conn() as conn:
        conn.execute('UPDATE sources SET raw_text=? WHERE source_id=?', ('栈遵循后进先出的顺序。', sid))
    context = ReviewLearningContext(store, lambda: clock[0]).build(old['ref']['wrong_id'], old['attempt']['attempt_id'])
    cause = {'cause_code': 'concept_gap', 'hypothesis': '可能混淆栈与队列的次序',
        'answer_evidence_refs': [{'attempt_id': context['attempt']['attempt_id'], 'quote': 'B'}],
        'source_evidence_refs': [context['source_evidence'][0]['evidence_id']]}
    valid = {**output(), 'kind': 'supported_hypotheses', 'possible_causes': [cause]}
    result = copy.deepcopy(valid)
    if corrupt == 'answer':
        result['possible_causes'][0]['answer_evidence_refs'][0]['quote'] = '用户并没说过的句子'
    elif corrupt == 'source':
        result['possible_causes'][0]['source_evidence_refs'] = ['fabricated-source']
    elif corrupt == 'duplicates':
        result['possible_causes'].append(copy.deepcopy(cause))
    elif corrupt == 'duplicate_answer':
        result['possible_causes'][0]['answer_evidence_refs'] *= 2
    elif corrupt == 'unsupported_statistic':
        result['possible_causes'][0]['hypothesis'] = '你的掌握率为90%，紧张概率40%'
    else:
        result['mastery'] = 99
    runner = Runner(result)
    view = service((store, clock, context), runner).analyze(context['ref']['wrong_id'], command(context))
    assert view['status'] == 'failed' and view['error_code'] == 'invalid_output'
    assert len(runner.calls) == 1


def test_supported_result_is_saved_but_never_changes_manual_diagnosis(analysis_case):
    store, clock, old = analysis_case
    sid = store._conn().execute('SELECT source_id FROM wrong_questions').fetchone()[0]
    with store._conn() as conn:
        conn.execute('UPDATE sources SET raw_text=? WHERE source_id=?', ('栈遵循后进先出的顺序。', sid))
    context = ReviewLearningContext(store, lambda: clock[0]).build(old['ref']['wrong_id'], old['attempt']['attempt_id'])
    result = {**output(), 'kind': 'supported_hypotheses', 'possible_causes': [{'cause_code': 'concept_gap',
        'hypothesis': '可能混淆次序', 'answer_evidence_refs': [{'attempt_id': context['attempt']['attempt_id'], 'quote': 'B'}],
        'source_evidence_refs': [context['source_evidence'][0]['evidence_id']]}]}
    view = service((store, clock, context), Runner(result)).analyze(context['ref']['wrong_id'], command(context))
    assert view['status'] == 'ready'
    assert store.get_wrong_question(context['ref']['wrong_id'])['error_cause'] == 'unconfirmed'


def test_missing_consent_or_stale_preview_never_calls_model(analysis_case):
    _, _, context = analysis_case
    runner = Runner(output())
    api = service(analysis_case, runner)
    with pytest.raises(ValueError):
        api.analyze(context['ref']['wrong_id'], {**command(context), 'allow_external_model': False})
    with pytest.raises(QuestionRevisionConflict):
        api.analyze(context['ref']['wrong_id'], {**command(context), 'input_digest': '0'*64})
    assert not runner.calls


def test_provider_switch_rejects_late_finish(analysis_case, monkeypatch):
    _, _, context = analysis_case
    def switch():
        monkeypatch.setenv('LLM_MODEL', 'different-model')
        return {'output': output(), 'usage': None}
    view = service(analysis_case, Runner(switch)).analyze(context['ref']['wrong_id'], command(context))
    assert view['status'] == 'failed' and view['error_code'] == 'input_changed'


@pytest.mark.parametrize('changed', [{'course_id': 'another-course'}, {'credential_mode': 'browser'}])
def test_same_key_cannot_change_requested_scope_even_with_old_digest(analysis_case, changed):
    _, _, context = analysis_case
    runner = Runner(output())
    api = service(analysis_case, runner)
    api.analyze(context['ref']['wrong_id'], command(context))
    with pytest.raises(QuestionRevisionConflict):
        api.analyze(context['ref']['wrong_id'], {**command(context), **changed})
    assert len(runner.calls) == 1


def test_deadline_expiry_is_not_reported_as_manual_cancellation(analysis_case):
    _, clock, context = analysis_case
    runner = Runner(None)
    def expire():
        clock[0] += timedelta(seconds=21)
        assert not runner.calls[-1][2]['cancelled'](), '截止由runner计时，不能冒认用户取消'
        return {'error_code': 'timeout'}
    runner.result = expire
    view = service(analysis_case, runner).analyze(context['ref']['wrong_id'], command(context))
    assert view['status'] == 'failed' and view['error_code'] == 'timeout'
