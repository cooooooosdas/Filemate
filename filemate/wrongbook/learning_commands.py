"""Preview and confirm evidence-based changes without overwriting manual work."""

import json
import os
from datetime import date, timedelta
from uuid import uuid4

from filemate.execution import data_actions
from filemate.execution.storage import QuestionRevisionConflict
from filemate.task_resources import admit_plan
from filemate.wrongbook.analysis_models import Adoption, LearningPlan
from filemate.wrongbook.analysis_repository import ReviewAnalysisRepository, enabled, valid_key
from filemate.wrongbook.engine import LOCAL_ZONE
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.models import Diagnosis
from filemate.wrongbook.repository import ReviewRepository


class ReviewLearningCommands:
    def __init__(self, storage, clock=None):
        self.storage = storage
        self.repo = ReviewRepository(storage, clock=clock)
        self.analyses = ReviewAnalysisRepository(storage, clock)

    def _adoption(self, wrong_id, analysis_id, selection):
        if not enabled():
            raise ValueError('analysis_disabled')
        old = self.repo.detail(wrong_id)
        analysis = self.analyses.get(wrong_id, analysis_id)
        candidates = {c['cause_code'] for c in (analysis.get('result') or {}).get('possible_causes', [])}
        if (old['revision'] != selection.expected_revision or old['read_only_snapshot'] or analysis['stale']
                or analysis['status'] != 'ready' or not set(selection.selected_causes) <= candidates):
            raise QuestionRevisionConflict('analysis_or_diagnosis_changed')
        current = old['error_causes'] if old['error_cause_source'] == 'user' else []
        causes = list(dict.fromkeys([*current, *selection.selected_causes]))
        if len(causes) > 3:
            raise QuestionRevisionConflict('已确认错因与所选候选合计超过3项，请先调整选择')
        after = {'error_causes': causes, 'primary_cause': old['error_cause'] if current else causes[0],
            'note': old['error_cause_note'], 'custom_tags': old['custom_tags']}
        return old, analysis, after

    @staticmethod
    def _adoption_digest(wrong_id, analysis_id, selection):
        return data_actions.digest({'action': 'analysis_adopt', 'wrong_id': wrong_id,
            'analysis_id': analysis_id, **selection.model_dump()})

    def preview_adoption(self, wrong_id, analysis_id, selection):
        """Show the exact merged diagnosis before any learning state is changed."""
        body = Adoption.model_validate(selection)
        with self.repo.transaction() as conn:
            old, analysis, after = self._adoption(wrong_id, analysis_id, body)
            binding = json.dumps({'command_digest': self._adoption_digest(wrong_id, analysis_id, body),
                'before_digest': data_actions.digest(old), 'analysis_digest': data_actions.digest(analysis),
                'after': after}, ensure_ascii=False, sort_keys=True)
            token = data_actions.issue(conn, 'review_learning_adopt', f'{wrong_id}:{analysis_id}', binding)
            return {'wrong_id': wrong_id, 'analysis_id': analysis_id, 'before': self.repo.state(old),
                'after': after, 'confirmation_token': token, 'expires_in_seconds': 900}

    def confirm_adoption(self, wrong_id, analysis_id, selection, token, key, confirmed):
        """Commit a current preview, preserving notes, tags and existing confirmed causes."""
        valid_key(key)
        if confirmed is not True:
            raise ValueError('confirmation_required')
        if not enabled():
            raise ValueError('analysis_disabled')
        body = Adoption.model_validate(selection)
        fingerprint = self._adoption_digest(wrong_id, analysis_id, body)
        with self.repo.transaction() as conn:
            replay = self.repo.replay(conn, key, fingerprint)
            preview = conn.execute('SELECT * FROM data_action_previews WHERE token_hash=?', (data_actions.digest(token),)).fetchone()
            if preview is None:
                raise QuestionRevisionConflict('请重新预览错因采纳')
            try:
                binding = json.loads(preview['revision'])
                if binding['command_digest'] != fingerprint:
                    raise ValueError('changed_selection')
                if preview['result'] is not None:
                    result = data_actions.check(conn, 'review_learning_adopt', f'{wrong_id}:{analysis_id}', token, None)
                    if replay is not None and replay != result:
                        raise ValueError('receipt_conflict')
                    return result
                old, analysis, after = self._adoption(wrong_id, analysis_id, body)
                if binding['before_digest'] != data_actions.digest(old) or binding['analysis_digest'] != data_actions.digest(analysis):
                    raise ValueError('input_changed')
                data_actions.check(conn, 'review_learning_adopt', f'{wrong_id}:{analysis_id}', token, preview['revision'])
            except (ValueError, KeyError, TypeError) as exc:
                raise QuestionRevisionConflict('证据、错因或预览已变化，请重新预览') from exc
            command = Diagnosis.model_validate({'expected_revision': body.expected_revision, 'request_key': key, **after})
            result = self.repo._diagnose_in_transaction(conn, wrong_id, command, fingerprint=fingerprint,
                action='analysis_adopt', extra={'analysis_id': analysis_id, 'selected_causes': body.selected_causes,
                    'affected': {'wrong_questions': 1}})
            data_actions.finish(conn, 'review_learning_adopt', f'{wrong_id}:{analysis_id}', token, result)
            return result

    def _plan_context(self, wrong_id, attempt_id=None, course_id=None):
        detail = self.repo.detail(wrong_id)
        if detail['read_only_snapshot']:
            raise QuestionRevisionConflict('历史题不新建学习任务')
        if attempt_id is None:
            last = self.storage._conn().execute('''SELECT attempt_id FROM quiz_attempts
                WHERE artifact_id=? AND question_index=? ORDER BY created_at DESC,rowid DESC LIMIT 1''',
                (detail['artifact_id'], detail['question_index'])).fetchone()
            if last is None:
                raise LookupError('缺少实际作答')
            attempt_id = last[0]
        return ReviewLearningContext(self.storage, self.repo.now).build(wrong_id, attempt_id, course_id)

    def _goal(self, context, goal_id):
        if goal_id is None:
            return None
        goal = self.storage.get_artifact(goal_id)
        primary = self.repo.detail(context['ref']['wrong_id'])['source_id']
        allowed = bool(goal and goal['artifact_type'] == 'reverse_goal_plan' and goal['source_id'] == primary and primary)
        cid = (context.get('_graph_binding') or {}).get('course_id')
        if not allowed and cid and goal and goal['artifact_type'] == 'reverse_goal_plan':
            allowed = bool(self.storage._conn().execute('SELECT 1 FROM kg_course_sources WHERE course_id=? AND source_id=? AND active=1', (cid, goal['source_id'])).fetchone())
        if not allowed:
            raise QuestionRevisionConflict('目标不属于此题资料或所选课程')
        return goal

    def suggestions(self, wrong_id, goal_id=None):
        """Return bounded rules; no model call, target rewrite or task creation."""
        context = self._plan_context(wrong_id)
        self._goal(context, goal_id)
        return {'items': context['next_actions'], 'goal_id': goal_id,
            'start_date': self.repo.now().astimezone(LOCAL_ZONE).date().isoformat()}

    def _prepare_plan(self, wrong_id, selection):
        context = self._plan_context(wrong_id, selection.attempt_id, selection.course_id)
        if context['review_state']['revision'] != selection.expected_revision:
            raise QuestionRevisionConflict('复盘证据已变化')
        start = date.fromisoformat(selection.start_date)
        today = self.repo.now().astimezone(LOCAL_ZONE).date()
        if not today <= start <= today+timedelta(days=30):
            raise ValueError('计划日期须在今天至未来30日')
        candidates = {t['action_id']: t for t in context['next_actions']}
        if not {t.action_id for t in selection.tasks} <= candidates.keys():
            raise QuestionRevisionConflict('候选任务已变化，请重新选择')
        goal = self._goal(context, selection.goal_id)
        days = {}
        basis = []
        for task in selection.tasks:
            day = days.setdefault(task.day_offset, {'date': (start+timedelta(days=task.day_offset)).isoformat(),
                'focus': task.title, 'duration_minutes': 0, 'review_method': '独立训练后核对', 'tasks': [], 'training_actions': []})
            day['duration_minutes'] += task.duration_minutes
            day['tasks'].append(task.instructions)
            day['training_actions'].append({'label': task.title, 'route': candidates[task.action_id]['route']})
            basis.append({'action_id': task.action_id, 'basis': candidates[task.action_id]['basis']})
        daily = [days[d] for d in sorted(days)]
        plan = {'title': '错题复盘增量计划', 'exam_date': daily[-1]['date'], 'daily_minutes': max(d['duration_minutes'] for d in daily),
            'goal': '完成有依据的短行动；完成记录不代表答对或掌握', 'daily_plan': daily, 'total_days': len(daily),
            'strategy': '保留原计划，仅新增本次确认的任务', 'topics': [], 'checkpoints': [],
            'review_learning': {'ref': context['ref'], 'attempt_id': context['attempt']['attempt_id'],
                'context_revision': context['context_revision'], 'goal_id': selection.goal_id, 'basis': basis}}
        dependencies = {s['source_id']: s['source_revision'] for s in context['_source_dependencies']}
        if goal and goal['source_id']:
            dependencies[goal['source_id']] = self.storage.get_source_revision(goal['source_id'])
        return {'plan': plan, 'input_digest': context['input_digest'], 'context_revision': context['context_revision'],
            'goal_digest': data_actions.digest(goal), 'source_dependencies': dependencies}

    @staticmethod
    def _plan_fingerprint(wrong_id, selection):
        return data_actions.digest({'action': 'learning_plan_confirm', 'wrong_id': wrong_id, **selection.model_dump()})

    @staticmethod
    def _write_enabled():
        if os.getenv('FILEMATE_ENABLE_WRONGBOOK_V2', '0') != '1':
            raise ValueError('review_writes_disabled')

    def preview_plan(self, wrong_id, selection):
        self._write_enabled()
        body = LearningPlan.model_validate(selection)
        with self.repo.transaction() as conn:
            proposal = self._prepare_plan(wrong_id, body)
            binding = json.dumps({'command_digest': self._plan_fingerprint(wrong_id, body), 'proposal': proposal}, ensure_ascii=False, sort_keys=True)
            token = data_actions.issue(conn, 'review_learning_plan', wrong_id, binding)
            return {'wrong_id': wrong_id, 'plan': proposal['plan'], 'affected': {'plans': 1, 'tasks': len(body.tasks)},
                'confirmation_token': token, 'expires_in_seconds': 900}

    def _check_learning_token(self, conn, action, resource, token, fingerprint, current=None):
        row = conn.execute('SELECT * FROM data_action_previews WHERE token_hash=?', (data_actions.digest(token),)).fetchone()
        try:
            if row is None or row['action'] != action or row['resource_id'] != resource:
                raise ValueError('missing_preview')
            binding = json.loads(row['revision'])
            if binding['command_digest'] != fingerprint:
                raise ValueError('changed_command')
            if row['result'] is None and current != binding:
                raise ValueError('changed_proposal')
            return data_actions.check(conn, action, resource, token, row['revision'] if current == binding else None)
        except (ValueError, TypeError, KeyError) as exc:
            raise QuestionRevisionConflict('证据、编辑内容或预览已变化，请重新预览') from exc

    def _plan_state(self, plan_id, artifact_id):
        plan, artifact = self.storage.get_study_plan(plan_id), self.storage.get_artifact(artifact_id)
        if not plan or not artifact or plan['artifact_id'] != artifact_id:
            raise QuestionRevisionConflict('本次新增计划已不存在')
        return {'plan': plan, 'artifact': artifact}

    def confirm_plan(self, wrong_id, selection, token, key, confirmed):
        self._write_enabled()
        valid_key(key)
        if confirmed is not True:
            raise ValueError('confirmation_required')
        body = LearningPlan.model_validate(selection)
        fingerprint = self._plan_fingerprint(wrong_id, body)
        with self.repo.transaction() as conn:
            replay = self.repo.replay(conn, key, fingerprint)
            if replay is not None:
                return replay
            # 已确认token可直接恢复回执，不再次要求已消费的旧修订仍是当前。
            saved = conn.execute('SELECT result FROM data_action_previews WHERE token_hash=?', (data_actions.digest(token),)).fetchone()
            proposal = None if saved and saved['result'] else self._prepare_plan(wrong_id, body)
            receipt = self._check_learning_token(conn, 'review_learning_plan', wrong_id, token, fingerprint,
                {'command_digest': fingerprint, 'proposal': proposal} if proposal else None)
            if receipt is not None:
                return receipt
            plan = proposal['plan']
            admit_plan(self.storage.db_path, 'study_plan', plan)
            aid, pid, eid = uuid4().hex, uuid4().hex, uuid4().hex
            source_id = self.repo.detail(wrong_id)['source_id']
            content = json.dumps(plan, ensure_ascii=False)
            metadata = {'review_learning': {**plan['review_learning'], 'event_id': eid}}
            conn.execute("INSERT INTO artifacts(artifact_id,source_id,artifact_type,title,content,metadata) VALUES(?,?,'study_plan',?,?,?)",
                (aid, source_id, plan['title'], content, json.dumps(metadata, ensure_ascii=False)))
            conn.execute('''INSERT INTO study_plans(plan_id,artifact_id,source_id,title,exam_date,daily_minutes,goal,plan_data)
                VALUES(?,?,?,?,?,?,?,?)''', (pid, aid, source_id, plan['title'], plan['exam_date'], plan['daily_minutes'], plan['goal'], content))
            for sid in proposal['source_dependencies']:
                conn.execute('INSERT INTO kg_learning_artifact_sources VALUES(?,?)', (aid, sid))
            state = self._plan_state(pid, aid)
            receipt = self.repo.event(conn, row=self.repo.detail(wrong_id), action='learning_plan_confirm', key=key,
                fingerprint=fingerprint, before={}, after={'plan_id': pid, 'artifact_id': aid, 'digest': data_actions.digest(state)},
                result={'wrong_id': wrong_id, 'plan_id': pid, 'artifact_id': aid,
                    'route': f'/study-plan?plan={pid}', 'affected': {'plans': 1, 'tasks': len(body.tasks)}}, event_id=eid)
            data_actions.finish(conn, 'review_learning_plan', wrong_id, token, receipt)
            return receipt

    def _undo_proposal(self, wrong_id, event_id):
        conn = self.storage._conn()
        raw = conn.execute('SELECT * FROM review_events WHERE event_id=? AND wrong_id=?', (event_id, wrong_id)).fetchone()
        if raw is None or raw['action'] not in {'analysis_adopt', 'learning_plan_confirm'}:
            raise LookupError('本次学习操作不存在')
        if conn.execute('SELECT 1 FROM review_events WHERE undo_of=?', (event_id,)).fetchone():
            raise QuestionRevisionConflict('该操作已撤销')
        event = dict(raw)
        before, after = json.loads(event['before_state']), json.loads(event['after_state'])
        if event['action'] == 'learning_plan_confirm':
            state = self._plan_state(after['plan_id'], after['artifact_id'])
            if state['plan']['completed_days'] or state['plan']['status'] != 'active' or data_actions.digest(state) != after['digest']:
                raise QuestionRevisionConflict('新增计划已完成、修改或归档，保留当前内容')
            proposal = {'kind': 'plan', 'plan_id': after['plan_id'], 'artifact_id': after['artifact_id'], 'state_digest': after['digest']}
        else:
            current = self.repo.detail(wrong_id)
            if current['revision'] != after['revision']:
                raise QuestionRevisionConflict('错因已有后续操作，不能覆盖当前版本')
            fields = ('error_cause', 'error_cause_source', 'error_cause_confidence', 'error_cause_note',
                'error_causes', 'custom_tags', 'diagnosed_at')
            proposal = {'kind': 'diagnosis', 'before': {k: before[k] for k in fields}, 'state_digest': data_actions.digest(current)}
        return proposal

    def preview_undo(self, wrong_id, event_id):
        self._write_enabled()
        with self.repo.transaction() as conn:
            proposal = self._undo_proposal(wrong_id, event_id)
            fingerprint = data_actions.digest({'action': 'learning_undo', 'wrong_id': wrong_id, 'event_id': event_id})
            binding = json.dumps({'command_digest': fingerprint, 'proposal': proposal}, ensure_ascii=False, sort_keys=True)
            token = data_actions.issue(conn, 'review_learning_undo', f'{wrong_id}:{event_id}', binding)
            return {'wrong_id': wrong_id, 'event_id': event_id, 'changes': proposal,
                'confirmation_token': token, 'expires_in_seconds': 900}

    def confirm_undo(self, wrong_id, event_id, token, key, confirmed):
        self._write_enabled()
        valid_key(key)
        if confirmed is not True:
            raise ValueError('confirmation_required')
        fingerprint = data_actions.digest({'action': 'learning_undo', 'wrong_id': wrong_id, 'event_id': event_id})
        with self.repo.transaction() as conn:
            replay = self.repo.replay(conn, key, fingerprint)
            if replay is not None:
                return replay
            saved = conn.execute('SELECT result FROM data_action_previews WHERE token_hash=?', (data_actions.digest(token),)).fetchone()
            proposal = None if saved and saved['result'] else self._undo_proposal(wrong_id, event_id)
            receipt = self._check_learning_token(conn, 'review_learning_undo', f'{wrong_id}:{event_id}', token, fingerprint,
                {'command_digest': fingerprint, 'proposal': proposal} if proposal else None)
            if receipt is not None:
                return receipt
            row = self.repo.detail(wrong_id)
            if proposal['kind'] == 'plan':
                conn.execute('DELETE FROM artifacts WHERE artifact_id=?', (proposal['artifact_id'],))
                affected = {'plans': 1, 'artifacts': 1}
            else:
                values = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in proposal['before'].items()}
                values.update(revision=row['revision']+1, updated_at=self.repo.now().isoformat(timespec='seconds'))
                conn.execute('UPDATE wrong_questions SET '+','.join(k+'=?' for k in values)+' WHERE wrong_id=?', [*values.values(), wrong_id])
                affected = {'wrong_questions': 1}
            receipt = self.repo.event(conn, row=row, action='learning_undo', key=key, fingerprint=fingerprint,
                before=self.repo.state(row), after=self.repo.state(self.repo.detail(wrong_id)), undo_of=event_id,
                result={'wrong_id': wrong_id, 'undone_event_id': event_id, 'affected': affected})
            data_actions.finish(conn, 'review_learning_undo', f'{wrong_id}:{event_id}', token, receipt)
            return receipt
