"""Measure bounded coach reads, rules and four-concurrent actual HTTP requests."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from filemate.execution.data_actions import digest
from filemate.study.orchestrator.coach.context import CoachContextReader
from filemate.study.orchestrator.coach.rules import build_rule_proposal
from scripts.acceptance.learning_coach_fixture import seed_coach, source_identity
from scripts.acceptance.learning_coach_runtime import API, sqlite_profile, start_api
from scripts.acceptance.orchestrator_performance import stats
from scripts.acceptance.orchestrator_runtime import output_path, write_json


def ids(value: dict[str, Any]) -> str:
    """Compare evidence and review identities independently of response timestamps."""
    return digest(
        {
            "facts": sorted((f["fact_id"], f["record_id"], f["revision"]) for f in value["facts"]),
            "reviews": sorted(row["wrong_id"] for row in value["snapshot"]["facts"]["reviews"]),
        }
    )


def benchmark(
    root: Path, *, wrong_count: int, node_count: int, force_no_json1: bool, samples: int = 16
) -> dict[str, Any]:
    """Use the same database and record identities for direct and HTTP measurements."""
    if wrong_count < 0 or node_count < 2 or samples < 4:
        raise ValueError("invalid_capacity_parameters")
    with sqlite_profile(force_no_json1) as counters:
        case = seed_coach(root, "exam", count=max(1, wrong_count))
        store, body = case["store"], case["input"]
        try:
            conn = store._conn()
            if wrong_count == 0:
                conn.execute("DELETE FROM wrong_questions")
                body.selection.wrong_ids = []
            base = datetime(2020, 1, 1, tzinfo=timezone.utc)
            conn.executemany(
                "UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?",
                [
                    (
                        (base + timedelta(seconds=index + group * wrong_count)).isoformat(),
                        f"synthetic-{group}-{index:06}",
                    )
                    for group in (0, 1)
                    for index in range(wrong_count)
                ],
            )
            revision = store.get_source_revision(body.scope.source_ids[0])
            for index in range(2, node_count):
                nid = f"synthetic-journey-node-{index}"
                conn.execute(
                    "INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)",
                    (nid, body.scope.course_id, f"原创合成节点{index}"),
                )
                conn.execute(
                    """INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                             concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'原创合成引用',0,6)""",
                    ("e-" + nid, body.scope.course_id, body.scope.source_ids[0], revision, nid),
                )
            for index in range(1, node_count):
                rid = f"synthetic-capacity-relation-{index}"
                conn.execute(
                    "INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,'related_to')",
                    (
                        rid,
                        body.scope.course_id,
                        f"synthetic-journey-node-{index - 1}",
                        f"synthetic-journey-node-{index}",
                    ),
                )
                conn.execute(
                    """INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                             relation_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'原创合成引用',0,6)""",
                    ("e-" + rid, body.scope.course_id, body.scope.source_ids[0], revision, rid),
                )
            conn.commit()
            reader = CoachContextReader(store)
            context_times, rule_times, digests, sizes = [], [], [], []
            for _ in range(samples):
                began = time.perf_counter()
                context = reader.read(body)
                context_times.append((time.perf_counter() - began) * 1000)
                assert context.snapshot.coverage["reviews"]["total"] == wrong_count
                encoded = context.model_dump(mode="json")
                digests.append(ids(encoded))
                sizes.append(len(context.model_dump_json().encode("utf-8")))
                began = time.perf_counter()
                proposal = build_rule_proposal(context)
                rule_times.append((time.perf_counter() - began) * 1000)
                assert len(proposal.new_actions) <= 7 and len(context.projection.tasks) <= 200

            def call(_: int) -> tuple[float, str, int]:
                began = time.perf_counter()
                response = client.post(API + "/context", json=body.model_dump(mode="json"))
                elapsed = (time.perf_counter() - began) * 1000
                response.raise_for_status()
                assert (
                    response.headers["X-FileMate-Fixture-Json1-Rejected"]
                    == str(bool(counters["json1_probe_rejected"])).lower()
                )
                result = response.json()["data"]
                assert result["snapshot"]["coverage"]["reviews"]["total"] == wrong_count
                return elapsed, ids(result), len(response.content)

            with (
                start_api(case, force_no_json1=force_no_json1) as (client, _),
                ThreadPoolExecutor(max_workers=4) as pool,
            ):
                concurrent = list(pool.map(call, range(samples)))
            digests.extend(row[1] for row in concurrent)
            assert len(set(digests)) == 1
            nodes = conn.execute(
                "SELECT COUNT(*) FROM kg_concepts WHERE course_id=?", (body.scope.course_id,)
            ).fetchone()[0]
            scope_count = conn.execute(
                "SELECT COUNT(*) FROM wrong_questions WHERE source_id=?",
                (body.scope.source_ids[0],),
            ).fetchone()[0]
            assert nodes == node_count and scope_count == wrong_count
            context_stats, rule_stats = stats(context_times), stats(rule_times)
            http_stats = stats([row[0] for row in concurrent])
            passed = max(context_stats["p95_ms"], http_stats["p95_ms"]) <= 500
            report = {
                "data_type": "synthetic",
                "scope_wrong_count": scope_count,
                "foreign_wrong_count": store._conn()
                .execute(
                    "SELECT COUNT(*) FROM wrong_questions WHERE source_id!=?",
                    (body.scope.source_ids[0],),
                )
                .fetchone()[0],
                "scope_node_count": nodes,
                "scope_relation_count": conn.execute(
                    "SELECT COUNT(*) FROM kg_relations WHERE course_id=?", (body.scope.course_id,)
                ).fetchone()[0],
                "distinct_due_times_per_scope": wrong_count,
                "context": context_stats,
                "rule": rule_stats,
                "http_four_concurrent": http_stats,
                "context_coverage": context.snapshot.coverage,
                "max_response_bytes": max(*sizes, *(row[2] for row in concurrent)),
                "semantic_ids_stable": True,
                "semantic_id_sha256": digests[0],
                "force_no_json1": force_no_json1,
                "json1_profile": "forced_function_rejection" if force_no_json1 else "native",
                "json1_rejections": counters["json1_rejections"],
                "json1_probe_rejected": counters["json1_probe_rejected"],
                "workload_json1_rejections": counters["json1_rejections"]
                - int(counters["json1_probe_rejected"]),
                "supplier_calls": 0,
                "status": "PASS" if passed else "P2",
            }
            write_json(root / "performance.json", report)
            return report
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    """Execute every declared scale in native and function-rejection profiles."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args(argv)
    root = output_path(args.output)
    root.mkdir(parents=True)
    os.environ["FILEMATE_ENABLE_LEARNING_ORCHESTRATOR"] = "1"
    os.environ["FILEMATE_ENABLE_LEARNING_COACH"] = "1"
    scales = ((0, 100), (100, 100), (1000, 1000), (10000, 10000))
    results = [
        benchmark(
            root / f"{count}-{nodes}-{'no-json1' if forced else 'native'}",
            wrong_count=count,
            node_count=nodes,
            force_no_json1=forced,
            samples=args.samples,
        )
        for count, nodes in scales
        for forced in (False, True)
    ]
    passed = all(row["status"] == "PASS" for row in results)
    write_json(
        root / "report.json",
        source_identity()
        | {
            "data_type": "synthetic",
            "results": results,
            "status": "PASS" if passed else "P2",
            "exit_code": 0 if passed else 1,
        },
    )
    print(
        json.dumps(
            {"output": str(root), "scenarios": len(results), "status": "PASS" if passed else "P2"}
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
