"""Assessment claims, immutable artifacts and stale-write protection."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from filemate.interview_coach.repository import CoachError, CoachRepository
from filemate.interview_review.repository import ReviewRepository

from .rules import PROMPT_VERSION, RULES_VERSION, digest, pending_result, rubric_for, snapshot


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class AssessmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["local", "model"] = "local"
    external_consent: bool = False


def normalize_restored_assessments(conn) -> None:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='interview_assessments'"
    ).fetchone():
        return
    conn.execute(
        "UPDATE interview_assessments SET status='interrupted',error_code=CASE WHEN error_code='cleared' THEN 'cleared' ELSE 'restored' END,epoch=lower(hex(randomblob(16))) WHERE status IN ('running','cancelling')"
    )


class AssessmentRepository:
    def __init__(self, storage):
        self.storage = storage
        self.coach = CoachRepository(storage)

    def _input(self, sid: str):
        interview = self.storage.get_interview(sid)
        if interview is None:
            raise CoachError("assessment_not_found", 404)
        try:
            snap = snapshot(interview)
            rubric = rubric_for(interview)
        except ValueError as exc:
            raise CoachError("assessment_evidence_unavailable") from exc
        return snap, rubric

    def _interrupt(self, conn, sid):
        conn.execute(
            "UPDATE interview_assessments SET status='interrupted',error_code=CASE WHEN error_code='cleared' THEN 'cleared' ELSE 'timeout' END,finished_at=? WHERE interview_id=? AND status IN ('running','cancelling') AND deadline_at<?",
            (now(), sid, now()),
        )

    def context(self, sid: str) -> dict[str, Any]:
        with self.storage._write_lock, self.storage._conn() as conn:
            snap, rubric = self._input(sid)
            self._interrupt(conn, sid)
            row = conn.execute(
                "SELECT model_reserved FROM interview_assessment_limits WHERE interview_id=?",
                (sid,),
            ).fetchone()
            return {
                "input_digest": digest(snap),
                "rubric": rubric,
                "answered": len(snap["turns"]),
                "model_requests_remaining": (12 - (row[0] if row else 0)) // 2,
                "history": self.history(sid=sid)["items"],
            }

    def history(self, *, sid: str | None = None, limit: int = 20, offset: int = 0):
        if not 1 <= limit <= 100 or offset < 0:
            raise CoachError("invalid_parameter", 422)
        conn = self.storage._conn()
        where, params = (
            ("WHERE COALESCE(error_code,'')!='cleared' AND interview_id=?", [sid])
            if sid
            else ("WHERE COALESCE(error_code,'')!='cleared'", [])
        )
        rows = conn.execute(
            f"SELECT assessment_id,interview_id,mode,status,rubric_id,rubric_version,created_at,error_code,input_digest FROM interview_assessments {where} ORDER BY created_at DESC,assessment_id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        count = conn.execute(
            f"SELECT COUNT(*) FROM interview_assessments {where}", params
        ).fetchone()[0]
        return {
            "items": [dict(row) for row in rows],
            "total": count,
            "offset": offset,
            "limit": limit,
        }

    def read(self, sid: str, assessment_id: str):
        row = (
            self.storage._conn()
            .execute(
                "SELECT * FROM interview_assessments WHERE interview_id=? AND assessment_id=?",
                (sid, assessment_id),
            )
            .fetchone()
        )
        if not row:
            raise CoachError("assessment_not_found", 404)
        artifact = self.storage.get_artifact(row["artifact_id"]) if row["artifact_id"] else None
        report = artifact["content"] if artifact else None
        if report is not None and (not isinstance(report, dict) or report.get("version") != "2.6"):
            raise CoachError("assessment_evidence_unavailable")
        return {
            "assessment_id": row["assessment_id"],
            "interview_id": sid,
            "status": row["status"],
            "mode": row["mode"],
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "input_digest": row["input_digest"],
            "report": report,
        }

    def previous(self, sid: str, command: AssessmentCommand):
        row = (
            self.storage._conn()
            .execute(
                "SELECT assessment_id,request_digest FROM interview_assessments WHERE interview_id=? AND request_key=?",
                (sid, command.request_key),
            )
            .fetchone()
        )
        if not row:
            return None
        if row["request_digest"] != digest(command.model_dump()):
            raise CoachError("request_key_conflict")
        return self.read(sid, row["assessment_id"])

    def claim(self, sid: str, command: AssessmentCommand, provenance: dict[str, Any]):
        self.coach.snapshot(sid)
        with self.coach.transaction() as conn:
            self._interrupt(conn, sid)
            previous = self.previous(sid, command)
            if previous:
                return {"execute": False, "assessment": previous}
            snap, rubric = self._input(sid)
            if digest(snap) != command.expected_digest:
                raise CoachError("assessment_stale")
            if not snap["turns"]:
                raise CoachError("assessment_answer_required", 422)
            if command.mode == "model" and not command.external_consent:
                raise CoachError("consent_required")
            if (
                conn.execute(
                    "SELECT 1 FROM interview_assessments WHERE interview_id=? AND status IN ('running','cancelling')",
                    (sid,),
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM interview_coach_analysis_runs WHERE interview_id=? AND status IN ('running','cancelling')",
                    (sid,),
                ).fetchone()
            ):
                raise CoachError("analysis_in_progress")
            if (
                conn.execute(
                    "SELECT COUNT(*) FROM interview_assessments WHERE interview_id=?", (sid,)
                ).fetchone()[0]
                >= 100
            ):
                raise CoachError("assessment_limit", 429)
            conn.execute(
                "INSERT OR IGNORE INTO interview_assessment_limits(interview_id) VALUES (?)", (sid,)
            )
            if command.mode == "model":
                if (
                    conn.execute(
                        "SELECT model_reserved FROM interview_assessment_limits WHERE interview_id=?",
                        (sid,),
                    ).fetchone()[0]
                    >= 12
                ):
                    raise CoachError("assessment_budget", 429)
                runtime = conn.execute(
                    "SELECT status FROM interview_runtime WHERE interview_id=?", (sid,)
                ).fetchone()
                if runtime and runtime[0] == "running":
                    from filemate.interview_runtime import reserve_runtime_ai

                    reserve_runtime_ai(conn, sid)
                conn.execute(
                    "UPDATE interview_assessment_limits SET model_reserved=model_reserved+2 WHERE interview_id=?",
                    (sid,),
                )
            conn.execute(
                "INSERT OR IGNORE INTO interview_rubrics VALUES (?,?,?,?)",
                (rubric["id"], rubric["version"], encode(rubric), digest(rubric)),
            )
            saved = conn.execute(
                "SELECT content_digest FROM interview_rubrics WHERE rubric_id=? AND version=?",
                (rubric["id"], rubric["version"]),
            ).fetchone()[0]
            if saved != digest(rubric):
                raise CoachError("assessment_rubric_conflict")
            conn.execute(
                "INSERT OR IGNORE INTO interview_review_state(interview_id) VALUES (?)", (sid,)
            )
            review_rev = conn.execute(
                "SELECT revision FROM interview_review_state WHERE interview_id=?", (sid,)
            ).fetchone()[0]
            consent_rev = conn.execute(
                "SELECT consent_revision FROM interview_coach_state WHERE interview_id=?", (sid,)
            ).fetchone()[0]
            aid, epoch, instant = uuid.uuid4().hex, uuid.uuid4().hex, datetime.now(timezone.utc)
            conn.execute(
                "INSERT INTO interview_assessments(assessment_id,interview_id,request_key,request_digest,input_digest,input_snapshot,rubric_id,rubric_version,rubric_snapshot,mode,status,epoch,consent_revision,review_revision,provenance,created_at,deadline_at) VALUES (?,?,?,?,?,?,?,?,?,?,'running',?,?,?,?,?,?)",
                (
                    aid,
                    sid,
                    command.request_key,
                    digest(command.model_dump()),
                    digest(snap),
                    encode(snap),
                    rubric["id"],
                    rubric["version"],
                    encode(rubric),
                    command.mode,
                    epoch,
                    consent_rev,
                    review_rev,
                    encode(provenance),
                    instant.isoformat(),
                    (instant + timedelta(seconds=65)).isoformat(),
                ),
            )
            for turn in snap["turns"]:
                run_id = turn.get("latest_run_id")
                if (
                    run_id
                    and not conn.execute(
                        "SELECT 1 FROM interview_coach_analysis_runs WHERE run_id=? AND attempt_id=?",
                        (run_id, turn["attempt_id"]),
                    ).fetchone()
                ):
                    run_id = None
                conn.execute(
                    "INSERT INTO interview_assessment_evidence VALUES (?,?,?)",
                    (aid, turn["attempt_id"], run_id),
                )
            ReviewRepository(self.storage)._event(
                sid, "assessment_started", {"assessment_id": aid, "mode": command.mode}
            )
            return {
                "execute": True,
                "assessment_id": aid,
                "epoch": epoch,
                "input": snap,
                "rubric": rubric,
            }

    def finish(self, claim, *, result=None, error_code=None, enabled=True):
        aid = claim["assessment_id"]
        with self.coach.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM interview_assessments WHERE assessment_id=?", (aid,)
            ).fetchone()
            if not row:
                raise CoachError("assessment_stale")
            sid = row["interview_id"]
            if row["status"] != "running" or row["epoch"] != claim["epoch"]:
                if row["status"] == "cancelling" and row["epoch"] == claim["epoch"]:
                    conn.execute(
                        "UPDATE interview_assessments SET status='cancelled',finished_at=? WHERE assessment_id=?",
                        (now(), aid),
                    )
                return self.read(sid, aid)
            state = conn.execute(
                "SELECT consent_revision FROM interview_coach_state WHERE interview_id=?", (sid,)
            ).fetchone()
            review = conn.execute(
                "SELECT revision FROM interview_review_state WHERE interview_id=?", (sid,)
            ).fetchone()
            try:
                current, _ = self._input(sid)
                current_digest = digest(current)
            except CoachError:
                current_digest = None
            fresh = (
                enabled
                and current_digest == row["input_digest"]
                and state
                and review
                and state[0] == row["consent_revision"]
                and review[0] == row["review_revision"]
                and now() <= row["deadline_at"]
            )
            status = "succeeded" if result else "failed"
            if not fresh:
                status, result, error_code = "cancelled", None, "superseded"
            artifact_id = None
            if result:
                artifact_id = uuid.uuid4().hex
                report = {
                    "version": "2.6",
                    "assessment_id": aid,
                    "artifact_id": artifact_id,
                    "generated_at": now(),
                    "input": json.loads(row["input_snapshot"]),
                    "rubric": json.loads(row["rubric_snapshot"]),
                    "result": result,
                    "provenance": json.loads(row["provenance"]),
                    "purpose": "大学生自主训练参考，未经专家校准；不用于录用或心理判断。",
                }
                conn.execute(
                    "INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) VALUES (?,'interview_report',?,?,?)",
                    (
                        artifact_id,
                        "六维面试训练复盘",
                        encode(report),
                        encode({"interview_id": sid, "assessment_id": aid, "version": "2.6"}),
                    ),
                )
            conn.execute(
                "UPDATE interview_assessments SET status=?,artifact_id=?,error_code=?,finished_at=? WHERE assessment_id=?",
                (status, artifact_id, error_code, now(), aid),
            )
            ReviewRepository(self.storage)._event(
                sid,
                "assessment_finished",
                {"assessment_id": aid, "status": status, "error_code": error_code},
            )
            return self.read(sid, aid)

    def create_local(self, sid: str, command: AssessmentCommand):
        if command.mode != "local":
            raise CoachError("request_key_conflict")
        claim = self.claim(
            sid,
            command,
            {
                "provider_identity": "",
                "model": "local-evidence-only",
                "prompt_version": PROMPT_VERSION,
                "rules_version": RULES_VERSION,
            },
        )
        if not claim["execute"]:
            return claim["assessment"]
        return self.finish(claim, result=pending_result(claim["rubric"], claim["input"]))
