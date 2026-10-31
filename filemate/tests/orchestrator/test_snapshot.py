"""Scope and consistent-read regressions over real SQLite."""

import json
from datetime import timedelta

import pytest

from .conftest import module, scope, snapshot, wrong


def test_scope_never_reads_other_course(world):
    store = world['store']
    store.save_artifact(artifact_type='reverse_goal_plan', source_id=world['sources'][1], content={'tasks': [{'task_id': 'foreign', 'title': 'foreign-secret'}]})
    wrong(world)
    before = store._conn().total_changes
    result = snapshot(world)
    text = result.model_dump_json()
    assert 'foreign-secret' not in text and 'synthetic-secret-question' not in text and 'user_answer' not in text
    assert len(result.facts['reviews']) == 1
    assert store._conn().total_changes == before
    world['now'][0] += timedelta(seconds=20)
    assert snapshot(world).evidence_revision == result.evidence_revision


def test_goal_without_scope_has_no_global_evidence(world):
    goal = world['store'].save_artifact(artifact_type='reverse_goal_plan', content={'tasks': []})
    result = module('snapshot').SnapshotReader(world['store']).read(module('models').ScopeRequest(goal_id=goal))
    assert result.coverage['needs_scope'] is True
    assert result.facts['reviews'] == [] and result.facts['plans'] == []


def test_scope_membership_and_foreign_ids(world):
    models = module('models')
    reader = module('snapshot').SnapshotReader(world['store'])
    for values in [{'goal_id': 'unknown'}, {'goal_id': world['goal'], 'course_id': world['courses'][1], 'source_ids': [world['sources'][0]]}, {'goal_id': world['goal'], 'source_ids': [world['sources'][1]]}]:
        with pytest.raises(models.OrchestratorError):
            reader.read(models.ScopeRequest(**values))


def test_writer_between_tables_cannot_mix_snapshots(world):
    store = world['store']
    from filemate.execution.storage import SQLiteStorage
    other = SQLiteStorage(store.db_path)
    try:
        reader = module('snapshot').SnapshotReader(store, clock=lambda: world['now'][0])
        with store.read_snapshot() as read:
            first = reader.read_in_transaction(read, scope(world), as_of=world['now'][0])
            other._conn().execute('UPDATE sources SET updated_at=? WHERE source_id=?', ('2026-11-01', world['sources'][0]))
            other._conn().commit()
            second = reader.read_in_transaction(read, scope(world), as_of=world['now'][0])
            assert first.evidence_revision == second.evidence_revision
        assert reader.read(scope(world)).evidence_revision != first.evidence_revision
    finally:
        other.close()


def test_scoped_due_after_global_first_hundred_is_not_hidden(world):
    wid = wrong(world)
    conn = world['store']._conn()
    row = dict(conn.execute('SELECT * FROM wrong_questions WHERE wrong_id=?', (wid,)).fetchone())
    for i in range(120):
        clone = row | {'wrong_id': f'foreign-{i:04}', 'source_id': world['sources'][1], 'question_index': i + 1}
        conn.execute('INSERT INTO wrong_questions (' + ','.join(clone) + ') VALUES (' + ','.join('?' for _ in clone) + ')', tuple(clone.values()))
    conn.commit()
    result = snapshot(world)
    assert [r['wrong_id'] for r in result.facts['reviews']] == [wid]
    assert result.coverage['reviews']['total'] == 1
    assert json.loads(result.model_dump_json())['coverage']['reviews']['truncated'] is False


def test_verified_attempt_refs_without_answers(world):
    wrong(world)
    result = snapshot(world)
    assert result.coverage['attempts']['total'] == 1
    assert len(result.facts['attempts']) == 1
    assert 'attempt_id' in result.facts['attempts'][0]
    assert result.coverage['graph']['total'] == 0


def test_only_explicit_goal_interviews_without_model_scores(world):
    store = world['store']
    own = None
    for gid in (world['goal'], 'foreign-goal'):
        run = store.create_agent_run(task_type='interview', goal='原创合成面试', selected_agents=[],
                                     context_refs={'goal_id': gid, 'source_id': world['sources'][0]})
        session = store.create_interview(target_role='学生训练', scenario='technical', difficulty='easy',
                                         questions=['原创问题'], agent_run_id=run['run_id'])
        if gid == world['goal']:
            own = session['interview_id']
    result = snapshot(world)
    assert [i['interview_id'] for i in result.facts['interviews']] == [own]
    assert 'score' not in json.dumps(result.facts['interviews'])
    assert result.coverage['interviews']['returned'] == 1


def test_shared_source_requires_explicit_course_and_reports_source_basis(world):
    from filemate.course_graph.repository import CourseGraphRepository
    repo = CourseGraphRepository(world['store'])
    revision = world['store']._conn().execute('SELECT revision FROM kg_courses WHERE course_id=?', (world['courses'][1],)).fetchone()[0]
    repo.attach_sources(world['courses'][1], [world['sources'][0]], None, revision)
    reader = module('snapshot').SnapshotReader(world['store'], clock=lambda: world['now'][0])
    with pytest.raises(module('models').OrchestratorError, match='explicit_course_required'):
        reader.read(module('models').ScopeRequest(goal_id=world['goal']))
    result = reader.read(scope(world))
    assert result.coverage['shared_source_ids'] == [world['sources'][0]]
    assert result.coverage['practice_scope_basis'] == 'source_records_not_course_mastery'
