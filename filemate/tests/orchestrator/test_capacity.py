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
