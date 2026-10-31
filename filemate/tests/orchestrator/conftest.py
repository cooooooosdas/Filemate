"""Original synthetic evidence; no real account or model access."""

import importlib.util
from datetime import datetime, timezone

import pytest

from filemate.course_graph.repository import CourseGraphRepository
from filemate.execution.storage import SQLiteStorage


def module(name):
    assert importlib.util.find_spec('filemate.study.orchestrator'), 'Learning decision layer is not implemented'
    return __import__('filemate.study.orchestrator.' + name, fromlist=['*'])


@pytest.fixture
def world(tmp_path):
    store = SQLiteStorage(tmp_path / 'synthetic.db')
    store.init_schema()
    sources = [store.save_source(original_name=n, source_path='synthetic.txt') for n in ('数据结构', '线性代数')]
    courses = CourseGraphRepository(store)
    ids = []
    for i, sid in enumerate(sources):
        course = courses.create_course(('数据结构', '线性代数')[i], f'synthetic-course-{i:04}')
        courses.attach_sources(course['course_id'], [sid], None, course['revision'])
        ids.append(course['course_id'])
    goal = store.save_artifact(artifact_type='reverse_goal_plan', source_id=sources[0], content={
        'title': '复习栈与队列', 'goal_type': 'exam', 'deadline': '2026-11-05',
        'tasks': [{'task_id': 'review-source', 'title': '读懂资料', 'status': 'pending', 'due_date': '2026-11-01'}],
    })
    question = {'question_type': 'choice', 'stem': 'synthetic-secret-question', 'options': ['后进先出', '先进先出'], 'answer': 'A'}
    aid = store.save_artifact(artifact_type='questions', source_id=sources[0], content=[question])
    now = [datetime(2026, 10, 31, 8, tzinfo=timezone.utc)]
    yield {'store': store, 'sources': sources, 'courses': ids, 'goal': goal, 'artifact': aid, 'question': question, 'now': now}
    store.close()


def scope(world, **extra):
    return module('models').ScopeRequest(goal_id=world['goal'], course_id=world['courses'][0], source_ids=[world['sources'][0]], **extra)


def snapshot(world):
    return module('snapshot').SnapshotReader(world['store'], clock=lambda: world['now'][0]).read(scope(world))


def wrong(world):
    world['store'].record_quiz_attempt(artifact_id=world['artifact'], question_index=0, user_answer='B', is_correct=False, score=0, feedback='合成错答')
    return world['store']._conn().execute('SELECT wrong_id FROM wrong_questions WHERE artifact_id=?', (world['artifact'],)).fetchone()[0]
