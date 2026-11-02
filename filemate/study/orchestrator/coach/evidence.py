"""Read only explicitly selected answer, feedback, graph and compiler evidence."""

import hashlib
import json
from typing import Any

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage
from filemate.interview_review.models import CONTENT_AREAS, validate_saved_analysis
from filemate.programming.problems import get_problem

from .models import FACT_TYPES, CoachFact, CoachSelection, OrchestratorError, ScopeRequest


def decode(raw: str | None, expected: type = dict) -> Any:
    """Reject oversized or malformed stored evidence without exposing its contents."""
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 1048576:
            raise ValueError()

        def invalid(value):
            raise ValueError("non_finite_json")

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate_json_key")
                result[key] = value
            return result

        value = json.loads(raw, parse_constant=invalid, object_pairs_hook=unique_object)
        if not isinstance(value, expected):
            raise TypeError()
        return value
    except (ValueError, TypeError, RecursionError):
        raise OrchestratorError("selected_evidence_invalid") from None


def fact(
    kind: str,
    identifier: str,
    original: Any,
    data: dict[str, Any],
    *,
    observed_at: str | None = None,
    label: str = "",
) -> CoachFact:
    revision = digest(original)
    return CoachFact(
        fact_id=f"{kind}:{identifier}:{revision[:16]}",
        kind=kind,
        record_id=identifier,
        revision=revision,
        observed_at=observed_at,
        display_text=str(label)[:500],
        data=FACT_TYPES[kind].model_validate(data),
    )


