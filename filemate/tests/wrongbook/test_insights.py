"""Evidence-grounded ranking against real filtered SQLite snapshots."""

import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from filemate.tests.wrongbook.test_workspace_reads import many
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries


def details(row, now):
    module = importlib.import_module('filemate.wrongbook.insights')
    return module.priority_details(row, now=now)


def test_priority_uses_shanghai_day_and_annotated_cause():
    now = datetime(2026, 10, 29, 0, 30, tzinfo=timezone.utc)
    result = details({'next_review_at': '2026-10-28T20:00:00Z', 'error_count': 2,
                      'error_cause_source': 'user'}, now)
    assert result['overdue_days'] == 0
    assert result['priority_score'] == 12
    assert '今日到期' in result['reason'] and '2次' in result['reason']
    assert result['rule_version'] == 'review2-priority-v1'
    assert '%' not in result['reason'] and '掌握' not in result['reason']
    capped = details({'next_review_at': '2026-09-20T12:00:00', 'error_count': 100,
                      'error_cause_source': 'model'}, now)
    assert capped['priority_score'] == 130 and capped['overdue_days'] > 30


@pytest.mark.parametrize('due', ['not-a-time', '', None, '0001-01-01T00:00:00+14:00',
                                '2026-10-30T00:00:00Z'])
def test_priority_rejects_invalid_or_future_time(due):
    with pytest.raises(ValueError):
        details({'next_review_at': due, 'error_count': 1},
                datetime(2026, 10, 29, tzinfo=timezone.utc))


@pytest.mark.parametrize('count', [-1, True, '9', 9.5, None])
def test_priority_does_not_invent_bad_counters(count):
    with pytest.raises(ValueError):
        details({'next_review_at': '2026-10-25T00:00:00Z', 'error_count': count},
                datetime(2026, 10, 29, tzinfo=timezone.utc))


def seed_due(fixture, count=1):
    store, _, _, _, clock = fixture
    many(store, count)
    return store, ReviewQueries(store, clock=lambda: clock[0])


def test_recommendation_sorts_all_candidates_before_paging(review_store):
    store, read = seed_due(review_store, 65)
    first = read.page(ReviewFilter(), limit=30)
    target = read.page(ReviewFilter(), offset=60)['items'][-1]
    assert target['wrong_id'] not in {item['wrong_id'] for item in first['items']}
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET error_count=10,error_cause_source='user' WHERE wrong_id=?",
                     (target['wrong_id'],))
    recommended = read.page(ReviewFilter(sort='recommended'), limit=7)
    assert recommended['total'] == 65
    assert recommended['items'][0]['wrong_id'] == target['wrong_id']
    assert recommended['priority_rule_version'] == 'review2-priority-v1'
    assert recommended['recommendation_scope'] == 'filtered_eligible_due'
    assert read.page(ReviewFilter(), limit=30)['items'][0]['wrong_id'] == first['items'][0]['wrong_id']
    assert [i['wrong_id'] for i in read.page(ReviewFilter(sort='recommended', direction='desc'), limit=7)['items']] == [i['wrong_id'] for i in recommended['items']]
    rest = read.page(ReviewFilter(sort='recommended'), limit=100, offset=7)
    all_items = recommended['items'] + rest['items']
    assert len({i['wrong_id'] for i in all_items}) == 65
    scores = [i['priority']['priority_score'] for i in all_items]
    assert scores == sorted(scores, reverse=True)
    assert [i['wrong_id'] for i in all_items[1:]] == sorted(i['wrong_id'] for i in all_items[1:])
    last = read.page(ReviewFilter(sort='recommended', q=target['stem']))
    assert last['total'] == 1
    for item in all_items:
        assert item['priority'] == details(item, review_store[-1][0])
        assert not {'answer', 'latest_answer', 'question', 'analysis'} & item.keys()


@pytest.mark.parametrize('change', [
    {'schedule_status': 'paused'}, {'mastered': 1},
    {'next_review_at': '2999-01-01T00:00:00Z'}, {'next_review_at': 'invalid'},
    {'next_review_at': '0001-01-01T00:00:00+14:00'},
    {'question': '[]'}, {'error_causes': 'not-json'}, {'error_count': -1},
])
def test_recommendation_excludes_unreviewable_records(review_store, change):
    store, read = seed_due(review_store)
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET ' + ','.join(f'{key}=?' for key in change),
                     list(change.values()))
    assert read.page(ReviewFilter(sort='recommended'))['total'] == 0


