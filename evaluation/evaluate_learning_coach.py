"""Count engineering violations without estimating student learning improvement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from filemate.study.orchestrator.coach.models import CoachContext
from filemate.study.orchestrator.coach.output import ACTION_METHODS
from filemate.study.orchestrator.coach.rules import action_candidates


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    """Compare proposed actions with selected evidence, budgets and protected history."""
    if case.get("data_type") not in {"synthetic", "recorded_provider", "human_study"}:
        raise ValueError("explicit_data_type_required")
    context = CoachContext.model_validate(case["context"])
    registry = {action.action_key: action for action in action_candidates(context)}
    facts = {fact.fact_id: fact for fact in context.facts}
    revisions = case["current_fact_revisions"]
    actions = case["proposal"]["new_actions"]
    report = dict.fromkeys(
        (
            "evidence_unsupported",
            "duplicate_actions",
            "overbudget_days",
            "irrelevant_actions",
            "stale_evidence",
            "crosscourse_evidence",
            "history_damage",
            "actual_edit_count",
        ),
        0,
    )
    report["duplicate_actions"] = len(actions) - len({a.get("action_key") for a in actions})
    for action in actions:
        references = action.get("fact_ids", [])
        original = registry.get(action.get("action_key"))
        allowed = set(original.fact_ids) if original else set()
        report["evidence_unsupported"] += int(
            not references or any(ref not in facts or ref not in allowed for ref in references)
        )
        report["stale_evidence"] += int(
            any(ref in facts and revisions.get(ref) != facts[ref].revision for ref in references)
        )
        target = action.get("target_ref", {})
        report["irrelevant_actions"] += int(
            original is None
            or target != original.target_ref.model_dump(mode="json")
            or action.get("action") != original.action
            or action.get("method_code") not in ACTION_METHODS.get(action.get("action"), set())
        )
        course = context.input.scope.course_id
        report["crosscourse_evidence"] += int(
            bool(course)
            and (
                target.get("course_id") not in (None, course)
                or any(
                    ref in facts
                    and getattr(facts[ref].data, "course_id", None) not in (None, course)
                    for ref in references
                )
            )
        )
    selected_ids: list[str] = []
    for day in case["proposal"]["days"]:
        selected = day["schedule"]["selected"]
        selected_ids.extend(task["task_id"] for task in selected)
        scheduled_minutes = sum(task.get("estimated_minutes") or 0 for task in selected)
        action_minutes = sum(
            action.get("minutes", 0)
            for action in actions
            if action["study_date"] == day["study_date"]
        )
        report["overbudget_days"] += int(
            max(scheduled_minutes, action_minutes) > day["options"]["available_minutes"]
        )
    report["duplicate_actions"] += len(selected_ids) - len(set(selected_ids))
    before, after = case.get("protected_before", {}), case.get("protected_after", {})
    report["history_damage"] = sum(
        key not in after or after[key] != value for key, value in before.items()
    )
    report["actual_edit_count"] = sum(
        bool(event.get("field"))
        and "before" in event
        and "after" in event
        and event["before"] != event["after"]
        for event in case.get("edit_events", [])
    )
    return report | {"learning_improvement": None}


def main(argv: list[str] | None = None) -> int:
    """Write a new engineering evaluation artifact from explicit cases."""
    from scripts.acceptance.learning_coach_fixture import source_identity

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    target = args.output.resolve()
    if not target.is_relative_to((Path.cwd() / "_working").resolve()) or target.exists():
        raise ValueError("use_new_project_working_output")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    rows = [
        {
            "case_id": case["case_id"],
            "condition": case["condition"],
            "data_type": case["data_type"],
            "metrics": evaluate_case(case),
        }
        for case in cases["cases"]
    ]
    passed = bool(rows) and all(
        value == 0
        for row in rows
        for field, value in row["metrics"].items()
        if field not in {"actual_edit_count", "learning_improvement"}
    )
    exit_code = 0 if passed else 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            source_identity()
            | {
                "contract": "learning-coach-evaluation-v1",
                "results": rows,
                "status": "PASS" if passed else "FAIL",
                "exit_code": exit_code,
                "real_supplier_tested": False,
                "limitations": ["Engineering regression only. No measured learning improvement."],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(target), "case_count": len(rows)}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
