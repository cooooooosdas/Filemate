"""Purge dependent advice in caller transactions and invalidate restored authority."""

import json
import sqlite3
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ..repository import put
from .context import RUNTIME_ID
from .models import CoachProposal, CoachRunView
from .repository import REQUEST_TYPE, RESULT_TYPE, RUNTIME_TYPE, result_id

KINDS = {"source", "interview", "attempt", "submission", "position", "goal", "reflection"}


def _object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, RecursionError):
        return {}


def _require_transaction(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        raise RuntimeError("transaction_required")


def _matches(
    content: dict[str, Any], metadata: dict[str, Any], kind: str, identifiers: set[str]
) -> bool:
    dependencies = metadata.get("dependencies", {})
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    input_data = content.get("input", {})
    input_data = input_data if isinstance(input_data, dict) else {}
    scope = input_data.get("scope", {})
    selection = input_data.get("selection", {})
    scope = scope if isinstance(scope, dict) else {}
    selection = selection if isinstance(selection, dict) else {}
    refs = dependencies.get("feedback_refs")
    refs = refs if isinstance(refs, list) else []
    fields = {
        "source": [dependencies.get("sources"), scope.get("source_ids")],
        "goal": [dependencies.get("goal"), scope.get("goal_id")],
        "reflection": [dependencies.get("reflection_id"), input_data.get("reflection_id")],
        "interview": [dependencies.get("interview_ids"), selection.get("interview_ids")],
        "submission": [dependencies.get("submission_ids"), selection.get("submission_ids")],
        "position": [dependencies.get("position_id"), selection.get("position_id")],
        "attempt": [
            dependencies.get("attempt_ids"),
            *[r.get("attempt_id") for r in refs if isinstance(r, dict)],
        ],
    }[kind]
    if any(
        identifier in identifiers
        for value in fields
        for identifier in (value if isinstance(value, list) else [value])
        if isinstance(identifier, str)
    ):
        return True
    for key in ("baseline", "proposal"):
        proposal = content.get(key, {})
        facts = proposal.get("facts", []) if isinstance(proposal, dict) else []
        for fact in facts if isinstance(facts, list) else []:
            if not isinstance(fact, dict):
                continue
            fact_kind, record_id = fact.get("kind"), fact.get("record_id")
            if fact_kind == kind and isinstance(record_id, str) and record_id in identifiers:
                return True
            if (
                kind == "submission"
                and fact_kind == "compiler_result"
                and isinstance(record_id, str)
                and record_id in identifiers
            ):
                return True
            if (
                kind == "attempt"
                and isinstance(fact_kind, str)
                and fact_kind in {"answer", "feedback", "interview_answer", "interview_feedback"}
                and isinstance(record_id, str)
                and record_id.split(":", 1)[0] in identifiers
            ):
                return True
    return False


def _affected(
    conn: sqlite3.Connection, kind: str, record_ids: list[str]
) -> tuple[set[str], set[str], set[str], int]:
    if kind not in KINDS:
        raise ValueError("invalid_coach_dependency_kind")
    identifiers = set(record_ids)
    if not identifiers:
        return set(), set(), set(), 0
    works, plans, operations = set(), set(), set()
    # 删除遍历不能使用页面上限，否则旧派生结果会留在备份和导出中。
    for row in conn.execute(
        "SELECT artifact_id,content,metadata FROM artifacts WHERE artifact_type=?", (RESULT_TYPE,)
    ):
        if _matches(_object(row["content"]), _object(row["metadata"]), kind, identifiers):
            works.add(
                "learning-coach-request-"
                + row["artifact_id"].removeprefix("learning-coach-result-")
            )
    results = len(works)
    rows = conn.execute(
        "SELECT artifact_id,content,metadata,artifact_type FROM artifacts WHERE artifact_type IN ('study_plan','learning_coach_operation')"
    ).fetchall()
    for row in rows:
        if row["artifact_type"] != "study_plan":
            continue
        metadata = _object(row["metadata"])
        namespace = metadata.get("learning_coach", {})
        if isinstance(namespace, dict) and _matches({}, metadata, kind, identifiers):
            work = namespace.get("work_id")
            if isinstance(work, str):
                works.add(work)
    for row in rows:
        content, metadata = _object(row["content"]), _object(row["metadata"])
        if row["artifact_type"] == "study_plan":
            namespace = metadata.get("learning_coach", {})
            if (
                isinstance(namespace, dict)
                and isinstance(namespace.get("work_id"), str)
                and namespace["work_id"] in works
            ):
                plans.add(row["artifact_id"])
        else:
            after = content.get("after", {})
            if isinstance(after, dict) and any(
                isinstance(config, dict)
                and isinstance(config.get("learning_coach"), dict)
                and isinstance(config["learning_coach"].get("work_id"), str)
                and config["learning_coach"]["work_id"] in works
                for config in after.values()
            ):
                operations.add(row["artifact_id"])
    return works, plans, operations, results


def coach_dependency_impact(
    conn: sqlite3.Connection, *, kind: str, record_ids: list[str]
) -> dict[str, int]:
    _works, plans, operations, results = _affected(conn, kind, record_ids)
    return {
        "learning_coach_results": results,
        "learning_coach_plans": len(plans),
        "learning_coach_operations": len(operations),
    }


def invalidate_coach_dependencies(
    conn: sqlite3.Connection, *, kind: str, record_ids: list[str]
) -> dict[str, int]:
    _require_transaction(conn)
    works, plans, operations, results = _affected(conn, kind, record_ids)
    for work in works:
        row = conn.execute(
            "SELECT content FROM artifacts WHERE artifact_id=? AND artifact_type=?",
            (work, REQUEST_TYPE),
        ).fetchone()
        if row:
            record = _object(row[0])
            record.update(
                status="stale",
                model_status="interrupted"
                if record.get("requested_mode") == "llm"
                else "not_requested",
                safe_error_code="context_changed",
                admission_status="closed",
                claim_epoch=None,
                lease_until=0,
            )
            put(conn, work, REQUEST_TYPE, record, replace=True)
        conn.execute(
            "DELETE FROM artifacts WHERE artifact_id=? AND artifact_type=?",
            (result_id(work), RESULT_TYPE),
        )
        conn.execute(
            "DELETE FROM data_action_previews WHERE resource_id=? AND action LIKE 'learning_coach_%' AND result IS NULL",
            (work,),
        )
    for artifact in plans:
        conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (artifact,))
    for operation in operations:
        row = conn.execute(
            "SELECT content FROM artifacts WHERE artifact_id=?", (operation,)
        ).fetchone()
        record = _object(row[0])
        minimal = {
            key: record[key]
            for key in (
                "command_digest",
                "token_hash",
                "receipt",
                "restore_epoch",
                "issued_study_date",
                "undo_of",
            )
            if key in record
        }
        minimal["dependency_erased"] = True
        put(conn, operation, "learning_coach_operation", minimal, replace=True)
        conn.execute(
            "DELETE FROM data_action_previews WHERE resource_id=? AND result IS NULL", (operation,)
        )
    for row in conn.execute(
        "SELECT artifact_id,content FROM artifacts WHERE artifact_type='learning_orchestration_day'"
    ).fetchall():
        record = _object(row["content"])
        config = record.get("config", {})
        namespace = config.get("learning_coach", {}) if isinstance(config, dict) else {}
        if (
            isinstance(namespace, dict)
            and isinstance(namespace.get("work_id"), str)
            and namespace["work_id"] in works
        ):
            record.update(config=None, revision=int(record.get("revision", 0)) + 1)
            put(conn, row["artifact_id"], "learning_orchestration_day", record, replace=True)
    runtime_row = conn.execute(
        "SELECT content FROM artifacts WHERE artifact_id=?", (RUNTIME_ID,)
    ).fetchone()
    if runtime_row:
        runtime = _object(runtime_row[0])
        if runtime.get("model_work_id") in works:
            runtime.update(model_work_id=None, claim_epoch=None, lease_until=None)
            put(conn, RUNTIME_ID, RUNTIME_TYPE, runtime, replace=True)
    return {
        "learning_coach_results": results,
        "learning_coach_plans": len(plans),
        "learning_coach_operations": len(operations),
    }