def test_history_excluded_but_due_v2_criterion_met_included(review_store):
    store, read = seed_due(review_store)
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET mastered=1,scheduler_version='review-interval-v2',learning_status='criterion_met'")
    assert read.page(ReviewFilter(sort='recommended'))['total'] == 1
    assert read.page(ReviewFilter(sort='recommended', status='paused'))['total'] == 0
    assert read.page(ReviewFilter(sort='recommended', source_id='another-workspace-source'))['total'] == 0
    with store._conn() as conn:
        conn.execute('UPDATE artifacts SET metadata=?', (json.dumps({'read_only_snapshot': True}),))
    assert read.page(ReviewFilter(sort='recommended'))['total'] == 0


def test_ranking_uses_one_server_clock_and_keeps_naive_utc(review_store):
    store, _ = seed_due(review_store)
    times = [datetime(2026, 10, 29, 0, 30, tzinfo=timezone.utc),
             datetime(2026, 10, 30, 0, 30, tzinfo=timezone.utc)]
    clock_calls = []

    def clock():
        clock_calls.append(True)
        return times[min(len(clock_calls) - 1, 1)]

    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='2026-10-28T20:00:00'")
    page = ReviewQueries(store, clock=clock).page(ReviewFilter(sort='recommended'))
    assert len(clock_calls) == 1
    assert page['as_of'] == times[0].isoformat()
    assert page['items'][0]['priority']['overdue_days'] == 0
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='2026-10-29T16:00:00'")
    assert ReviewQueries(store, clock=lambda: times[0]).page(ReviewFilter(sort='recommended'))['total'] == 0


def test_recommendation_search_works_without_json1(review_store, monkeypatch):
    _store, read = seed_due(review_store, 65)
    module = importlib.import_module('filemate.wrongbook.queries')
    monkeypatch.setattr(module, '_has_json1', lambda conn: False)
    page = read.page(ReviewFilter(sort='recommended', q='知识点00064'))
    assert page['total'] == 1 and page['items'][0]['question_index'] == 64


@pytest.mark.parametrize('question,causes,tags,metadata,expected', [
    ('{"stem":"有效题目"}', '[]', '[]', '{}', 1),
    (' { } ', '[]', '[]', '{}', 0), ('[]', '[]', '[]', '{}', 0),
    ('broken', '[]', '[]', '{}', 0), ('{"stem":"有效题目"}', 'null', '[]', '{}', 0),
    ('{"stem":"有效题目"}', '[]', 'null', '{}', 0),
    ('{"stem":"有效题目"}', '[]', '[]', '{"read_only_snapshot":true}', 0),
    ('{"stem":"有效题目"}', '[]', '[]', '{"read_only_snapshot":"false"}', 0),
    ('{"stem":"有效题目"}', '[]', '[]', '{"read_only_snapshot":[]}', 1),
    ('{"stem":"有效题目","invalid":NaN}', '[]', '[]', '{}', 0),
    ('{"stem":"有效题目"}', '[]', '[]', 'broken', 0),
    ('{"stem":"有效题目"}', '[]', '[]', '[]', 0),
    ('{"stem":"有效题目"}', '[]', '[]', 'null', 0),
])
def test_json1_and_legacy_validation_agree(review_store, monkeypatch, question, causes, tags, metadata, expected):
    store, read = seed_due(review_store)
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET question=?,error_causes=?,custom_tags=?', (question, causes, tags))
        conn.execute('UPDATE artifacts SET metadata=?', (metadata,))
    module = importlib.import_module('filemate.wrongbook.queries')
    for available in (True, False):
        monkeypatch.setattr(module, '_has_json1', lambda conn, available=available: available)
        assert read.page(ReviewFilter(sort='recommended'))['total'] == expected


def test_distinct_offsets_and_timestamps_follow_the_explained_order(review_store):
    from filemate.wrongbook.engine import parse_time

    store, read = seed_due(review_store, 65)
    with store._conn() as conn:
        for index, row in enumerate(conn.execute('SELECT wrong_id FROM wrong_questions').fetchall()):
            instant = review_store[-1][0] - timedelta(hours=index * 13 + 1)
            value = instant.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat() if index % 2 else instant.replace(tzinfo=None).isoformat()
            conn.execute('UPDATE wrong_questions SET next_review_at=?,error_count=?,error_cause_source=? WHERE wrong_id=?',
                         (value, index % 15, 'user' if index % 5 == 0 else 'model', row['wrong_id']))
    original = [dict(row) for row in store._conn().execute('SELECT * FROM wrong_questions')]
    expected = sorted(original, key=lambda row: (-details(row, review_store[-1][0])['priority_score'],
                                               parse_time(row['next_review_at']), row['wrong_id']))
    actual = read.page(ReviewFilter(sort='recommended'), limit=100)['items']
    assert [row['wrong_id'] for row in actual] == [row['wrong_id'] for row in expected]
