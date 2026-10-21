"""Validate stored reports against their immutable claim, never current answers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .rules import catalog, digest, parse_result, pending_result


def validate_report(report: Any, row: Any, rubric_digest: str) -> None:
    if not isinstance(report, dict) or set(report) != {
        "version",
        "assessment_id",
        "artifact_id",
        "generated_at",
        "input",
        "rubric",
        "result",
        "provenance",
        "purpose",
    }:
        raise ValueError("invalid saved report")
    if (
        report["version"] != "2.6"
        or row["status"] != "succeeded"
        or report["assessment_id"] != row["assessment_id"]
        or report["artifact_id"] != row["artifact_id"]
    ):
        raise ValueError("invalid saved report ownership")
    snap, rubric = json.loads(row["input_snapshot"]), json.loads(row["rubric_snapshot"])
    if (
        report["input"] != snap
        or digest(snap) != row["input_digest"]
        or snap["interview_id"] != row["interview_id"]
        or report["rubric"] != rubric
        or rubric["id"] != row["rubric_id"]
        or rubric["version"] != row["rubric_version"]
        or digest(rubric) != rubric_digest
        or report["provenance"] != json.loads(row["provenance"])
    ):
        raise ValueError("saved report snapshot mismatch")
    datetime.fromisoformat(report["generated_at"])
    if not isinstance(report["purpose"], str) or not 1 <= len(report["purpose"]) <= 2000:
        raise ValueError("invalid saved report purpose")
    if row["mode"] == "local":
        expected = pending_result(rubric, snap)
    else:
        refs = {digest(value): key for key, value in catalog(snap).items()}
        payload = {
            "dimensions": [
                {
                    **{key: dim[key] for key in ("id", "status", "score", "reason", "suggestion")},
                    "evidence": [refs[digest(e)] for e in dim["evidence"]],
                }
                for dim in report["result"]["dimensions"]
            ]
        }
        expected = parse_result(json.dumps(payload, allow_nan=False), rubric, snap)
    if digest(report["result"]) != digest(expected):
        raise ValueError("invalid saved score or evidence")
