# ruff: noqa: F811
"""Synthetic release regressions for backup, stale questions and scoped prerequisites."""

from datetime import timedelta
from uuid import uuid4

import pytest

from filemate.course_graph.learning_evidence import node_learning_evidence
from filemate.course_graph.learning_paths import suggest_path
from filemate.course_graph.models import CourseGraphError
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.course_graph.test_graph_assistant import (  # noqa: F401
    answer,
    assistant_flag,
    service,
)
from filemate.tests.course_graph.test_learning_evidence import NOW
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401


def test_old_backup_does_not_refund_course_budget(learning_context, tmp_path):
    store, *_ = learning_context
    backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    raw = backup.export()
    key = uuid4().hex
    answer(learning_context, request_key=key)
    for _ in range(29):
        answer(learning_context)
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    with pytest.raises(CourseGraphError, match='learning_budget_exceeded'):
        answer(learning_context)
    with pytest.raises(CourseGraphError, match='learning_work_unavailable'):
        answer(learning_context, request_key=key)
    assert store._conn().execute('SELECT COUNT(*) FROM kg_learning_work').fetchone()[0] == 0


def test_changed_question_is_not_scheduled_as_available_practice(learning_context):
    store, cid, _, nid, aid, question = learning_context
    confirm(learning_context)
    store.update_artifact(aid, title='修订', content=[{**question, 'answer': '修订后答案'}])
    result = node_learning_evidence(store, cid, nid, now=NOW)
    assert result['counts']['linked_questions'] == 0
    assert result['question_refs']['items'][0]['link_valid'] is False
    path = suggest_path(store, cid, '复习', concept_ids=[nid], now=NOW)
    assert path['tasks'][0]['kind'] == 'read'


def test_outside_chapter_prerequisite_is_disclosed(learning_context):
    store, cid, _, nid, *_ = learning_context
    from filemate.course_graph.repository import CourseGraphRepository
    repo = CourseGraphRepository(store)
    chapter = str(uuid4())
    repo.put_chapter(cid, chapter, '进阶', None, 0, 0)
    sid = store.save_source(original_name='进阶.txt', source_path='synthetic.txt', raw_text='DFS：深度优先搜索。')
    repo.attach_sources(cid, [sid], chapter, repo.get_course(cid)['revision'])
    with store._conn() as conn:
        dfs = conn.execute("SELECT concept_id FROM kg_concepts WHERE label='DFS'").fetchone()[0]
        conn.execute('UPDATE kg_evidence SET source_id=?,source_revision=?,excerpt=?,char_start=0,char_end=3 WHERE concept_id=?',
                     (sid, store.get_source_revision(sid), 'DFS', dfs))
    path = suggest_path(store, cid, '学习DFS', concept_ids=[dfs], chapter_id=chapter, now=NOW)
    assert [t['concept_id'] for t in path['tasks']] == [dfs]
    assert path['outside_scope_prerequisite_count'] == 1
    assert path['outside_scope_prerequisites'][0]['concept_id'] == nid
    assert path['outside_scope_prerequisites'][0]['relation_ids']


def test_window_expiry_marks_saved_answer_stale(learning_context):
    from filemate.course_graph.learning_work import LearningWorkService
    from filemate.tests.course_graph.test_learning_evidence import attempt
    store, cid, *_ = learning_context
    confirm(learning_context)
    attempt(learning_context, NOW - timedelta(days=7) + timedelta(seconds=1), False)
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET mastered=1')
    work = answer(learning_context)
    later = LearningWorkService(store, lambda: NOW + timedelta(seconds=2))
    assert later.get(cid, work['work_id'])['stale'] is True


def test_training_projection_never_reads_private_answer_bodies(learning_context):
    import sqlite3

    from filemate.course_graph.learning_evidence import read_learning_projection
    from filemate.tests.course_graph.test_learning_evidence import attempt
    store, cid, _, nid, *_ = learning_context
    confirm(learning_context)
    attempt(learning_context, NOW - timedelta(minutes=1), False)
    forbidden = {('quiz_attempts', 'user_answer'), ('quiz_attempts', 'feedback'),
                 ('wrong_questions', 'latest_answer')}
    with store.read_snapshot() as read:
        connection = read._conn()
        connection.set_authorizer(lambda action, table, column, *_:
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and (table, column) in forbidden
            else sqlite3.SQLITE_OK)
        try:
            result = read_learning_projection(read, cid, now=NOW)
        finally:
            connection.set_authorizer(None)
    assert result['nodes'][nid]['counts']['attempts'] == 1
    assert result['nodes'][nid]['status'] == 'needs_reinforcement'