def has_active_coach(conn: sqlite3.Connection) -> bool:
    return any(
        _object(row[0]).get("status") == "running"
        for row in conn.execute(
            "SELECT content FROM artifacts WHERE artifact_type=?", (REQUEST_TYPE,)
        )
    )


def _restore_put(
    conn: sqlite3.Connection, identifier: str, kind: str, content: dict[str, Any]
) -> None:
    row = conn.execute(
        "SELECT artifact_type FROM artifacts WHERE artifact_id=?", (identifier,)
    ).fetchone()
    if row and row[0] == kind:
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=? AND artifact_type=?",
            (json.dumps(content, ensure_ascii=False, allow_nan=False), identifier, kind),
        )
    else:
        put(conn, identifier, kind, content)


def normalize_restored_coach(conn: sqlite3.Connection) -> None:
    _require_transaction(conn)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts'").fetchone():
        return
    if not conn.execute(
        "SELECT 1 FROM artifacts WHERE artifact_type IN ('learning_coach_request','learning_coach_result','learning_coach_runtime','learning_coach_operation') LIMIT 1"
    ).fetchone():
        return
    epoch = uuid4().hex
    for row in conn.execute(
        "SELECT artifact_id,content FROM artifacts WHERE artifact_type=?", (REQUEST_TYPE,)
    ).fetchall():
        record = _object(row["content"])
        try:
            CoachRunView.model_validate(record)
        except ValidationError:
            record = {
                "work_id": row["artifact_id"],
                "request_key": "restored_invalid_record",
                "input_digest": "invalid",
                "context_revision": "0" * 64,
                "requested_mode": "rule",
                "effective_mode": "rule",
                "model_status": "interrupted",
                "status": "running",
                "restore_epoch": epoch,
            }
        if record.get("status") == "running" or not record.get("work_id"):
            record.update(
                status="interrupted",
                model_status="interrupted",
                safe_error_code="interrupted",
                admission_status="closed",
                claim_epoch=uuid4().hex,
                lease_until=0,
            )
            conn.execute(
                "DELETE FROM artifacts WHERE artifact_id=? AND artifact_type=?",
                (result_id(row["artifact_id"]), RESULT_TYPE),
            )
        elif record.get("status") == "ready":
            saved = conn.execute(
                "SELECT content FROM artifacts WHERE artifact_id=? AND artifact_type=?",
                (result_id(row["artifact_id"]), RESULT_TYPE),
            ).fetchone()
            try:
                CoachProposal.model_validate(_object(saved[0]).get("proposal") if saved else None)
            except ValidationError:
                record.update(status="stale", safe_error_code="context_changed")
                conn.execute(
                    "DELETE FROM artifacts WHERE artifact_id=? AND artifact_type=?",
                    (result_id(row["artifact_id"]), RESULT_TYPE),
                )
        _restore_put(conn, row["artifact_id"], REQUEST_TYPE, record)
    # 恢复只使旧授权失效，独立治理额度不在业务库中，不能在此退还。
    _restore_put(
        conn,
        RUNTIME_ID,
        RUNTIME_TYPE,
        {"restore_epoch": epoch, "model_work_id": None, "claim_epoch": None, "lease_until": None},
    )
    conn.execute(
        "DELETE FROM data_action_previews WHERE action IN ('learning_coach_confirm','learning_coach_undo')"
    )
