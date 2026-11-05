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
from filemate.llm_client import LLMConfig
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
        ReviewRepository(store, clock=clock).submit(
            {
                "artifact_id": case["wrong_artifact"],
                "question_index": 0,
                "expected_question": question,
                "user_answer": "A",
                "request_key": "synthetic_journey_reanswer_01",
            }
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
            "compiler_execution": case["compiler_execution"],
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
    write_json(
        out / "report.json",
        source_identity()
        | {
            "data_type": "synthetic",
            "results": results,
            "exit_code": 0,
            "real_supplier_tested": False,
            "compiler_execution": "synthetic_record_only",
        },
    )
    print(json.dumps({"output": str(out), "journeys": len(results)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
