"""Real scoped counts and damaged metadata handling; synthetic data only."""

import pytest

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


def test_explicit_scope_orders_offsets_by_real_instant(tmp_path):
    store, scope = runtime().seed(tmp_path, count=3)
    try:
        for i, due in enumerate(('2026-10-31T20:00:00+08:00', '2026-10-31T17:00:00+08:00', '2026-10-31T10:00:00+00:00')):
            store._conn().execute('UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?', (due, f'synthetic-0-{i:06}'))
        store._conn().commit()
        snap = module('snapshot').SnapshotReader(store).read(scope)
        assert [r['wrong_id'] for r in snap.facts['reviews']] == [f'synthetic-0-{i:06}' for i in (1, 2, 0)]
    finally:
        store.close()


def test_scoped_compact_sort_keeps_paging_and_full_counts(tmp_path):
    from filemate.wrongbook.queries import ReviewFilter, ReviewQueries
    store, scope = runtime().seed(tmp_path, count=220)
    try:
        with store.read_snapshot() as read:
            pages = [ReviewQueries(read).page_in_snapshot(read, ReviewFilter(), as_of=module('models').utc_now(),
                     source_ids=tuple(scope.source_ids), limit=100, offset=i) for i in (0, 100, 200)]
        assert [p['total'] for p in pages] == [220, 220, 220]
        assert [p['has_more'] for p in pages] == [True, True, False]
        assert len({r['wrong_id'] for p in pages for r in p['items']}) == 220
    finally:
        store.close()


@pytest.mark.parametrize('json1', [True, False])
def test_date_helpers_never_parse_foreign_scope_dates(world, monkeypatch, json1):
    from filemate.wrongbook import queries
    from filemate.wrongbook.queries import ReviewFilter, ReviewQueries

    from .conftest import wrong
    wid = wrong(world)
    conn = world['store']._conn()
    row = dict(conn.execute('SELECT * FROM wrong_questions WHERE wrong_id=?', (wid,)).fetchone())
    foreign_date = '2088-01-01T00:00:00+00:00'
    row.update(wrong_id='foreign-date-row', source_id=world['sources'][1], question_index=1, next_review_at=foreign_date)
    conn.execute('INSERT INTO wrong_questions (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
    conn.commit()
    seen, original = [], queries.parse_time
    monkeypatch.setattr(queries, 'parse_time', lambda v: (seen.append(v), original(v))[1])
    monkeypatch.setattr(queries, '_has_json1', lambda c: json1)
    with world['store'].read_snapshot() as read:
        for sources in ((world['sources'][0],), ()):
            ReviewQueries(read).page_in_snapshot(read, ReviewFilter(sort='recommended'), as_of=world['now'][0], source_ids=sources)
    assert foreign_date not in seen
