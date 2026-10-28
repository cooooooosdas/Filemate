"""Synthetic durable analysis lifecycle without any external model calls."""
# ruff: noqa: F811

import importlib
from datetime import timedelta

import pytest

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.tests.wrongbook.conftest import answer_payload, review_store  # noqa: F401
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.repository import ReviewRepository


@pytest.fixture
def analysis_case(review_store, monkeypatch):
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '1')
    store, _, _, _, clock = review_store
    result = ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store))
    context = ReviewLearningContext(store, lambda: clock[0]).build(result['wrong_id'], result['attempt_id'])
    return store, clock, context


def repository(store, clock):
    assert importlib.util.find_spec('filemate.wrongbook.analysis_repository'), '缺少可恢复的分析仓储'
    cls = importlib.import_module('filemate.wrongbook.analysis_repository').ReviewAnalysisRepository
    return cls(store, lambda: clock[0])


def test_two_connections_claim_once_and_cache_replays(analysis_case):
    store, clock, context = analysis_case
    repo = repository(store, clock)
    first, claimed, epoch = repo.claim(context, 'synthetic-analysis-key-0001')
    assert claimed and first['status'] == 'running'
    peer = SQLiteStorage(store.db_path)
    try:
        same, claimed, _ = repository(peer, clock).claim(context, 'synthetic-analysis-key-0001')
        assert same == first and not claimed
        with pytest.raises(QuestionRevisionConflict):
            repo.claim(context, 'synthetic-analysis-key-0001', force_refresh=True)
        with pytest.raises(QuestionRevisionConflict):
            repo.claim(context, 'synthetic-analysis-key-0002', force_refresh=True)
        assert repo.finish(first['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {'usage': None})
        ready = repo.get(context['ref']['wrong_id'], first['analysis_id'])
        assert ready['status'] == 'ready' and ready['result_artifact_id']
        cached, claimed, _ = repo.claim(context, 'synthetic-analysis-key-0003')
        assert not claimed and cached['analysis_id'] == first['analysis_id']
        assert repo.find_request('synthetic-analysis-key-0003')['status'] == 'ready'
        refresh, claimed, _ = repo.claim(context, 'synthetic-analysis-key-0004', force_refresh=True)
        assert claimed and refresh['analysis_id'] != ready['analysis_id']
        assert repo.page(context['ref']['wrong_id'])['total'] == 2
        assert 'result' not in repo.page(context['ref']['wrong_id'])['items'][0]
    finally:
        peer.close()


@pytest.mark.parametrize('action', ['cancel', 'restore', 'source_delete', 'new_answer', 'timeout', 'disabled'])
def test_late_epoch_cannot_publish(analysis_case, review_store, monkeypatch, action):
    store, clock, context = analysis_case
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-late-analysis-0001')
    aid, wid = view['analysis_id'], context['ref']['wrong_id']
    if action == 'cancel':
        assert repo.cancel(wid, aid, 'synthetic-cancel-key-0001')['status'] == 'cancelled'
    elif action == 'restore':
        from filemate.wrongbook.privacy import normalize_restored_wrongbook
        with store._conn() as conn:
            normalize_restored_wrongbook(conn)
        assert repo.get(wid, aid)['status'] == 'interrupted'
    elif action == 'source_delete':
        store.delete_source(review_store[1])
    elif action == 'new_answer':
        ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store, key='synthetic-new-answer-0001'))
    elif action == 'disabled':
        monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '0')
    else:
        clock[0] += timedelta(seconds=21)
    assert not repo.finish(aid, epoch, {'kind': 'insufficient_evidence'}, {})
    assert store._conn().execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='wrong_review_analysis'").fetchone()[0] == 0


def test_get_is_readonly_and_claim_reclaims_expired_lease(analysis_case):
    store, clock, context = analysis_case
    repo = repository(store, clock)
    view, _, _ = repo.claim(context, 'synthetic-lease-key-0001')
    clock[0] += timedelta(seconds=31)
    assert repo.get(context['ref']['wrong_id'], view['analysis_id'])['status'] == 'running'
    assert repo.claim(context, 'synthetic-lease-key-0002', force_refresh=True)[1]
    assert repo.get(context['ref']['wrong_id'], view['analysis_id'])['status'] == 'interrupted'
