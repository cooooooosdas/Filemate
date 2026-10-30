"""Preserve read contracts while removing timestamp callback contention."""

import importlib
import sqlite3
from contextlib import contextmanager
from datetime import timedelta

import pytest

from filemate.tests.wrongbook.test_workspace_reads import many
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries
from filemate.wrongbook.session_preview import ReviewSessions


@pytest.fixture(params=[False, True], ids=['json1', 'no-json1'])
def date_reader(review_store, request, monkeypatch):
    if request.param:
        module = importlib.import_module('filemate.wrongbook.queries')
        monkeypatch.setattr(module, '_has_json1', lambda _conn: False)
    store, *_, clock = review_store
    return store, ReviewQueries(store, clock=lambda: clock[0]), clock


@pytest.mark.parametrize('separator', ['T', ' ', "'", '"', '\x00', '\u2028', '\U00010400'])
def test_exact_legacy_time_bytes_survive_native_relation(date_reader, separator):
    store, query, _clock = date_reader
    many(store, 1)
    raw = f'2026-10-25{separator}23:59:59.123456+03:30'
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET next_review_at=?', (raw,))
    page = query.page(ReviewFilter(sort='recommended'))
    assert page['total'] == 1
    row = page['items'][0]
    assert row['next_review_at'] == raw and row['data_error'] is False
    assert row['priority']['overdue_days'] == 0
    assert row['priority']['priority_score'] == 4


def test_many_distinct_times_work_with_legacy_bind_limit(date_reader, monkeypatch):
    store, query, clock = date_reader
    many(store, 1100)
    now = clock[0]
    rows = store._conn().execute('SELECT wrong_id,question_index FROM wrong_questions').fetchall()
    with store._conn() as conn:
        conn.executemany('UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?',
            [((now - timedelta(days=1) + timedelta(microseconds=row['question_index'])).isoformat(),
              row['wrong_id']) for row in rows])
    original_snapshot = store.read_snapshot

    @contextmanager
    def limited_snapshot():
        with original_snapshot() as read:
            conn = read._conn()
            assert conn.execute('PRAGMA query_only').fetchone()[0] == 1
            if hasattr(conn, 'setlimit'):
                conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
            yield read

    monkeypatch.setattr(store, 'read_snapshot', limited_snapshot)
    page = query.page(ReviewFilter(sort='recommended'), offset=1099)
    assert page['total'] == 1100 and len(page['items']) == 1
    assert page['items'][0]['question_index'] == 1099
    assert page['items'][0]['priority']['overdue_days'] == 1
    assert page['has_more'] is False


@pytest.mark.parametrize('corrupt', [None, 'text', 'blob'], ids=['empty', 'invalid-dates', 'blob-dates'])
def test_empty_date_relation_is_read_only_and_has_no_candidates(date_reader, corrupt):
    store, query, clock = date_reader
    if corrupt:
        many(store, 2)
        with store._conn() as conn:
            conn.execute('UPDATE wrong_questions SET next_review_at=?',
                         (b'not-a-time' if corrupt == 'blob' else "2026-10-25'); DROP TABLE sources;--",))
    before = tuple(store._conn().iterdump())
    assert query.page(ReviewFilter(sort='recommended'))['total'] == 0
    preview = ReviewSessions(store, clock=lambda: clock[0]).preview(ReviewFilter(), available_minutes=12)
    assert preview['eligible_count'] == preview['selected_count'] == 0
    assert tuple(store._conn().iterdump()) == before


@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_default_due_preserves_invalid_rows_and_null_tie_order(date_reader, direction):
    store, query, clock = date_reader
    many(store, 5)
    rows = store._conn().execute('SELECT wrong_id,question_index FROM wrong_questions ORDER BY question_index').fetchall()
    times = ['', b'not-a-time', 'invalid', (clock[0] - timedelta(days=1)).isoformat(),
             (clock[0] + timedelta(days=1)).isoformat()]
    with store._conn() as conn:
        conn.executemany('UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?',
                         [(raw, row['wrong_id']) for raw, row in zip(times, rows, strict=True)])
    invalid = sorted(row['wrong_id'] for row in rows[:3])
    expected = invalid + [rows[3]['wrong_id'], rows[4]['wrong_id']]
    if direction == 'desc':
        expected.reverse()
    page = query.page(ReviewFilter(direction=direction))
    assert page['total'] == 5 and [row['wrong_id'] for row in page['items']] == expected
    assert sum(row['data_error'] for row in page['items']) == 3


def test_time_conversion_stays_inside_the_current_read_snapshot(date_reader):
    store, query, clock = date_reader
    many(store, 1)
    with store.read_snapshot() as read:
        original = dict(read._conn().execute('SELECT * FROM wrong_questions').fetchone())
        with store._conn() as writer:
            writer.execute('UPDATE wrong_questions SET next_review_at=?,revision=revision+1',
                           ((clock[0] + timedelta(days=2)).isoformat(),))
        page = query._snapshot_page(read, ReviewFilter(sort='recommended'), as_of=clock[0])
        assert page['total'] == 1
        assert page['items'][0]['revision'] == original['revision']
        assert page['items'][0]['next_review_at'] == original['next_review_at']
    assert query.page(ReviewFilter(sort='recommended'))['total'] == 0


def test_blob_date_never_inherits_the_time_of_identical_text_bytes(date_reader):
    store, query, _clock = date_reader
    many(store, 2)
    raw = '2026-10-25T00:00:00+00:00'
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET next_review_at=? WHERE question_index=0', (raw,))
        conn.execute('UPDATE wrong_questions SET next_review_at=? WHERE question_index=1',
                     (sqlite3.Binary(raw.encode('utf-8')),))
    page = query.page(ReviewFilter(sort='recommended'))
    assert page['total'] == 1 and page['items'][0]['question_index'] == 0
    ordinary = query.page(ReviewFilter())
    assert ordinary['total'] == 2
    assert ordinary['items'][0]['question_index'] == 1
    assert ordinary['items'][0]['data_error'] is True