def read_wrong_record(
    read: SQLiteStorage, scope: ScopeRequest, identifier: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one selected question identity without reading its answer attempts."""
    conn = read._conn()
    row = conn.execute("SELECT * FROM wrong_questions WHERE wrong_id=?", (identifier,)).fetchone()
    if row is None or row["source_id"] not in scope.source_ids:
        raise OrchestratorError("selected_evidence_not_found", 404)
    item = dict(row)
    artifact = conn.execute(
        """SELECT source_id,artifact_type,
        CASE WHEN length(CAST(content AS BLOB))<=1048576 THEN content END AS content,
        CASE WHEN length(CAST(metadata AS BLOB))<=1048576 THEN metadata END AS metadata
        FROM artifacts WHERE artifact_id=?""",
        (item["artifact_id"],),
    ).fetchone()
    if (
        artifact is None
        or artifact["source_id"] != item["source_id"]
        or artifact["artifact_type"] != "questions"
    ):
        raise OrchestratorError("selected_evidence_invalid")
    questions = decode(artifact["content"], list)
    index = item["question_index"]
    if (
        type(index) is not int
        or not 0 <= index < len(questions)
        or not isinstance(questions[index], dict)
    ):
        raise OrchestratorError("selected_evidence_invalid")
    question = questions[index]
    metadata = decode(artifact["metadata"])
    if metadata.get("read_only_snapshot") or digest(question) != digest(decode(item["question"])):
        raise OrchestratorError("selected_evidence_invalid")
    return item, question


def selected_wrongs(
    read: SQLiteStorage, scope: ScopeRequest, selection: CoachSelection
) -> list[CoachFact]:
    conn, result = read._conn(), []
    for identifier in selection.wrong_ids:
        item, question = read_wrong_record(read, scope, identifier)
        index = item["question_index"]
        result.append(
            fact(
                "review",
                identifier,
                item,
                {
                    "artifact_id": item["artifact_id"],
                    "question_index": index,
                    "next_review_at": item["next_review_at"],
                    "schedule_status": item["schedule_status"],
                },
                observed_at=item["updated_at"],
                label="已保存的错题与复习安排",
            )
        )
        attempt = conn.execute(
            "SELECT * FROM quiz_attempts WHERE artifact_id=? AND question_index=? "
            "ORDER BY created_at DESC,attempt_id DESC LIMIT 1",
            (item["artifact_id"], index),
        ).fetchone()
        if attempt is not None:
            original = dict(attempt)
            if attempt["source_id"] != item["source_id"] or attempt["question_digest"] not in (
                "",
                digest(question),
            ):
                raise OrchestratorError("selected_evidence_invalid")
            result.append(
                fact(
                    "attempt",
                    attempt["attempt_id"],
                    {"attempt": original, "question": question},
                    {
                        "artifact_id": item["artifact_id"],
                        "question_index": index,
                        "question_excerpt": str(
                            question.get("stem") or question.get("question") or ""
                        )[:500],
                        "answer_excerpt": str(attempt["user_answer"])[:500],
                        "purpose": attempt["purpose"],
                        "judgement_status": attempt["judgement_status"],
                    },
                    observed_at=attempt["created_at"],
                    label="用户独立作答片段",
                )
            )
        if item["error_cause_source"] == "user" and item["error_cause"] != "unconfirmed":
            result.append(
                fact(
                    "cause",
                    identifier,
                    item,
                    {"cause": item["error_cause"], "note": str(item["error_cause_note"])[:300]},
                    observed_at=item["diagnosed_at"],
                    label="用户确认的错因",
                )
            )
    return result


def selected_interviews(
    read: SQLiteStorage, scope: ScopeRequest, selection: CoachSelection, goal_type: str | None
) -> tuple[list[CoachFact], list[dict[str, Any]]]:
    conn, result, bindings = read._conn(), [], []
    if goal_type == "exam" and selection.interview_ids:
        raise OrchestratorError("interview_evidence_not_for_course", 422)
    for identifier in selection.interview_ids:
        session = conn.execute(
            """SELECT i.interview_id,i.agent_run_id,i.target_role,i.scenario,i.status,i.updated_at,
            r.context_refs FROM interview_sessions i LEFT JOIN agent_runs r ON r.run_id=i.agent_run_id
            WHERE i.interview_id=?""",
            (identifier,),
        ).fetchone()
        if session is None:
            raise OrchestratorError("selected_evidence_not_found", 404)
        refs = decode(session["context_refs"] or "{}")
        if refs.get("source_id") is not None and refs.get("source_id") not in scope.source_ids:
            raise OrchestratorError("selected_evidence_not_found", 404)
        bindings.append(dict(session))
        for ref in (r for r in selection.feedback_refs if r.interview_id == identifier):
            attempt = conn.execute(
                "SELECT * FROM interview_answer_attempts WHERE interview_id=? AND attempt_id=?",
                (identifier, ref.attempt_id),
            ).fetchone()
            if attempt is None or ref.feedback_item_id not in CONTENT_AREAS:
                raise OrchestratorError("selected_evidence_not_found", 404)
            latest = conn.execute(
                "SELECT attempt_id FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1",
                (attempt["turn_id"],),
            ).fetchone()
            run = conn.execute(
                "SELECT * FROM interview_coach_analysis_runs WHERE attempt_id=? ORDER BY attempt_seq DESC LIMIT 1",
                (ref.attempt_id,),
            ).fetchone()
            if (
                latest["attempt_id"] != ref.attempt_id
                or run is None
                or run["status"] != "succeeded"
                or run["run_id"] != ref.expected_revision
            ):
                raise OrchestratorError("context_changed")
            try:
                analysis = validate_saved_analysis(
                    decode(run["evaluation"])["content_analysis"], attempt["answer"]
                )
            except (KeyError, ValueError, TypeError):
                raise OrchestratorError("selected_evidence_invalid") from None
            area = analysis["areas"][ref.feedback_item_id]
            if not area["evidence"]:
                raise OrchestratorError("feedback_evidence_insufficient")
            result.append(
                fact(
                    "interview_feedback",
                    ref.attempt_id + ":" + ref.feedback_item_id,
                    {"session": dict(session), "attempt": dict(attempt), "run": dict(run)},
                    {
                        "interview_id": identifier,
                        "attempt_id": ref.attempt_id,
                        "feedback_item_id": ref.feedback_item_id,
                        "quote": area["evidence"],
                        "suggestion": area["suggestion"][:500],
                    },
                    observed_at=run["created_at"],
                    label="所选模型反馈及其原回答依据",
                )
            )
    return result, bindings


def selected_submissions(read: SQLiteStorage, selection: CoachSelection) -> list[CoachFact]:
    result = []
    for identifier in selection.submission_ids:
        row = (
            read._conn()
            .execute(
                """SELECT c.*,CASE WHEN length(CAST(a.content AS BLOB))<=1048576 THEN a.content END AS content FROM coding_submissions c
            JOIN artifacts a ON a.artifact_id=c.artifact_id AND a.artifact_type='coding_submission'
            WHERE c.submission_id=? AND c.active=1 AND c.status='completed' """,
                (identifier,),
            )
            .fetchone()
        )
        if row is None:
            raise OrchestratorError("selected_evidence_not_found", 404)
        payload = decode(row["content"])
        outcome = payload.get("result")
        try:
            problem = get_problem(row["problem_id"])
            valid = (
                problem["version"] == row["problem_version"]
                and isinstance(payload.get("code"), str)
                and hashlib.sha256(payload["code"].encode()).hexdigest()
                == payload.get("code_sha256")
                and isinstance(outcome, dict)
                and outcome.get("provider") in {"windows-appcontainer-msvc", "linux-gvisor-gcc"}
                and outcome.get("verdict") in {"AC", "WA", "CE", "RE", "TLE", "MLE", "OLE"}
            )
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            raise OrchestratorError("compiler_evidence_unavailable")
        result.append(
            fact(
                "compiler_result",
                identifier,
                dict(row),
                {
                    "problem_id": row["problem_id"],
                    "problem_version": row["problem_version"],
                    "verdict": outcome["verdict"],
                },
                observed_at=row["updated_at"],
                label="已保存的编译器判题结果",
            )
        )
    return result


def selected_position(
    read: SQLiteStorage, selection: CoachSelection, goal_type: str | None
) -> list[CoachFact]:
    if selection.position_id is None:
        return []
    if goal_type != "job":
        raise OrchestratorError("position_evidence_requires_job_goal", 422)
    row = (
        read._conn()
        .execute(
            "SELECT * FROM career_positions WHERE position_id=? AND active=1",
            (selection.position_id,),
        )
        .fetchone()
    )
    if row is None:
        raise OrchestratorError("selected_evidence_not_found", 404)
    from filemate.career.models import Position

    try:
        position = Position.model_validate(decode(row["payload"]))
        return [
            fact(
                "position_requirement",
                f"{selection.position_id}:{index}",
                dict(row),
                {
                    "position_id": selection.position_id,
                    "requirement_index": index,
                    "label": position.requirements[index].label,
                    "quote": position.requirements[index].evidence,
                },
                observed_at=row["updated_at"],
                label="用户选定的岗位要求",
            )
            for index in selection.requirement_indices
        ]
    except (ValueError, TypeError, IndexError):
        raise OrchestratorError("selected_evidence_invalid") from None


def selected_concepts(
    read: SQLiteStorage, scope: ScopeRequest, selection: CoachSelection, snapshot: Any
) -> list[CoachFact]:
    if not selection.concept_ids:
        return []
    if scope.course_id is None:
        raise OrchestratorError("explicit_course_required", 422)
    from filemate.course_graph.projection import valid_evidence

    result = []
    selected = set()
    for identifier in selection.concept_ids:
        root = (
            read._conn()
            .execute(
                "SELECT * FROM kg_concepts WHERE course_id=? AND concept_id=? AND status='confirmed'",
                (scope.course_id, identifier),
            )
            .fetchone()
        )
        if root is None:
            raise OrchestratorError("selected_evidence_not_found", 404)
        if root["canonical_id"]:
            root = (
                read._conn()
                .execute(
                    "SELECT * FROM kg_concepts WHERE course_id=? AND concept_id=? AND status='confirmed'",
                    (scope.course_id, root["canonical_id"]),
                )
                .fetchone()
            )
        if root is None:
            raise OrchestratorError("selected_evidence_invalid")
        slots = ",".join("?" for _ in scope.source_ids) or "NULL"
        rows = read._conn().execute(
            f"""SELECT e.* FROM kg_evidence e JOIN kg_concepts member
            ON member.concept_id=e.concept_id AND member.course_id=e.course_id
            WHERE e.course_id=? AND (member.concept_id=? OR member.canonical_id=?)
            AND member.status='confirmed' AND e.status='confirmed' AND e.source_id IN ({slots})
            ORDER BY e.evidence_id LIMIT 200""",
            (scope.course_id, root["concept_id"], root["concept_id"], *scope.source_ids),
        )
        cache = {}
        refs = [
            dict(row)
            for row in rows
            if valid_evidence(read, read._conn(), scope.course_id, row, cache)
        ]
        if not refs:
            raise OrchestratorError("concept_evidence_unavailable")
        selected.add(root["concept_id"])
        if root["concept_id"] in {f.record_id for f in result}:
            continue
        result.append(
            fact(
                "concept",
                root["concept_id"],
                {"node": dict(root), "refs": refs},
                {
                    "course_id": scope.course_id,
                    "label": root["label"][:240],
                    "source_ids": sorted({r["source_id"] for r in refs}),
                },
                label="已确认且来源有效的概念",
            )
        )
    for item in snapshot.facts["graph"]:
        relation = item.get("relation") or {}
        if (
            item.get("relation_id")
            and relation.get("from_id") in selected
            and relation.get("to_id") in selected
        ):
            result.append(
                fact(
                    "relation",
                    item["relation_id"],
                    item,
                    {
                        "course_id": scope.course_id,
                        "from_id": relation["from_id"],
                        "to_id": relation["to_id"],
                        "relation_type": relation["type"],
                        "source_ids": [item["source_id"]],
                    },
                    label="已确认且来源有效的概念关系",
                )
            )
    return result
