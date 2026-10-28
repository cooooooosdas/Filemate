"""AI hypotheses become diagnosis only after a current explicit preview."""
# ruff: noqa: F811

import importlib

import pytest

from filemate.execution.storage import QuestionRevisionConflict
from filemate.tests.wrongbook.test_analysis_repository import (  # noqa: F401
    analysis_case,
    repository,
)
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.repository import ReviewRepository


def commands(store, clock):
    assert importlib.util.find_spec('filemate.wrongbook.learning_commands'), '缺少错因采纳预览与确认'
    return importlib.import_module('filemate.wrongbook.learning_commands').ReviewLearningCommands(store, lambda: clock[0])


def supported(case, causes=None):
    store, clock, context = case
    wid = context['ref']['wrong_id']
    old = ReviewRepository(store).detail(wid)
    ReviewRepository(store, clock=lambda: clock[0]).diagnose(wid, {'expected_revision': old['revision'],
        'request_key': 'synthetic-manual-before-0001', 'error_causes': causes or ['memory_gap'],
        'primary_cause': (causes or ['memory_gap'])[0], 'note': '保留人工备注', 'custom_tags': ['待讨论']})
    context = ReviewLearningContext(store, lambda: clock[0]).build(wid, context['attempt']['attempt_id'])
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-adopt-analysis-0001')
    assert repo.finish(view['analysis_id'], epoch, {'kind': 'supported_hypotheses',
        'possible_causes': [{'cause_code': 'concept_gap', 'hypothesis': '候选原因'}]}, {})
    return view['analysis_id'], ReviewRepository(store).detail(wid)['revision']


def test_adoption_preserves_manual_causes_and_requires_current_preview(analysis_case):
    store, clock, context = analysis_case
    aid, revision = supported(analysis_case)
    wid = context['ref']['wrong_id']
    api = commands(store, clock)
    selection = {'selected_causes': ['concept_gap'], 'expected_revision': revision}
    preview = api.preview_adoption(wid, aid, selection)
    assert preview['after']['error_causes'] == ['memory_gap', 'concept_gap']
    assert ReviewRepository(store).detail(wid)['error_causes'] == ['memory_gap']
    result = api.confirm_adoption(wid, aid, selection, preview['confirmation_token'], 'synthetic-adopt-confirm-0001', True)
    row = ReviewRepository(store).detail(wid)
    assert row['error_cause_source'] == 'user'
    assert row['error_causes'] == ['memory_gap', 'concept_gap']
    assert row['error_cause_note'] == '保留人工备注' and row['custom_tags'] == ['待讨论']
    assert result['review_event_id'] and result['analysis_id'] == aid
    assert api.confirm_adoption(wid, aid, selection, preview['confirmation_token'], 'synthetic-adopt-confirm-0001', True) == result
    assert store._conn().execute("SELECT COUNT(*) FROM review_events WHERE action='analysis_adopt'").fetchone()[0] == 1


def test_adoption_never_silently_removes_existing_causes(analysis_case):
    store, clock, context = analysis_case
    aid, revision = supported(analysis_case, ['memory_gap', 'careless', 'method_gap'])
    with pytest.raises(QuestionRevisionConflict):
        commands(store, clock).preview_adoption(context['ref']['wrong_id'], aid,
            {'selected_causes': ['concept_gap'], 'expected_revision': revision})


def test_changed_input_invalidates_adoption_without_overwriting_manual_note(analysis_case):
    store, clock, context = analysis_case
    aid, revision = supported(analysis_case)
    api, wid = commands(store, clock), context['ref']['wrong_id']
    selection = {'selected_causes': ['concept_gap'], 'expected_revision': revision}
    preview = api.preview_adoption(wid, aid, selection)
    ReviewRepository(store).diagnose(wid, {'expected_revision': revision, 'request_key': 'synthetic-new-diagnosis-0001',
        'error_causes': ['careless'], 'note': '新人工备注'})
    with pytest.raises(QuestionRevisionConflict):
        api.confirm_adoption(wid, aid, selection, preview['confirmation_token'], 'synthetic-stale-adopt-0001', True)
    assert ReviewRepository(store).detail(wid)['error_cause_note'] == '新人工备注'
