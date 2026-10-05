"""编程记录的预览确认、关联报告清理与最小审计。"""

from __future__ import annotations

import json
from typing import Any

from filemate.execution import data_actions
from filemate.execution.storage import SQLiteStorage, _now_iso


def _references(value: Any, identifier: str) -> bool:
    if isinstance(value, dict):
        return any(_references(item, identifier) for item in value.values())
    if isinstance(value, list):
        return any(_references(item, identifier) for item in value)
    return value == identifier


class CodingPrivacy:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def _state(self, identifier: str) -> dict[str, Any] | None:
        conn = self.storage._conn()
        row = conn.execute('SELECT * FROM coding_submissions WHERE submission_id=?', (identifier,)).fetchone()
        if not row:
            return None
        related = []
        for artifact in conn.execute("SELECT * FROM artifacts WHERE artifact_type IN ('resume','resume_profile','growth_report')"):
            try:
                content = json.loads(artifact['content'])
                matched = _references(content, identifier)
            except (ValueError, TypeError):
                matched = identifier in artifact['content']
            if matched:
                related.append(dict(artifact))
        return {'submission': dict(row),
                'artifact': dict(conn.execute('SELECT * FROM artifacts WHERE artifact_id=?', (row['artifact_id'],)).fetchone() or {}),
                'events': [dict(event) for event in conn.execute('SELECT * FROM coding_events WHERE submission_id=? ORDER BY event_id', (identifier,))],
                'related': related}

    def preview(self, identifier: str) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._state(identifier)
            if not state:
                raise KeyError(identifier)
            if state['submission']['status'] in {'queued', 'running'}:
                raise ValueError('请先取消或结束该提交的评测')
            return {'submission_id': identifier, 'code_records': 1, 'feedback_and_events': len(state['events']),
                    'related_reports': sum(artifact['artifact_type'] != 'resume_profile' for artifact in state['related']),
                    'profile_links': sum(artifact['artifact_type'] == 'resume_profile' for artifact in state['related']),
                    'confirmation_token': data_actions.issue(conn, 'coding_delete', identifier, data_actions.digest(state)),
                    'notice': '删除源码、编译结果、AI建议、笔记和操作事件；相关简历/成长报告整份移除，当前个人事实解除作品关联。技能目标保留并重新判断证据。已经下载的备份或第三方模型留存不由此操作删除。'}

    def delete(self, identifier: str, token: str) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            state = self._state(identifier)
            if not state and not conn.execute("SELECT 1 FROM data_action_previews WHERE token_hash=? AND action='coding_delete' AND resource_id=? AND result IS NOT NULL", (data_actions.digest(token), identifier)).fetchone():
                raise KeyError(identifier)
            receipt = data_actions.check(conn, 'coding_delete', identifier, token, data_actions.digest(state) if state else None)
            if receipt:
                return receipt
            if state['submission']['status'] in {'queued', 'running'}:
                raise ValueError('评测仍在执行，请结束后重新预览')
            reports = 0; links = 0
            for artifact in state['related']:
                if artifact['artifact_type'] == 'resume_profile':
                    from filemate.portfolio.resume import Profile
                    try:
                        profile = Profile.model_validate(json.loads(artifact['content']))
                        for project in profile.projects:
                            if project.submission_id == identifier:
                                project.submission_id = None; links += 1
                        profile.revision += 1
                        conn.execute('UPDATE artifacts SET content=?,updated_at=? WHERE artifact_id=?', (profile.model_dump_json(), _now_iso(), artifact['artifact_id']))
                    except (ValueError, TypeError):
                        raise ValueError('关联的个人事实数据异常，请修复或导出检查后再删除；原数据保留') from None
                else:
                    conn.execute('DELETE FROM artifacts WHERE artifact_id=?', (artifact['artifact_id'],)); reports += 1
            conn.execute('DELETE FROM artifacts WHERE artifact_id=?', (state['submission']['artifact_id'],))
            conn.execute('DELETE FROM coding_submissions WHERE submission_id=?', (identifier,))
            receipt = {'deleted': True, 'code_records': 1, 'related_reports': reports, 'profile_links': links}
            data_actions.finish(conn, 'coding_delete', identifier, token, receipt)
            return receipt
