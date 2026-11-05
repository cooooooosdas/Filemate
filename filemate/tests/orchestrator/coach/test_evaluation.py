"""Engineering evaluation counts observed violations over actual synthetic context."""

import copy
import importlib.util

from .conftest import coach_module, graph_evidence, read_context


def evaluator():
    assert importlib.util.find_spec("evaluation.evaluate_learning_coach")
    from evaluation.evaluate_learning_coach import evaluate_case

    return evaluate_case


def evaluation_case(coach_case):
    nodes = graph_evidence(coach_case)
    context = read_context(coach_case, selection={"concept_ids": nodes})
    proposal = coach_module("rules").build_rule_proposal(context)
    assert proposal.new_actions
    return {
        "data_type": "synthetic",
        "context": context.model_dump(mode="json"),
        "proposal": proposal.model_dump(mode="json"),
        "current_fact_revisions": {fact.fact_id: fact.revision for fact in context.facts},
        "protected_before": {"old-completion": {"completed": True}},
        "protected_after": {"old-completion": {"completed": True}},
        "edit_events": [],
    }


def test_evaluation_rejects_duplicate_and_overbudget(coach_case):
    case = evaluation_case(coach_case)
    case["proposal"]["new_actions"].append(copy.deepcopy(case["proposal"]["new_actions"][0]))
    case["proposal"]["days"][0]["options"]["available_minutes"] = 1
    report = evaluator()(case)
    assert report["duplicate_actions"] == 1
    assert report["overbudget_days"] == 1
    assert report["learning_improvement"] is None


def test_evaluation_rejects_unsupported_stale_crosscourse_and_history_damage(coach_case):
    case = evaluation_case(coach_case)
    action = case["proposal"]["new_actions"][0]
    fact_id = action["fact_ids"][0]
    case["current_fact_revisions"][fact_id] = "changed-current-revision"
    action["target_ref"]["course_id"] = coach_case["world"]["courses"][1]
    case["protected_after"] = {}
    report = evaluator()(case)
    assert report["stale_evidence"] == 1
    assert report["crosscourse_evidence"] == 1
    assert report["irrelevant_actions"] == 1
    assert report["history_damage"] == 1
    action["fact_ids"] = ["fabricated-reference"]
    assert evaluator()(case)["evidence_unsupported"] == 1


def test_valid_rule_and_observed_edits_do_not_claim_learning_gain(coach_case):
    case = evaluation_case(coach_case)
    case["edit_events"] = [
        {"field": "minutes", "before": 15, "after": 16},
        {"field": "minutes", "before": 16, "after": 16},
    ]
    case["learning_improvement"] = 0.95
    report = evaluator()(case)
    assert report["actual_edit_count"] == 1
    assert report["learning_improvement"] is None
    assert all(
        value == 0
        for key, value in report.items()
        if key not in ("actual_edit_count", "learning_improvement")
    )


def test_cli_records_source_environment_and_exit_code(coach_case, tmp_path, monkeypatch):
    import json

    from evaluation.evaluate_learning_coach import main

    monkeypatch.chdir(tmp_path)
    case = evaluation_case(coach_case)
    case.update(case_id="synthetic-cli", condition="rule")
    source = tmp_path / "cases.json"
    source.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
    target = tmp_path / "_working/result.json"
    assert main(["--cases", str(source), "--output", str(target)]) == 0
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["environment"]["python"]
    assert len(report["critical_source_sha256"]) == 64
    assert report["exit_code"] == 0
    assert report["real_supplier_tested"] is False


def test_cli_fails_when_an_engineering_violation_is_observed(coach_case, tmp_path, monkeypatch):
    import json

    from evaluation.evaluate_learning_coach import main

    monkeypatch.chdir(tmp_path)
    case = evaluation_case(coach_case)
    case.update(case_id="synthetic-invalid-cli", condition="rule")
    case["proposal"]["new_actions"].append(copy.deepcopy(case["proposal"]["new_actions"][0]))
    source = tmp_path / "cases.json"
    source.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
    target = tmp_path / "_working/result.json"
    assert main(["--cases", str(source), "--output", str(target)]) == 1
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert report["exit_code"] == 1
