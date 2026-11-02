"""Version-bound schedule previews, confirmations and reversible events."""

import json
from datetime import datetime, timedelta, timezone

from filemate.execution import data_actions
from filemate.execution.storage import QuestionRevisionConflict
from filemate.wrongbook.engine import RULE_VERSION, parse_time
from filemate.wrongbook.models import Schedule
from filemate.wrongbook.repository import ENGINE_FIELDS, ReviewRepository

SCHEDULE_FIELDS = (*ENGINE_FIELDS, "legacy_mastered")


class ReviewCommands:
    def __init__(self, repository: ReviewRepository):
        self.repo = repository

    def _proposal(self, conn, old: dict, command: Schedule) -> dict:
        """Calculate exactly what the user will confirm, without touching evidence."""
        if old["revision"] != command.expected_revision:
            raise QuestionRevisionConflict("错题已变化，请重新预览")
        now = self.repo.now()
        after = {field: old[field] for field in SCHEDULE_FIELDS}
        if command.action == "undo":
            event = conn.execute("SELECT * FROM review_events WHERE event_id=? AND wrong_id=?",
                                 (command.undo_event_id, old["wrong_id"])).fetchone()
            undone = conn.execute("SELECT 1 FROM review_events WHERE undo_of=?", (command.undo_event_id,)).fetchone()
            if (event is None or not event["action"].startswith("schedule_") or event["action"] == "schedule_undo"
                    or undone or json.loads(event["after_state"])["revision"] != old["revision"]):
                raise QuestionRevisionConflict("已有后续操作或该事件不可撤销，请保留记录并重新预览")
            before = json.loads(event["before_state"])
            after.update({field: before[field] for field in SCHEDULE_FIELDS})
            return after
        if command.action == "pause":
            if old["schedule_status"] == "paused":
                raise QuestionRevisionConflict("该错题已暂停")
            after.update(schedule_status="paused", paused_at=now.isoformat(timespec="seconds"))
            return after
        if old["read_only_snapshot"]:
            raise QuestionRevisionConflict("历史题集只读；可保留或暂停，不重新安排训练")
        if command.action == "activate":
            if old["scheduler_version"] == RULE_VERSION:
                raise QuestionRevisionConflict("该错题已经使用新规则")
            after.update(scheduler_version=RULE_VERSION, learning_status="needs_review",
                         schedule_status="active", paused_at=None, mastered=0,
                         correct_streak=0, review_stage=0, eligible_count=0,
                         first_verified_at=None, last_verified_at=None, interval_days=0,
                         legacy_mastered=int(old["legacy_mastered"]))
        elif command.action == "resume":
            if old["schedule_status"] != "paused":
                raise QuestionRevisionConflict("该错题未暂停")
            after.update(schedule_status="active", paused_at=None)
        if command.next_review_at is not None:
            try:
                moment = datetime.fromisoformat(command.next_review_at)
                if moment.tzinfo is None or not now <= moment <= now + timedelta(days=365):
                    raise ValueError("invalid date")
                moment = moment.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("复习时间须带时区，且在现在至365天内") from exc
        else:
            original = parse_time(old["next_review_at"])
            if original is None:
                raise ValueError("原排期无效，请明确选择新的复习时间")
            moment = now if command.action == "activate" else max(now, original)
        after["next_review_at"] = moment.isoformat(timespec="seconds")
        return after

    def preview(self, wrong_id: str, payload: dict) -> dict:
        """Issue a short-lived token bound to current data, parameters and exact changes."""
        command = Schedule.model_validate(payload)
        fingerprint = data_actions.digest({"operation": "schedule", "wrong_id": wrong_id, **command.model_dump()})
        with self.repo.transaction() as conn:
            old = self.repo.detail(wrong_id)
            after = self._proposal(conn, old, command)
            binding = json.dumps({"state_digest": data_actions.digest(old), "command_digest": fingerprint,
                                  "after": after}, sort_keys=True, ensure_ascii=False)
            token = data_actions.issue(conn, "review_schedule", wrong_id, binding)
            return {"wrong_id": wrong_id, "before": self.repo.state(old), "after": after,
                    "confirmation_token": token, "expires_in_seconds": 900}

    def confirm(self, wrong_id: str, payload: dict, token: str) -> dict:
        """Atomically apply the shown state, event, audit and repeatable receipt."""
        command = Schedule.model_validate(payload)
        fingerprint = data_actions.digest({"operation": "schedule", "wrong_id": wrong_id, **command.model_dump()})
        with self.repo.transaction() as conn:
            old = self.repo.detail(wrong_id)
            preview = conn.execute("SELECT * FROM data_action_previews WHERE token_hash=?",
                                   (data_actions.digest(token),)).fetchone()
            if preview is None:
                raise QuestionRevisionConflict("请重新预览此排期操作")
            try:
                binding = json.loads(preview["revision"])
                if binding["command_digest"] != fingerprint:
                    raise ValueError("changed command")
                current = preview["revision"] if binding["state_digest"] == data_actions.digest(old) else None
                receipt = data_actions.check(conn, "review_schedule", wrong_id, token, current)
            except (ValueError, KeyError, TypeError) as exc:
                raise QuestionRevisionConflict("排期、参数或预览已变化，请重新预览") from exc
            if receipt is not None:
                replay = self.repo.replay(conn, command.request_key, fingerprint)
                if replay != receipt:
                    raise QuestionRevisionConflict("确认回执与操作记录不一致")
                return receipt
            if self.repo.replay(conn, command.request_key, fingerprint) is not None:
                raise QuestionRevisionConflict("此操作已执行，请读取原回执")
            after = binding["after"]
            changes = {field: after[field] for field in SCHEDULE_FIELDS}
            changes.update(revision=old["revision"] + 1, updated_at=self.repo.now().isoformat(timespec="seconds"))
            conn.execute("UPDATE wrong_questions SET " + ",".join(f"{key}=?" for key in changes) + " WHERE wrong_id=?",
                         [*changes.values(), wrong_id])
            state = self.repo.state(self.repo.detail(wrong_id))
            result = self.repo.event(conn, row=old, action="schedule_" + command.action,
                                     key=command.request_key, fingerprint=fingerprint,
                                     before=self.repo.state(old), after=state,
                                     result={"wrong_id": wrong_id, "revision": state["revision"],
                                             "after": state, "affected": {"wrong_questions": 1}, "reason": command.reason},
                                     undo_of=command.undo_event_id)
            data_actions.finish(conn, "review_schedule", wrong_id, token, result)
            return result
