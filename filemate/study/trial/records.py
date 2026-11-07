"""Immutable private trial records with body-free replay markers and explicit deletion."""

import os

from filemate import __version__
from filemate.execution import data_actions
from filemate.study.orchestrator.models import LOCAL_ZONE, OrchestratorError, aware, utc_now
from filemate.study.orchestrator.repository import atomic, load, put

from .models import RULE_VERSION, DeleteRecord, FeedbackInput, ReflectionInput
from .weekly import WeeklyReader

TYPES = {"reflection": "weekly_reflection", "feedback": "trial_feedback"}
REQUEST_TYPE = "trial_record_request"
DELETE_ACTION = "trial_record_delete"


def enabled():
    return os.getenv("FILEMATE_ENABLE_TRIAL_WORKSPACE", "0") == "1"


def request_id(key):
    return "trial-request-" + data_actions.digest(key)


def record_id(key):
    return "trial-record-" + data_actions.digest(key)


def receipt(marker):
    if marker["kind"] == "delete":
        return marker["result"]
    return {key: marker[key] for key in ("record_id", "kind", "status", "created_at")}


class TrialRecords:
    def __init__(self, storage, *, clock=utc_now):
        self.storage = storage
        self.clock = clock

    def save_feedback(self, body: FeedbackInput):
        return self._save("feedback", body)

    def save_reflection(self, body: ReflectionInput):
        return self._save("reflection", body)

    def _save(self, kind, body):
        if not enabled():
            raise OrchestratorError("trial_workspace_disabled", 503)
        payload_hash = data_actions.digest(body.model_dump(exclude={"request_key", "confirmed"}))
        marker_id = request_id(body.request_key)
        identifier = record_id(body.request_key)
        as_of = aware(self.clock())
        study_date = as_of.astimezone(LOCAL_ZONE).date().isoformat()
        with atomic(self.storage) as conn:
            marker = load(conn, marker_id, REQUEST_TYPE)
            if marker:
                if marker["kind"] != kind or marker["payload_hash"] != payload_hash:
                    raise OrchestratorError("request_key_conflict")
                if marker["status"] == "deleted":
                    raise OrchestratorError("record_deleted", 410)
                return receipt(marker)
            if kind == "reflection":
                weekly = WeeklyReader(self.storage, clock=self.clock).read_in_transaction(
                    self.storage, body.scope, as_of=as_of
                )
                if weekly.revision != body.expected_revision:
                    raise OrchestratorError("weekly_revision_changed")
                content = {
                    "scope": weekly.scope.model_dump(),
                    "week_start": weekly.week_start,
                    "week_end": weekly.week_end,
                    "as_of": weekly.as_of,
                    "summary": weekly.summary.model_dump(),
                    "rule_version": RULE_VERSION,
                    "reason": body.reason,
                    "notes": body.notes,
                    "reason_source": "user_reported",
                }
                title = weekly.week_start
            else:
                count = conn.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE artifact_type=? AND title=?",
                    (REQUEST_TYPE, "feedback:" + study_date),
                ).fetchone()[0]
                if count >= 10:
                    raise OrchestratorError("feedback_daily_limit", 429)
                content = body.model_dump(exclude={"request_key", "confirmed"})
                content["server_version"] = __version__
                title = body.category
            marker = {
                "record_id": identifier,
                "kind": kind,
                "status": "saved",
                "payload_hash": payload_hash,
                "created_at": as_of.isoformat(),
                "study_date": study_date,
            }
            put(conn, identifier, TYPES[kind], content, title=title)
            put(conn, marker_id, REQUEST_TYPE, marker, title=kind + ":" + study_date)
            return receipt(marker)

    def find_request(self, key):
        with self.storage.read_snapshot() as read:
            marker = load(read._conn(), request_id(key), REQUEST_TYPE)
            return receipt(marker) if marker else None

    def list_records(self, kind=None, *, limit=20, offset=0):
        if (
            kind not in (None, *TYPES)
            or type(limit) is not int
            or not 1 <= limit <= 50
            or type(offset) is not int
            or not 0 <= offset <= 10000
        ):
            raise OrchestratorError("invalid_record_page", 422)
        selected = [TYPES[kind]] if kind else list(TYPES.values())
        placeholders = ",".join("?" for _ in selected)
        with self.storage.read_snapshot() as read:
            conn = read._conn()
            total = conn.execute(
                f"SELECT COUNT(*) FROM artifacts WHERE artifact_type IN ({placeholders})", selected
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT artifact_id,artifact_type,title,created_at FROM artifacts "
                f"WHERE artifact_type IN ({placeholders}) ORDER BY created_at DESC,artifact_id LIMIT ? OFFSET ?",
                (*selected, limit, offset),
            ).fetchall()
            items = [
                {
                    "record_id": row["artifact_id"],
                    "kind": next(
                        key for key, value in TYPES.items() if value == row["artifact_type"]
                    ),
                    "title": row["title"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def _detail(self, conn, identifier):
        row = conn.execute(
            "SELECT artifact_type,content,created_at FROM artifacts WHERE artifact_id=?",
            (identifier,),
        ).fetchone()
        if row is None or row["artifact_type"] not in TYPES.values():
            raise OrchestratorError("record_not_found", 404)
        content = load(conn, identifier, row["artifact_type"])
        return {
            "record_id": identifier,
            "kind": next(key for key, value in TYPES.items() if value == row["artifact_type"]),
            "content": content,
            "created_at": row["created_at"],
        }

    def detail(self, identifier):
        with self.storage.read_snapshot() as read:
            return self._detail(read._conn(), identifier)

    def _deletion(self, conn, record):
        impact = {}
        if record["kind"] == "reflection":
            from filemate.study.orchestrator.coach.privacy import coach_dependency_impact

            impact = coach_dependency_impact(
                conn, kind="reflection", record_ids=[record["record_id"]]
            )
        return data_actions.digest({"record": record, "impact": impact}), impact

    def delete_preview(self, identifier):
        with atomic(self.storage) as conn:
            record = self._detail(conn, identifier)
            revision, impact = self._deletion(conn, record)
            token = data_actions.issue(conn, DELETE_ACTION, identifier, revision)
            return {
                "record_id": identifier,
                "kind": record["kind"],
                "confirmation_token": token,
                "affected": {"record": 1, **impact},
                "expires_in_seconds": 900,
            }

    def delete_confirm(self, identifier, body: DeleteRecord):
        operation_hash = data_actions.digest({"record_id": identifier})
        as_of = aware(self.clock())
        with atomic(self.storage) as conn:
            previous_marker = load(conn, request_id(body.request_key), REQUEST_TYPE)
            if previous_marker:
                if (
                    previous_marker["kind"] != "delete"
                    or previous_marker["payload_hash"] != operation_hash
                ):
                    raise OrchestratorError("request_key_conflict")
                return receipt(previous_marker)
            record = self._detail(conn, identifier)
            revision, impact = self._deletion(conn, record)
            previous = data_actions.check(
                conn, DELETE_ACTION, identifier, body.confirmation_token, revision
            )
            if previous:
                return previous
            if record["kind"] == "reflection":
                from filemate.study.orchestrator.coach.privacy import invalidate_coach_dependencies

                invalidate_coach_dependencies(conn, kind="reflection", record_ids=[identifier])
            marker_identifier = identifier.replace("trial-record-", "trial-request-", 1)
            marker = load(conn, marker_identifier, REQUEST_TYPE)
            if not marker or marker["record_id"] != identifier:
                raise OrchestratorError("record_request_missing")
            marker["status"] = "deleted"
            put(
                conn,
                marker_identifier,
                REQUEST_TYPE,
                marker,
                title=marker["kind"] + ":" + marker["study_date"],
                replace=True,
            )
            conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (identifier,))
            result = {
                "record_id": identifier,
                "kind": "delete",
                "status": "deleted",
                "created_at": as_of.isoformat(),
                "deleted": True,
                "affected": {"record": 1, **impact},
            }
            deletion_marker = {
                "record_id": identifier,
                "kind": "delete",
                "status": "deleted",
                "created_at": as_of.isoformat(),
                "study_date": as_of.astimezone(LOCAL_ZONE).date().isoformat(),
                "payload_hash": operation_hash,
                "result": result,
            }
            put(
                conn,
                request_id(body.request_key),
                REQUEST_TYPE,
                deletion_marker,
                title="delete:" + deletion_marker["study_date"],
            )
            data_actions.finish(conn, DELETE_ACTION, identifier, body.confirmation_token, result)
            return result
