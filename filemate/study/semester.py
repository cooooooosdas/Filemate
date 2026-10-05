"""基于用户课程与日期生成可确认、可追踪的学期计划。"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from filemate.execution import data_actions
from filemate.execution.storage import SQLiteStorage, _now_iso

SEMESTER_ID = 'personal-semester-v1'


class Course(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    course_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=1000)
    weekly_minutes: int = Field(default=90, ge=10, le=600, strict=True)
    weekday: int = Field(default=6, ge=0, le=6, strict=True)
    source_id: str | None = Field(default=None, max_length=80)
    exam_date: date | None = None


class SemesterConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0, strict=True)
    title: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    courses: list[Course] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def valid_dates(self):
        if not 0 <= (self.end_date - self.start_date).days <= 365:
            raise ValueError('学期结束须在开始后的366天以内')
        if len({course.course_id for course in self.courses}) != len(self.courses):
            raise ValueError('课程标识重复')
        if any(course.exam_date and not self.start_date <= course.exam_date <= self.end_date for course in self.courses):
            raise ValueError('考试日期须在本学期内')
        return self


class ConfirmSemester(BaseModel):
    model_config = ConfigDict(extra='forbid')
    config: SemesterConfig
    confirmed: Literal[True]
    confirmation_token: str = Field(min_length=64, max_length=64)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=1)
    completed: bool


class SemesterRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    @staticmethod
    def tasks(config: SemesterConfig) -> list[dict[str, Any]]:
        result = []
        weeks = (config.end_date - config.start_date).days // 7 + 1
        for course in config.courses:
            offset = (course.weekday - config.start_date.weekday()) % 7
            for week in range(weeks):
                due = min(config.end_date, config.start_date + timedelta(days=week * 7 + offset))
                result.append({'task_id': f'{course.course_id}-week-{week + 1}', 'course_id': course.course_id,
                               'kind': 'weekly', 'week': week + 1, 'title': course.objective,
                               'due_date': due.isoformat(), 'minutes': course.weekly_minutes,
                               'completed': False, 'completed_at': None})
            if course.exam_date:
                result.append({'task_id': course.course_id + '-exam', 'course_id': course.course_id, 'kind': 'exam',
                               'week': (course.exam_date - config.start_date).days // 7 + 1,
                               'title': '考试：' + course.title, 'due_date': course.exam_date.isoformat(),
                               'minutes': 0, 'completed': False, 'completed_at': None})
        return sorted(result, key=lambda item: (item['due_date'], item['task_id']))

    def read(self) -> dict[str, Any] | None:
        artifact = self.storage.get_artifact(SEMESTER_ID)
        if not artifact:
            return None
        if artifact['artifact_type'] != 'semester':
            raise ValueError('学期类型异常，原内容保留')
        content = artifact['content']
        config = SemesterConfig.model_validate(content['config'])
        expected = {task['task_id']: task for task in self.tasks(config)}
        if not isinstance(content['tasks'], list) or len(content['tasks']) != len(expected):
            raise ValueError('学期任务不完整，原内容保留')
        observed = set()
        for task in content['tasks']:
            base = expected.get(task.get('task_id'))
            if (base is None or task['task_id'] in observed or any(task.get(key) != value for key, value in base.items() if key not in {'completed', 'completed_at'})
                    or type(task.get('completed')) is not bool
                    or (task['completed'] and not isinstance(task.get('completed_at'), str))):
                raise ValueError('学期任务数据异常，原内容保留')
            observed.add(task['task_id'])
        return content

    def _revision(self, config: SemesterConfig) -> str:
        return data_actions.digest({'current': self.read(), 'proposed': config.model_dump(mode='json'),
                                    'sources': [self.storage.get_source(course.source_id) is not None for course in config.courses if course.source_id]})

    def preview(self, config: SemesterConfig) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = self.read()
            if (current['config']['revision'] if current else 0) != config.revision:
                raise ValueError('学期已更新，请刷新后重新编排')
            if any(course.source_id and self.storage.get_source(course.source_id) is None for course in config.courses):
                raise ValueError('关联资料不存在，请在当前空间重新选择')
            tasks = self.tasks(config)
            return {'task_count': len(tasks), 'week_count': (config.end_date - config.start_date).days // 7 + 1,
                    'previous_completed': sum(task['completed'] for task in current['tasks']) if current else 0,
                    'weekly_minutes': sum(course.weekly_minutes for course in config.courses),
                    'confirmation_token': data_actions.issue(conn, 'semester_replace', SEMESTER_ID, self._revision(config)),
                    'notice': '新编排从未完成开始；旧课程及进度将保留为历史版本，不推断成绩或掌握度。'}

    def confirm(self, request: ConfirmSemester) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            receipt = data_actions.check(conn, 'semester_replace', SEMESTER_ID, request.confirmation_token, self._revision(request.config))
            if receipt:
                return receipt
            current = self.read()
            config = request.config.model_copy(update={'revision': request.config.revision + 1})
            content = {'config': config.model_dump(mode='json'), 'tasks': self.tasks(config), 'created_at': _now_iso()}
            if current:
                conn.execute("INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) VALUES(?,'semester_history',?,?,?)",
                             ('semester-' + uuid.uuid4().hex, current['config']['title'], json.dumps(current, ensure_ascii=False), '{"schema_version":1,"origin":"semester"}'))
                conn.execute('UPDATE artifacts SET title=?,content=?,updated_at=? WHERE artifact_id=?', (config.title, json.dumps(content, ensure_ascii=False), _now_iso(), SEMESTER_ID))
            else:
                conn.execute("INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) VALUES(?,'semester',?,?,?)", (SEMESTER_ID, config.title, json.dumps(content, ensure_ascii=False), '{"schema_version":1,"origin":"semester"}'))
            receipt = {'revision': config.revision, 'task_count': len(content['tasks'])}
            data_actions.finish(conn, 'semester_replace', SEMESTER_ID, request.confirmation_token, receipt)
            return receipt

    def update(self, identifier: str, request: TaskUpdate) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            content = self.read()
            if not content:
                raise KeyError(identifier)
            if content['config']['revision'] != request.revision:
                raise ValueError('学期任务已更新，请刷新')
            task = next((task for task in content['tasks'] if task['task_id'] == identifier), None)
            if not task:
                raise KeyError(identifier)
            if task['completed'] != request.completed:
                task.update(completed=request.completed, completed_at=_now_iso() if request.completed else None)
                content['config']['revision'] += 1
                conn.execute('UPDATE artifacts SET content=?,updated_at=? WHERE artifact_id=?', (json.dumps(content, ensure_ascii=False), _now_iso(), SEMESTER_ID))
                conn.execute('INSERT INTO data_action_audit(action,resource_id,affected) VALUES(?,?,?)', ('semester_task_complete' if request.completed else 'semester_task_reopen', identifier, '{"tasks":1}'))
            return content
