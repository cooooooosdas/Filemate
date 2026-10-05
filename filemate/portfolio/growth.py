"""按明确时间窗口汇总有效记录，保存可追溯的成长报告快照。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from filemate.execution.storage import SQLiteStorage
from filemate.study.evidence_profile import _number, _time
from filemate.study.knowledge_graph import _after_question_revision
from filemate.study.question_validation import validate_question

REPORT_ZONE = timezone(timedelta(hours=8))


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_date: date
    end_date: date
    time_zone: Literal['Asia/Shanghai'] = 'Asia/Shanghai'

    @model_validator(mode='after')
    def valid_period(self):
        if not 0 <= (self.end_date - self.start_date).days <= 365 or self.end_date > datetime.now(REPORT_ZONE).date():
            raise ValueError('报告期间须为最多366天，结束日期不得在未来')
        return self


class GrowthRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def generate(self, request: ReportRequest) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        begin = datetime.combine(request.start_date, datetime.min.time(), REPORT_ZONE)
        end = datetime.combine(request.end_date + timedelta(days=1), datetime.min.time(), REPORT_ZONE)
        records: list[dict[str, Any]] = []
        excluded = {'quiz': 0, 'coding': 0, 'interview': 0, 'semester': 0}

        def in_period(value: Any) -> datetime | None:
            moment = _time(value, now)
            return moment if moment and begin <= moment < end else None

        with self.storage.read_snapshot() as snapshot:
            conn = snapshot._conn()
            artifacts = {}
            for row in conn.execute('SELECT rowid AS evidence_sequence,* FROM quiz_attempts ORDER BY created_at,rowid'):
                attempt = dict(row)
                if not in_period(attempt['created_at']):
                    continue
                aid = attempt['artifact_id']
                if aid not in artifacts:
                    artifacts[aid] = snapshot.get_artifact(aid)
                artifact = artifacts[aid]
                try:
                    if not artifact or artifact['artifact_type'] != 'questions':
                        raise ValueError('invalid question artifact')
                    if type(attempt['question_index']) is not int or attempt['question_index'] < 0:
                        raise ValueError('invalid question index')
                    question = artifact['content'][attempt['question_index']]
                    validate_question(question, legacy=True)
                    if (type(attempt['is_correct']) is not int or attempt['is_correct'] not in (0, 1)
                            or _number(attempt['score'], 1) != attempt['is_correct'] or not _after_question_revision(attempt, artifact)):
                        raise ValueError('unusable attempt')
                except (ValueError, KeyError, TypeError, IndexError):
                    excluded['quiz'] += 1
                    continue
                records.append({'kind': 'quiz', 'record_id': attempt['attempt_id'], 'created_at': attempt['created_at'],
                                'value': attempt['is_correct'], 'label': '课程练习作答', 'href': '/ai-tools?artifact=' + aid})
            from filemate.programming.repository import CodingRepository
            coding = CodingRepository(snapshot)
            for row in conn.execute("SELECT c.submission_id,MAX(e.created_at) AS completed_at FROM coding_submissions c JOIN coding_events e USING(submission_id) WHERE e.action='completed' AND c.status='completed' GROUP BY c.submission_id"):
                if not in_period(row['completed_at']):
                    continue
                try:
                    submission = coding.get(row['submission_id'])
                    verdict = submission['result'].get('verdict')
                    if submission['data_error'] or not submission['active'] or verdict not in {'AC', 'WA', 'CE', 'RE', 'TLE', 'MLE', 'OLE'}:
                        raise ValueError('unusable compiler result')
                except (ValueError, KeyError, TypeError):
                    excluded['coding'] += 1
                    continue
                records.append({'kind': 'coding', 'record_id': row['submission_id'], 'created_at': row['completed_at'],
                                'value': verdict, 'label': submission['problem_id'], 'href': '/programming?submission=' + row['submission_id']})
            for row in conn.execute('SELECT interview_id FROM interview_sessions'):
                try:
                    interview = snapshot.get_interview(row['interview_id'])
                    turns = interview['turns']
                except (ValueError, TypeError, KeyError, AttributeError, IndexError):
                    excluded['interview'] += 1
                    continue
                for turn in turns:
                    if not in_period(turn['created_at']) or not str(turn.get('answer', '')).strip():
                        continue
                    score = _number(turn.get('score'), 100) if turn.get('scoring_mode') == 'llm' and turn.get('content_analysis') and not turn.get('analysis_data_error') else None
                    records.append({'kind': 'interview', 'record_id': turn['turn_id'], 'created_at': turn['created_at'],
                                    'value': score, 'label': '模拟面试回答', 'href': '/interview?interview=' + row['interview_id']})
            from filemate.study.semester import SemesterRepository
            try:
                semester = SemesterRepository(snapshot).read()
            except (ValueError, KeyError, TypeError):
                semester = None
                excluded['semester'] += 1
            if semester:
                for task in semester['tasks']:
                    if task['completed'] and in_period(task.get('completed_at')):
                        records.append({'kind': 'semester', 'record_id': task['task_id'], 'created_at': task['completed_at'],
                                        'value': 1, 'label': task['title'], 'href': '/semester'})
            # 旧学习计划没有逐日完成时间，仅报告当前快照，避免伪造期间内完成事件。
            plan_snapshot = {'days': 0, 'completed_days': 0, 'excluded_plans': 0}
            for row in conn.execute("SELECT plan_data,completed_days FROM study_plans WHERE status!='archived'"):
                try:
                    days = json.loads(row['plan_data'])['daily_plan']
                    done = json.loads(row['completed_days'])
                    if (not isinstance(days, list) or not isinstance(done, list) or any(type(index) is not int or not 0 <= index < len(days) for index in done)
                            or len(set(done)) != len(done)):
                        raise ValueError('invalid plan')
                    plan_snapshot['days'] += len(days)
                    plan_snapshot['completed_days'] += len(done)
                except (ValueError, KeyError, TypeError):
                    plan_snapshot['excluded_plans'] += 1
        kinds = {key: [record for record in records if record['kind'] == key] for key in excluded}
        quiz = kinds['quiz']; compiled = kinds['coding']; interviews = kinds['interview']
        scored = [record['value'] for record in interviews if record['value'] is not None]
        metrics = {'quiz_attempts': len(quiz), 'quiz_correct': sum(row['value'] for row in quiz),
                   'quiz_accuracy': round(sum(row['value'] for row in quiz) / len(quiz) * 100, 2) if len(quiz) >= 5 else None,
                   'compiler_submissions': len(compiled), 'compiler_accepted': sum(row['value'] == 'AC' for row in compiled),
                   'compiler_verdicts': {verdict: sum(row['value'] == verdict for row in compiled) for verdict in sorted({row['value'] for row in compiled})},
                   'interview_answers': len(interviews), 'interview_scored_answers': len(scored),
                   'interview_model_score': round(sum(scored) / len(scored), 2) if len(scored) >= 5 else None,
                   'semester_completed_tasks': len(kinds['semester'])}
        recommendations = []
        if metrics['quiz_attempts'] > metrics['quiz_correct']:
            recommendations.append({'text': '期间存在错误作答，回看错题原文并复练。', 'href': '/wrongbook'})
        if metrics['compiler_submissions'] > metrics['compiler_accepted']:
            recommendations.append({'text': '期间存在未通过提交，查看编译器的实际失败用例。', 'href': '/programming'})
        if not records:
            recommendations.append({'text': '此期间没有有效活动记录，完成实际练习后再评测。', 'href': '/today'})
        content = {'schema_version': 1, 'period': request.model_dump(mode='json'), 'data_as_of': now.isoformat(),
                   'status': 'recorded' if records else 'pending_assessment', 'metrics': metrics, 'plan_snapshot': plan_snapshot,
                   'excluded_records': excluded, 'recommendations': recommendations,
                   'records': sorted(records, key=lambda row: (row['created_at'], row['record_id']), reverse=True),
                   'notice': '报告是生成时的有效记录快照。5条只是显示摘要的工程门槛；重复作答逐次计入。模型面试分数未经导师校准；计划与学期进度为用户勾选。报告不推断掌握度、学习时长、提升幅度或就业能力。旧学习计划只显示截至生成时的状态，不能确定每个学习日的完成时间。关联记录删除后，历史报告仍是当时快照；个人数据删除须同时删除有关报告。'}
        content['markdown'] = self.markdown(content)
        identifier = self.storage.save_artifact(artifact_type='growth_report', title=f'成长报告 {request.start_date} — {request.end_date}', content=content, metadata={'schema_version': 1, 'origin': 'growth_report'})
        return self.projection({'artifact_id': identifier, **content})

    @staticmethod
    def markdown(content: dict[str, Any]) -> str:
        m = content['metrics']; p = content['period']
        lines = ['# 成长报告', f"期间：{p['start_date']} 至 {p['end_date']}（Asia/Shanghai）", f"数据截至：{content['data_as_of']}",
                 f"有效课程作答：{m['quiz_attempts']}次，其中答对{m['quiz_correct']}次", f"课程练习正确率：{str(m['quiz_accuracy']) + '%' if m['quiz_accuracy'] is not None else '待评测（不足5条）'}",
                 f"编译器判题：{m['compiler_submissions']}次，AC {m['compiler_accepted']}次", f"面试回答：{m['interview_answers']}条，有效模型评分{m['interview_scored_answers']}条",
                 f"面试模型参考分：{m['interview_model_score'] if m['interview_model_score'] is not None else '待评测（不足5条）'}", f"学期任务完成：{m['semester_completed_tasks']}项", '', content['notice'], '', '## 记录依据']
        lines += [f"- {row['created_at']} · {row['kind']} · {row['record_id']} · {row['label']} · {row['value']} · {row['href']}" for row in content['records']]
        return '\n'.join(lines) + '\n'

    def get(self, identifier: str) -> dict[str, Any]:
        artifact = self.storage.get_artifact(identifier)
        if not artifact or artifact['artifact_type'] != 'growth_report':
            raise KeyError(identifier)
        content = artifact['content']
        if not isinstance(content, dict) or content.get('schema_version') != 1:
            raise ValueError('成长报告数据异常')
        try:
            generated = self.markdown(content)
            if generated != content['markdown']:
                raise ValueError('report snapshot mismatch')
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError('成长报告数据异常') from exc
        return {'artifact_id': identifier, **content}

    @staticmethod
    def projection(document: dict[str, Any]) -> dict[str, Any]:
        return {**{key: value for key, value in document.items() if key not in {'records', 'markdown'}},
                'evidence_total': len(document['records']), 'records': document['records'][:20]}

    def list(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.storage._conn().execute("SELECT artifact_id,title,created_at FROM artifacts WHERE artifact_type='growth_report' ORDER BY created_at DESC,rowid DESC LIMIT 30")]
