"""Run four isolated domain journeys and record synthetic comparison conditions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.evaluate_learning_coach import evaluate_case
from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachRepository
from filemate.llm_client import LLMConfig
from filemate.programming import service as programming_service
from filemate.programming.problems import get_problem
from filemate.programming.repository import CodingRepository
from filemate.programming.windows_sandbox import SandboxUnavailable
from filemate.runtime_governance import resource_scope
from filemate.study.orchestrator.coach.commands import CoachCommands, CoachDayReader
from filemate.study.orchestrator.coach.context import CoachContextReader
from filemate.study.orchestrator.coach.models import (
    CoachConfirm,
    CoachDraft,
    CoachRequest,
    OrchestratorError,
)
from filemate.study.orchestrator.coach.service import CoachService
from filemate.study.orchestrator.models import UndoConfirmRequest
from filemate.wrongbook.repository import ReviewRepository
from scripts.acceptance.learning_coach_fixture import protected_history, seed_coach, source_identity
from scripts.acceptance.orchestrator_runtime import output_path, write_json


class SyntheticExplanationRunner:
    def __init__(self, output: dict[str, Any], *, fail: bool = False) -> None:
        self.output = output
        self.fail = fail
        self.calls = 0

    def run(self, config: LLMConfig, scope: Any, **kwargs: Any) -> dict[str, Any]:
        """Return explicitly synthetic schema output without a network transport."""
        self.calls += 1
        if self.fail:
            return {"error_code": "provider_unavailable"}
        return {"output": self.output}


def rehearse_interview(store: SQLiteStorage, action: dict[str, Any]) -> dict[str, Any]:
    """Execute the accepted native interview action and preserve its prior answer."""
    repository = CoachRepository(store)
    interview_id = action["target_ref"]["id"]
    snapshot = repository.snapshot(interview_id)
    original = snapshot.current_attempt
    assert original and original.attempt_id == action["target_ref"]["attempt_id"]
    original_row = dict(
        store._conn()
        .execute(
            "SELECT * FROM interview_answer_attempts WHERE attempt_id=?", (original.attempt_id,)
        )
        .fetchone()
    )
    command = SubmitAnswer(
        answer="结论是队列遵循先进先出。我用空队列、单元素和出入队交替三个用例验证边界。",
        question_index=original.question_index,
        expected_attempt_id=original.attempt_id,
        expected_revision=snapshot.revision,
        request_key="synthetic_journey_original_interview_01",
    )
    submitted = repository.submit(interview_id, command)
    current = submitted.snapshot.current_attempt
    assert current and current.attempt_id != original.attempt_id
    count = store._conn().execute("SELECT COUNT(*) FROM interview_answer_attempts").fetchone()[0]
    replay = repository.submit(interview_id, command)
    reread = repository.snapshot(interview_id).current_attempt
    preserved = (
        dict(
            store._conn()
            .execute(
                "SELECT * FROM interview_answer_attempts WHERE attempt_id=?", (original.attempt_id,)
            )
            .fetchone()
        )
        == original_row
    )
    assert replay.receipt == submitted.receipt and reread and reread.answer == command.answer
    return {
        "kind": "interview",
        "action_key": action["action_key"],
        "interview_id": interview_id,
        "original_attempt_id": original.attempt_id,
        "new_attempt_id": current.attempt_id,
        "persisted": reread.attempt_id == current.attempt_id,
        "original_answer_preserved": preserved,
        "request_replay_created_attempts": store._conn()
        .execute("SELECT COUNT(*) FROM interview_answer_attempts")
        .fetchone()[0]
        - count,
        "status": "completed",
        "model_analysis_requested": False,
    }


def practice_problem(case: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """Submit new code through the native sandbox without manufacturing a verdict."""
    repository = CodingRepository(case["store"])
    original = repository.get(case["original_submission_id"])
    problem = get_problem(action["target_ref"]["id"])
    assert problem["version"] == action["target_ref"]["problem_version"]
    assert problem["id"] == "array-sum"
    code = (
        "#include <iostream>\n"
        "int main() {\n"
        "    int count;\n"
        "    std::cin >> count;\n"
        "    long long total = 0;\n"
        "    for (int index = 0; index < count; ++index) {\n"
        "        long long value;\n"
        "        std::cin >> value;\n"
        "        total += value;\n"
        "    }\n"
        "    std::cout << total << '\\n';\n"
        "}\n"
    )
    submission = repository.create(problem, code, "synthetic_journey_original_programming_01")
    count = len(repository.list())
    replay = repository.create(problem, code, "synthetic_journey_original_programming_01")
    assert replay["submission_id"] == submission["submission_id"]
    replay_count = len(repository.list()) - count
    dependency = None
    try:
        result = programming_service.execute(repository, submission["submission_id"])
    except SandboxUnavailable as error:
        if not isinstance(error.__cause__, (SandboxUnavailable, OSError)):
            raise
        result = repository.get(submission["submission_id"])
        dependency = "programming_sandbox_unavailable"
    reread = repository.get(submission["submission_id"])
    verdict = result["result"].get("verdict")
    if dependency is None:
        assert result["status"] == "completed" and verdict == "AC", result["result"]
        assert result["result"]["passed"] == result["result"]["total"] > 0
    return {
        "kind": "programming",
        "action_key": action["action_key"],
        "problem_id": problem["id"],
        "original_submission_id": original["submission_id"],
        "new_submission_id": submission["submission_id"],
        "persisted": reread["result"] == result["result"] and reread["code"] == code,
        "original_submission_preserved": digest(repository.get(original["submission_id"]))
        == digest(original),
        "request_replay_created_submissions": replay_count,
        "execution_attempted": True,
        "synthetic_judge_result": bool(result["result"].get("synthetic_fixture")),
        "status": "dependency_unavailable" if dependency else "completed",
        "dependency": dependency,
        "stored_status": reread["status"],
        "verdict": verdict,
        "provider": result["result"].get("provider"),
        "passed": result["result"].get("passed"),
        "total": result["result"].get("total"),
    }


def run_journey(root: Path, goal_type: str) -> dict[str, Any]:
    """Execute actual storage, evidence, proposal, confirmation and completion logic."""
    case = seed_coach(root, goal_type)
    with resource_scope(
        case["budget_store"], "local", "local", managed_db_path=case["store"].db_path
    ):
        return run_journey_case(case)


def run_journey_case(case: dict[str, Any]) -> dict[str, Any]:
    """Keep every synthetic mutation within the same owned resource ledger."""
    root, goal_type = case["root"], case["goal_type"]
    store, body = case["store"], case["input"]
    try:
        clock = lambda: case["now"]
        reader = CoachContextReader(store, clock=clock)
        context = reader.read(body)
        before = protected_history(store)
        plans_before = store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0]
        service = CoachService(store, clock=clock)

        def request(key: str, mode: str) -> CoachRequest:
            return CoachRequest(
                input=body,
                expected_context_revision=context.context_revision,
                request_key=key,
                mode=mode,
                allow_external_model=mode == "llm",
                consent_digest=context.external_digest if mode == "llm" else None,
            )

        rule_request = request("synthetic_journey_rule_0001", "rule")
        rule = service.request(rule_request)
        assert rule.proposal and rule.proposal.new_actions
        assert service.get(rule_request.request_key).proposal == rule.proposal
        output = {
            "explanations": [
                explanation.model_dump(exclude={"text"}, mode="json")
                for explanation in rule.proposal.explanations
            ],
            "task_order": [],
            "new_actions": [],
        }
        known_tasks = {
            task.task_id for task in context.projection.tasks + context.projection.completed
        }
        for explanation in output["explanations"]:
            if explanation["task_id"] not in known_tasks:
                explanation["task_id"] = None
        runner = SyntheticExplanationRunner(output)
        model_service = CoachService(
            store,
            clock=clock,
            runner=runner,
            config_factory=lambda: LLMConfig(api_key="synthetic-fixture-no-network"),
        )
        model = model_service.request(request("synthetic_journey_model_0001", "llm"))
        assert model.model_status == "succeeded" and runner.calls == 1, (
            model.model_status,
            model.safe_error_code,
            runner.calls,
        )
        assert model.proposal is not None
        assert model.proposal.new_actions == rule.proposal.new_actions
        failed_runner = SyntheticExplanationRunner({}, fail=True)
        fallback = CoachService(
            store,
            clock=clock,
            runner=failed_runner,
            config_factory=lambda: LLMConfig(api_key="synthetic-fixture-no-network"),
        ).request(request("synthetic_journey_failure_001", "llm"))
        assert fallback.model_status == "failed" and fallback.effective_mode == "rule_fallback"

        draft = CoachDraft(
            work_id=rule.work_id,
            expected_context_revision=rule.context_revision,
            days=[day.model_dump(exclude={"schedule"}) for day in rule.proposal.days],
            new_actions=rule.proposal.new_actions,
            overlap_choices=[],
        )
        edits = []
        previous = draft.new_actions[0].minutes
        draft.new_actions[0].minutes = previous + 1
        edits.append(
            {
                "field": "new_actions[0].minutes",
                "before": previous,
                "after": draft.new_actions[0].minutes,
            }
        )
        commands = CoachCommands(store, clock=clock)
        preview = commands.preview(draft)
        assert (
            store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0] == plans_before
        )
        confirm = CoachConfirm.model_validate(
            draft.model_dump()
            | {
                "request_key": "synthetic_journey_confirm_01",
                "confirmation_token": preview.confirmation_token,
                "confirmed": True,
            }
        )
        receipt = commands.confirm(confirm)
        plans_after = store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0]
        replay = commands.confirm(confirm)
        assert replay == receipt
        replay_count = (
            store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0] - plans_after
        )
        undo = commands.preview_undo(receipt.operation_id)
        completed = store.set_study_plan_day(receipt.plan_id, 0, True)
        question = store.get_artifact(case["wrong_artifact"])["content"][0]
        review_repository = ReviewRepository(store, clock=clock)
        answer_command = {
            "artifact_id": case["wrong_artifact"],
            "question_index": 0,
            "expected_question": question,
            "user_answer": "A",
            "request_key": "synthetic_journey_reanswer_01",
        }
        answer_receipt = review_repository.submit(answer_command)
        answer_row = (
            store._conn()
            .execute(
                "SELECT user_answer FROM quiz_attempts WHERE attempt_id=?",
                (answer_receipt["attempt_id"],),
            )
            .fetchone()
        )
        attempts_before_replay = (
            store._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
        )
        assert review_repository.submit(answer_command) == answer_receipt
        assert (
            store._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
            == attempts_before_replay
        )
        domain_execution = [
            {
                "kind": "wrongbook",
                "attempt_id": answer_receipt["attempt_id"],
                "persisted": answer_row["user_answer"] == answer_command["user_answer"],
                "status": "completed",
                "request_replay_created_attempts": 0,
            }
        ]
        saved = store.get_study_plan(receipt.plan_id)
        for day in saved["plan_data"]["daily_plan"]:
            for action in day["training_actions"]:
                if action["action"] == "rehearse_interview":
                    domain_execution.append(rehearse_interview(store, action))
                elif action["action"] == "practice_problem":
                    domain_execution.append(practice_problem(case, action))
        expected_domains = {"wrongbook"}
        if goal_type in {"competition", "job"}:
            expected_domains.add("interview")
        if goal_type in {"job", "skill"}:
            expected_domains.add("programming")
        assert {item["kind"] for item in domain_execution} == expected_domains
        assert all(item["persisted"] for item in domain_execution)
        dependencies = sorted(
            {item["dependency"] for item in domain_execution if item.get("dependency")}
        )
        compiler_runs = [item for item in domain_execution if item["kind"] == "programming"]
        compiler_execution = "not_requested"
        if compiler_runs:
            compiler_execution = (
                "dependency_unavailable" if dependencies else "native_original_executor"
            )
        reread = CoachDayReader(store, clock=clock).read(body.days[0].study_date)
        rejected = False
        try:
            commands.confirm_undo(
                receipt.operation_id,
                UndoConfirmRequest(
                    request_key="synthetic_journey_undo_0001",
                    confirmation_token=undo.confirmation_token,
                    confirmed=True,
                ),
            )
        except OrchestratorError as error:
            rejected = error.status_code == 409
        assert 0 in store.get_study_plan(receipt.plan_id)["completed_days"]
        after = protected_history(store)
        common = {
            "data_type": "synthetic",
            "context": context.model_dump(mode="json"),
            "current_fact_revisions": {fact.fact_id: fact.revision for fact in context.facts},
            "protected_before": before,
            "protected_after": after,
        }
        conditions = {}
        cases = []
        for condition, proposal, edit_events in (
            ("rule", rule.proposal, []),
            ("model_explanation", model.proposal, []),
            ("manual_edit", rule.proposal.model_copy(deep=True), edits),
        ):
            if condition == "manual_edit":
                proposal.new_actions = draft.new_actions
                for day in proposal.days:
                    impact = next(
                        row
                        for row in preview.changes["days"]
                        if row["study_date"] == day.study_date
                    )
                    day.schedule.estimated_minutes = impact["estimated_minutes"]
                    selected = {task["task_id"]: task for task in impact["selected"]}
                    for task in day.schedule.selected:
                        task.estimated_minutes = selected[task.task_id]["estimated_minutes"]
            evaluation = common | {
                "case_id": goal_type,
                "condition": condition,
                "proposal": proposal.model_dump(mode="json"),
                "edit_events": edit_events,
            }
            conditions[condition] = evaluate_case(evaluation)
            cases.append(evaluation)
        result = {
            "data_type": "synthetic",
            "goal_type": goal_type,
            "rule_status": rule.status,
            "model_status": model.model_status,
            "model_transport": "synthetic_runner",
            "real_supplier_tested": False,
            "context_compiler_evidence": case["compiler_execution"],
            "compiler_execution": compiler_execution,
            "domain_execution": domain_execution,
            "dependencies": dependencies,
            "status": "CONDITIONAL_PASS" if dependencies else "PASS",
            "saved_plan_count": plans_after - plans_before,
            "replay_created_plans": replay_count,
            "original_completion_recorded": 0 in completed["completed_days"],
            "reread_completed_count": len(reread.completed),
            "undo_after_progress_rejected": rejected,
            "history_damage": conditions["rule"]["history_damage"],
            "conditions": conditions,
            "learning_improvement": None,
        }
        write_json(root / "journey.json", result)
        write_json(root / "evaluation-cases.json", {"cases": cases})
        return result
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    """Create new owned evidence for all four goal types."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    out = output_path(args.output)
    out.mkdir(parents=True)
    os.environ["FILEMATE_ENABLE_LEARNING_ORCHESTRATOR"] = "1"
    os.environ["FILEMATE_ENABLE_LEARNING_COACH"] = "1"
    results = [run_journey(out / kind, kind) for kind in ("exam", "competition", "job", "skill")]
    dependencies = sorted({name for result in results for name in result["dependencies"]})
    write_json(
        out / "report.json",
        source_identity()
        | {
            "data_type": "synthetic",
            "results": results,
            "exit_code": 0,
            "real_supplier_tested": False,
            "context_compiler_evidence": "synthetic_record_only",
            "compiler_execution": "dependency_unavailable"
            if dependencies
            else "native_original_executor",
            "status": "CONDITIONAL_PASS" if dependencies else "PASS",
            "dependencies": dependencies,
        },
    )
    print(json.dumps({"output": str(out), "journeys": len(results)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
