"""Durable claims and minimal results with independent restore and request epochs."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage

from ..models import Clock, aware, utc_now
from ..repository import atomic, load, put
from .context import RUNTIME_ID, CoachContextReader, read_restore_epoch
from .models import (
    CoachContext,
    CoachInput,
    CoachProposal,
    CoachRequest,
    CoachRunView,
    OrchestratorError,
)
from .prompts import PROMPT_VERSION
from .rules import build_rule_proposal
from .settings import LEASE_SECONDS, enabled

REQUEST_TYPE = "learning_coach_request"
RESULT_TYPE = "learning_coach_result"
RUNTIME_TYPE = "learning_coach_runtime"
ERROR_CODES = {
    "cancelled",
    "interrupted",
    "context_changed",
    "quota_exceeded",
    "credentials_missing",
    "timeout",
    "invalid_output",
    "provider_unavailable",
    "admission_unconfirmed",
    "governance_unavailable",
    "admission_conflict",
}


def work_id(key: str) -> str:
    return "learning-coach-request-" + digest(key)


def result_id(identifier: str) -> str:
    return "learning-coach-result-" + identifier.removeprefix("learning-coach-request-")


def request_digest(body: CoachRequest) -> str:
    payload = body.model_dump(mode="json")
    if body.mode == "llm":
        return digest({"request": payload, "prompt_version": PROMPT_VERSION})
    return digest(payload)


@dataclass(frozen=True)
class CoachClaim:
    view: CoachRunView
    claimed: bool
    claim_epoch: str | None = None
    lease_until: float | None = None


class CoachRepository:
    def __init__(self, storage: SQLiteStorage, *, clock: Clock | None = None) -> None:
        self.storage = storage
        self.clock = clock or utc_now

    def _now(self) -> datetime:
        return aware(self.clock())

    def _save(self, conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        put(conn, record["work_id"], REQUEST_TYPE, record, replace=True)

    def _release(self, conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        runtime = load(conn, RUNTIME_ID, RUNTIME_TYPE)
        if (
            runtime
            and runtime.get("model_work_id") == record["work_id"]
            and runtime.get("claim_epoch") == record["claim_epoch"]
        ):
            runtime.update(model_work_id=None, claim_epoch=None, lease_until=None)
            put(conn, RUNTIME_ID, RUNTIME_TYPE, runtime, replace=True)

    def _terminal(
        self, conn: sqlite3.Connection, record: dict[str, Any], status: str, error: str
    ) -> None:
        record.update(status=status, safe_error_code=error, admission_status="closed")
        record["model_status"] = (
            "not_requested"
            if record["requested_mode"] == "rule"
            else "cancelled"
            if status == "cancelled"
            else "failed"
            if status == "failed"
            else "interrupted"
        )
        conn.execute(
            "DELETE FROM artifacts WHERE artifact_id=? AND artifact_type=?",
            (result_id(record["work_id"]), RESULT_TYPE),
        )
        self._save(conn, record)
        self._release(conn, record)

    def _expire(self, conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        if record["status"] == "running" and (
            record["lease_until"] <= self._now().timestamp()
            or record["restore_epoch"] != read_restore_epoch(conn)
        ):
            self._terminal(conn, record, "interrupted", "interrupted")

    def _view(self, conn: sqlite3.Connection, record: dict[str, Any]) -> CoachRunView:
        proposal = None
        if record["status"] == "ready":
            saved = load(conn, result_id(record["work_id"]), RESULT_TYPE)
            if not saved:
                self._terminal(conn, record, "stale", "context_changed")
            else:
                try:
                    proposal = CoachProposal.model_validate(saved["proposal"])
                    current = CoachContextReader(self.storage).read_in_transaction(
                        self.storage,
                        CoachInput.model_validate(saved["input"]),
                        as_of=self._now(),
                        restore_epoch=read_restore_epoch(conn),
                        historical_read=True,
                    )
                    revisions = {
                        (fact.kind, fact.record_id): fact.revision for fact in current.facts
                    }
                    if any(
                        revisions.get((fact.kind, fact.record_id)) != fact.revision
                        for fact in proposal.facts
                    ):
                        raise OrchestratorError("context_changed")
                except (KeyError, ValidationError, TypeError, OrchestratorError):
                    self._terminal(conn, record, "stale", "context_changed")
                    proposal = None
        fields = (
            "work_id",
            "request_key",
            "status",
            "requested_mode",
            "effective_mode",
            "model_status",
            "safe_error_code",
            "context_revision",
            "provider",
            "model",
        )
        return CoachRunView(
            **{k: record.get(k) for k in fields},
            proposal=proposal,
            prompt_version=record.get("prompt_version", "learning-coach-v1"),
        )

    def find(self, request_key: str, input_digest: str | None = None) -> CoachRunView | None:
        with atomic(self.storage) as conn:
            record = load(conn, work_id(request_key), REQUEST_TYPE)
            if record is None:
                return None
            if input_digest is not None and input_digest != record.get("input_digest"):
                raise OrchestratorError("request_conflict")
            self._expire(conn, record)
            return self._view(conn, record)

    def claim(self, body: CoachRequest, context: CoachContext) -> CoachClaim:
        with atomic(self.storage) as conn:
            identifier = work_id(body.request_key)
            old = load(conn, identifier, REQUEST_TYPE)
            if old:
                if old["input_digest"] != request_digest(body):
                    raise OrchestratorError("request_conflict")
                self._expire(conn, old)
                return CoachClaim(self._view(conn, old), False)
            if not enabled():
                raise OrchestratorError("learning_coach_disabled", 503)
            now = self._now()
            epoch = read_restore_epoch(conn)
            current = CoachContextReader(self.storage).read_in_transaction(
                self.storage, context.input, as_of=now, restore_epoch=epoch
            )
            if current.context_revision != context.context_revision:
                raise OrchestratorError("context_changed")
            runtime = load(conn, RUNTIME_ID, RUNTIME_TYPE) or {"restore_epoch": epoch}
            if body.mode == "llm" and runtime.get("model_work_id"):
                owner = load(conn, runtime["model_work_id"], REQUEST_TYPE)
                if owner:
                    self._expire(conn, owner)
                if owner and owner["status"] == "running":
                    raise OrchestratorError("model_already_running", 429)
            claim_epoch = uuid4().hex
            record = {
                "work_id": identifier,
                "request_key": body.request_key,
                "input_digest": request_digest(body),
                "context_revision": context.context_revision,
                "restore_epoch": epoch,
                "claim_epoch": claim_epoch,
                "lease_until": now.timestamp() + LEASE_SECONDS,
                "created_at": now.isoformat(),
                "status": "running",
                "requested_mode": body.mode,
                "effective_mode": "rule",
                "model_status": "running" if body.mode == "llm" else "not_requested",
                "safe_error_code": None,
                "admission_status": "pending",
                "provider": None,
                "model": None,
                "prompt_version": PROMPT_VERSION,
            }
            if body.mode == "llm":
                runtime.update(
                    model_work_id=identifier,
                    claim_epoch=claim_epoch,
                    lease_until=record["lease_until"],
                )
            put(conn, RUNTIME_ID, RUNTIME_TYPE, runtime, replace=True)
            put(conn, identifier, REQUEST_TYPE, record)
            metadata = {
                "dependencies": {
                    "goal": context.input.scope.goal_id,
                    "reflection_id": context.input.reflection_id,
                    "sources": context.input.scope.source_ids,
                    **context.input.selection.model_dump(mode="json"),
                }
            }
            baseline = build_rule_proposal(context)
            put(
                conn,
                result_id(identifier),
                RESULT_TYPE,
                {
                    "input": context.input.model_dump(mode="json"),
                    "baseline": baseline.model_dump(mode="json"),
                },
            )
            conn.execute(
                "UPDATE artifacts SET metadata=? WHERE artifact_id=?",
                (self.storage._dump_json(metadata), result_id(identifier)),
            )
            conn.executemany(
                "INSERT INTO kg_learning_artifact_sources VALUES(?,?)",
                [(result_id(identifier), sid) for sid in context.input.scope.source_ids],
            )
            return CoachClaim(self._view(conn, record), True, claim_epoch, record["lease_until"])

    def authorize_claim(self, identifier: str, claim_epoch: str, *, admitted: bool) -> bool:
        with atomic(self.storage) as conn:
            record = load(conn, identifier, REQUEST_TYPE)
            if not record or record["claim_epoch"] != claim_epoch:
                return False
            self._expire(conn, record)
            if record["status"] != "running":
                return False
            if not admitted:
                self._terminal(conn, record, "interrupted", "admission_unconfirmed")
                return False
            record["admission_status"] = "admitted"
            self._save(conn, record)
            return True

    def reject(self, identifier: str, claim_epoch: str, error: str) -> None:
        with atomic(self.storage) as conn:
            record = load(conn, identifier, REQUEST_TYPE)
            if record and record["claim_epoch"] == claim_epoch and record["status"] == "running":
                self._terminal(
                    conn,
                    record,
                    "failed",
                    error if error in ERROR_CODES else "provider_unavailable",
                )

    def set_provider(self, identifier: str, claim_epoch: str, provider: str, model: str) -> None:
        with atomic(self.storage) as conn:
            record = load(conn, identifier, REQUEST_TYPE)
            if record and record["claim_epoch"] == claim_epoch and record["status"] == "running":
                record.update(provider=str(provider)[:80], model=str(model)[:120])
                self._save(conn, record)

    def active(self, identifier: str, claim_epoch: str) -> bool:
        with self.storage.read_snapshot() as read:
            conn = read._conn()
            record = load(conn, identifier, REQUEST_TYPE)
            return bool(
                record
                and record["status"] == "running"
                and record["claim_epoch"] == claim_epoch
                and record["lease_until"] > self._now().timestamp()
                and record["restore_epoch"] == read_restore_epoch(conn)
                and conn.execute(
                    "SELECT 1 FROM artifacts WHERE artifact_id=? AND artifact_type=?",
                    (result_id(identifier), RESULT_TYPE),
                ).fetchone()
            )

    def finish(
        self,
        identifier: str,
        claim_epoch: str,
        proposal: CoachProposal,
        *,
        model_status: str,
        safe_error_code: str | None = None,
    ) -> bool:
        with atomic(self.storage) as conn:
            record = load(conn, identifier, REQUEST_TYPE)
            if not record or record["claim_epoch"] != claim_epoch:
                return False
            self._expire(conn, record)
            if record["status"] != "running":
                return False
            saved = load(conn, result_id(identifier), RESULT_TYPE)
            try:
                if record["admission_status"] != "admitted" or saved is None:
                    raise OrchestratorError("context_changed")
                current = CoachContextReader(self.storage).read_in_transaction(
                    self.storage,
                    CoachInput.model_validate(saved["input"]),
                    as_of=self._now(),
                    restore_epoch=read_restore_epoch(conn),
                )
                if current.context_revision != record["context_revision"]:
                    raise OrchestratorError("context_changed")
            except (OrchestratorError, ValidationError, KeyError, TypeError):
                self._terminal(conn, record, "stale", "context_changed")
                return False
            put(
                conn,
                result_id(identifier),
                RESULT_TYPE,
                {"input": saved["input"], "proposal": proposal.model_dump(mode="json")},
                replace=True,
            )
            record.update(
                status="ready",
                model_status=model_status,
                effective_mode="rule"
                if record["requested_mode"] == "rule"
                else "model"
                if model_status == "succeeded"
                else "rule_fallback",
                safe_error_code=(
                    safe_error_code if safe_error_code in ERROR_CODES else "provider_unavailable"
                )
                if model_status == "failed"
                else None,
            )
            self._save(conn, record)
            self._release(conn, record)
            return True

    def cancel(self, request_key: str) -> CoachRunView:
        with atomic(self.storage) as conn:
            record = load(conn, work_id(request_key), REQUEST_TYPE)
            if not record:
                raise OrchestratorError("coach_request_not_found", 404)
            self._expire(conn, record)
            if record["status"] == "running":
                self._terminal(conn, record, "cancelled", "cancelled")
            return self._view(conn, record)
