"""Real scoped counts and damaged metadata handling; synthetic data only."""

from .conftest import module, snapshot, wrong
from .test_runtime import runtime


def test_large_scope_reports_counts_without_cross_scope_fallback(tmp_path):
    result = runtime().seed(tmp_path, count=1000)
    store, scope = result
    try:
        snap = module('snapshot').SnapshotReader(store).read(scope)
        assert snap.coverage['reviews'] == {'total': 1000, 'returned': 100, 'truncated': True}
        assert all(row['source_id'] == scope.source_ids[0] for row in snap.facts['reviews'])
    finally:
        store.close()


def test_no_json1_and_malformed_records(world, monkeypatch):
    wid = wrong(world)
    from filemate.wrongbook import queries
    monkeypatch.setattr(queries, '_has_json1', lambda conn: False)
    conn = world['store']._conn()
    conn.execute('UPDATE wrong_questions SET question=? WHERE wrong_id=?', ('{broken', wid)); conn.commit()
    snap = snapshot(world)
    assert snap.facts['reviews'][0]['data_error']
    assert module('task_views').project_tasks(snap).unavailable[0]['reason'] == 'invalid_or_historical_evidence'


def test_due_review_is_not_hidden_by_a_hundred_future_reviews(tmp_path):
    store, scope = runtime().seed(tmp_path, count=101)
    try:
        conn = store._conn()
        target = conn.execute('SELECT wrong_id FROM wrong_questions WHERE source_id=? ORDER BY wrong_id DESC LIMIT 1', scope.source_ids).fetchone()[0]
        conn.execute('UPDATE wrong_questions SET error_count=100,next_review_at=? WHERE source_id=?', ('2099-01-01T00:00:00+00:00', scope.source_ids[0]))
        conn.execute('UPDATE wrong_questions SET error_count=1,next_review_at=? WHERE wrong_id=?', ('2020-01-01T00:00:00+00:00', target))
        conn.commit()
        snap = module('snapshot').SnapshotReader(store).read(scope)
        assert target in {r['wrong_id'] for r in snap.facts['reviews']}
    finally:
        store.close()
