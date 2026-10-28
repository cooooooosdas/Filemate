"""Preview and confirm evidence-based changes without overwriting manual work."""

import json

from filemate.execution import data_actions
from filemate.execution.storage import QuestionRevisionConflict
from filemate.wrongbook.analysis_models import Adoption
from filemate.wrongbook.analysis_repository import ReviewAnalysisRepository, enabled, valid_key
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
