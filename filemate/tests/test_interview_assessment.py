"""Synthetic six-dimensional evidence contracts; no human calibration claims."""

import copy
import importlib
import json
from types import SimpleNamespace

import pytest


def rules():
    return importlib.import_module("filemate.interview_assessment.rules")


def interview(category="general", track="general"):
    return {
        "interview_id": "s1",
        "target_role": "开发",
        "scenario": "求职面试",
        "status": "completed",
        "total": 1,
        "configuration": {
            "category": category,
            "track": track,
            "language": "zh-CN",
            "difficulty_strategy": "standard",
        },
        "turns": [
            {
                "attempt_id": "a1",
                "version": 1,
                "question_index": 0,
                "question": "请说明你的方案",
                "answer": "我用索引减少扫描，并对比执行计划。",
                "input_digest": "input1",
                "latest_run_id": "old-four-dim",
            }
        ],
        "runtime": None,
    }


def model_payload(rubric, snapshot):
    catalog = rules().catalog(snapshot)
    answer_ref = next(key for key, item in catalog.items() if item["kind"] == "answer")
    return {
        "dimensions": [
            {
                "id": dim["id"],
                "status": "assessed" if dim["evidence_kind"] == "answer" else "missing",
                "score": 80 if dim["evidence_kind"] == "answer" else None,
                "evidence": [answer_ref] if dim["evidence_kind"] == "answer" else [],
                "reason": "依据回答中的方案与验证描述。",
                "suggestion": "补充一次实测对比。",
            }
            for dim in rubric["dimensions"]
        ]
    }


@pytest.mark.parametrize(
    "category,track",
    [
        ("general", "general"),
        ("technical", "cpp"),
        ("project", "general"),
        ("creator", "knowledge"),
        ("creator", "commerce"),
        ("learning_expression", "general"),
    ],
)
def test_scenario_rubrics_have_six_versioned_weighted_anchored_dimensions(category, track):
    rubric = rules().rubric_for(interview(category, track))
    assert len(rubric["dimensions"]) == 6
    assert sum(d["weight"] for d in rubric["dimensions"]) == 100
    assert len({d["id"] for d in rubric["dimensions"]}) == 6
    assert all(d["anchors"] and d["range"] == [0, 100] for d in rubric["dimensions"])
    assert rubric["version"] and rubric["calibration"] == "待校准"
    changed = copy.deepcopy(rubric)
    changed["dimensions"][0]["name"] = "不应污染后续请求"
    assert rules().rubric_for(interview(category, track)) != changed


def test_missing_optional_evidence_is_not_zero_and_weight_is_explicitly_renormalized():
    r = rules()
    snap = r.snapshot(interview())
    rubric = r.rubric_for(interview())
    result = r.parse_result(json.dumps(model_payload(rubric, snap)), rubric, snap)
    assert result["overall_score"] == 80
    assert result["completeness"] == "partial"
    assert len([d for d in result["dimensions"] if d["score"] is None]) == 2
    assert result["weighting"]["applied_weight"] < 100
    assert "归一" in result["weighting"]["rule"]
    assert all(
        e["attempt_id"] == "a1" and e["quote"] in interview()["turns"][0]["answer"]
        for d in result["dimensions"]
        for e in d["evidence"]
    )


def test_missing_core_blocks_total_and_legacy_scores_are_not_used():
    r = rules()
    data = interview()
    data["turns"][0].update(score=100, dimensions={"内容": 100}, fluency_metrics={"score": 100})
    snap = r.snapshot(data)
    assert "score" not in snap["turns"][0] and "fluency_metrics" not in snap["turns"][0]
    rubric = r.rubric_for(data)
    payload = model_payload(rubric, snap)
    payload["dimensions"][0].update(status="missing", score=None, evidence=[])
    assert r.parse_result(json.dumps(payload), rubric, snap)["overall_score"] is None
    assert r.pending_result(rubric, snap)["overall_score"] is None


@pytest.mark.parametrize(
    "corruption", ["fake_quote", "duplicate", "nan", "boolean", "audio_guess", "total"]
)
def test_invalid_model_or_invented_evidence_is_rejected(corruption):
    r = rules()
    snap = r.snapshot(interview())
    rubric = r.rubric_for(interview())
    payload = model_payload(rubric, snap)
    if corruption == "fake_quote":
        payload["dimensions"][0]["evidence"] = ["invented"]
    elif corruption == "duplicate":
        payload["dimensions"][-1] = payload["dimensions"][0]
    elif corruption == "nan":
        payload["dimensions"][0]["score"] = float("nan")
    elif corruption == "boolean":
        payload["dimensions"][0]["score"] = True
    elif corruption == "audio_guess":
        next(d for d in payload["dimensions"] if d["status"] == "missing").update(
            status="assessed", score=90, evidence=["A1E1"]
        )
    else:
        payload["overall_score"] = 100
    with pytest.raises((ValueError, TypeError)):
        r.parse_result(json.dumps(payload), rubric, snap)


def test_comparison_rejects_version_language_and_missing_dimensions():
    r = rules()
    snap = r.snapshot(interview())
    rubric = r.rubric_for(interview())
    report = {
        "rubric": rubric,
        "input": snap,
        "result": r.pending_result(rubric, snap),
        "provenance": {"model": "test", "prompt_version": "v1", "rules_version": "v1"},
    }
    comparison = r.compare_reports(report, copy.deepcopy(report))
    assert comparison["comparable"] and all(d["delta"] is None for d in comparison["dimensions"])
    other = copy.deepcopy(report)
    other["rubric"]["version"] = "next"
    assert not r.compare_reports(report, other)["comparable"]
    other = copy.deepcopy(report)
    other["input"]["configuration"]["language"] = "en-US"
    assert not r.compare_reports(report, other)["comparable"]


def test_model_repair_is_bounded_and_provider_adapter_receives_only_text_evidence():
    r = rules()
    snap = r.snapshot(interview())
    rubric = r.rubric_for(interview())
    calls = []

    class Provider:
        def call(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content="bad-json" if len(calls) == 1 else json.dumps(model_payload(rubric, snap))
            )

    result = r.analyze(Provider(), rubric, snap)
    assert result["overall_score"] == 80 and len(calls) == 2
    assert all(c["retry"] == 1 and c["timeout"] <= 30 for c in calls)
    assert "fluency_metrics" not in calls[0]["messages"][1]["content"]
