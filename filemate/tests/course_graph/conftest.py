"""Synthetic isolated course graph fixtures."""

import pytest

from filemate.execution.storage import SQLiteStorage


@pytest.fixture
def course_store(tmp_path):
    store = SQLiteStorage(tmp_path / "courses.sqlite")
    store.init_schema()
    yield store
    store.close()


@pytest.fixture
def course_context(course_store):
    from filemate.course_graph.repository import CourseGraphRepository

    repo = CourseGraphRepository(course_store)
    course = repo.create_course("数据结构", "create_course_0001")
    sid = course_store.save_source(
        original_name="课程.txt", source_path="synthetic-course.txt",
        raw_text="栈：后进先出的线性表。队列：先进先出的线性表。栈是DFS的前置知识。",
    )
    repo.attach_sources(course["course_id"], [sid], None, 0)
    return course_store, repo, course["course_id"], sid
