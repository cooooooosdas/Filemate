"""Owned synthetic evidence for four learning-coach acceptance journeys."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from filemate.career.repository import CareerRepository
from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachRepository
from filemate.interview_review.models import CONTENT_AREAS
from filemate.programming.problems import PROBLEMS
from filemate.programming.repository import CodingRepository
from filemate.runtime_governance import BudgetStore, resource_scope
from filemate.study.orchestrator.coach.models import CoachInput
from filemate.study.orchestrator.models import LOCAL_ZONE, utc_now
from scripts.acceptance.orchestrator_runtime import output_path, seed, write_json

ROOT = Path(__file__).resolve().parents[2]


def source_identity() -> dict[str, Any]:
    """Record source provenance without exporting environment variables or credentials."""
    paths = list((ROOT / "filemate/study/orchestrator/coach").glob("*.py"))
    paths += list((ROOT / "scripts/acceptance").glob("learning_coach_*.py"))
    paths += [
        ROOT / "evaluation/evaluate_learning_coach.py",
        ROOT / "server.py",
        ROOT / "filemate/execution/storage.py",
    ]
    hashes = {
        str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in sorted(paths)
    }
    commit = None
    provenance = "unavailable"
    dirty = None
    git = shutil.which("git")
    if git:
        location = subprocess.run(
            [git, "-C", str(ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if location.returncode == 0 and Path(location.stdout.strip()).resolve() == ROOT:
            result = subprocess.run(
                [git, "-C", str(ROOT), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                provenance = "git_checkout"
                status = subprocess.run(
                    [git, "-C", str(ROOT), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                dirty = bool(status.stdout.strip())
    declared = os.getenv("FILEMATE_ACCEPTANCE_SOURCE_COMMIT", "")
    if commit is None and re.fullmatch("[a-f0-9]{40}", declared):
        commit, provenance = declared, "artifact_metadata"
    return {
        "source_commit": commit,
        "source_commit_provenance": provenance,
        "worktree_dirty": dirty,
        "critical_hash_normalization": "CRLF to LF for cross-platform source comparison",
        "critical_source_sha256": digest(hashes),
        "critical_files": hashes,
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.system(),
        },
    }


def protected_history(store: SQLiteStorage) -> dict[str, str]:
    """Fingerprint existing immutable rows while allowing new learning records."""
    result = {}
    for table in (
        "quiz_attempts",
        "kg_concepts",
        "kg_relations",
        "kg_evidence",
        "interview_answer_attempts",
        "interview_coach_analysis_runs",
        "study_plans",
    ):
        for row in store._conn().execute(f"SELECT rowid AS protected_rowid,* FROM {table}"):
            result[f"{table}:{row[0]}"] = digest(dict(row))
    return result


def seed_feedback(store: SQLiteStorage, source_id: str) -> tuple[str, str]:
    """Save an original answer and explicitly synthetic bounded feedback."""
    run = store.create_agent_run(
        task_type="interview_session",
        goal="原创合成答辩",
        selected_agents=[],
        context_refs={"source_id": source_id},
    )
    interview = store.create_interview(
        target_role="原创合成答辩",
        scenario="竞赛答辩",
        difficulty="标准",
        questions=["如何验证队列边界？"],
        agent_run_id=run["run_id"],
    )
    identifier = interview["interview_id"]
    attempt = (
        CoachRepository(store)
        .submit(
            identifier,
            SubmitAnswer(
                answer="我通过空队列与单元素用例验证队列边界。",
                question_index=0,
                expected_revision=0,
                request_key="synthetic_journey_answer_01",
            ),
        )
        .snapshot.current_attempt
    )
    analysis = {
        "content_analysis": {
            "source": "llm_reference",
            "keywords": [],
            "dimension_evidence": dict.fromkeys(["内容", "结构", "表达", "岗位匹配"], "队列边界"),
            "areas": {
                area: {
                    "status": "partial",
                    "evidence": "队列边界",
                    "suggestion": "补充具体验证条件",
                }
                for area in CONTENT_AREAS
            },
        }
    }
    with store._conn() as conn:
        conn.execute(
            """INSERT INTO interview_coach_analysis_runs
            (run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,review_revision,
             provider_identity,model,prompt_version,rubric_version,status,evaluation,created_at)
            VALUES ('synthetic-journey-feedback',?,?,1,'synthetic_journey_feedback','synthetic',1,1,
                    'synthetic-fixture','synthetic-fixture','v1','v1','succeeded',?,?)""",
            (identifier, attempt.attempt_id, json.dumps(analysis), attempt.created_at),
        )
    return identifier, attempt.attempt_id


def seed_coach(root: Path, goal_type: str, count: int = 1) -> dict[str, Any]:
    """Create a new isolated database and managed source files."""
    if goal_type not in {"exam", "competition", "job", "skill"}:
        raise ValueError("unsupported_goal_type")
    root.mkdir(parents=True, exist_ok=False)
    budget = BudgetStore(root / "control/resource-governance.db")
    with resource_scope(budget, "local", "local", managed_db_path=root / "synthetic.db"):
        return seed_coach_records(root, goal_type, count) | {"budget_store": budget}


def seed_coach_records(root: Path, goal_type: str, count: int) -> dict[str, Any]:
    """Seed original records under the caller's explicit fixture governance scope."""
    store, scope = seed(root, count=count)
    now = utc_now()
    today = now.astimezone(LOCAL_ZONE).date()
    inbox = root / "inbox"
    inbox.mkdir()
    (root / "archive").mkdir()
    with store._conn() as conn:
        for source in conn.execute("SELECT source_id,raw_text FROM sources").fetchall():
            text = source["raw_text"] or "原创合成引用：栈后进先出，队列先进先出。"
            path = inbox / (source["source_id"] + ".txt")
            path.write_text(text, encoding="utf-8")
            conn.execute(
                "UPDATE sources SET source_path=?,raw_text=? WHERE source_id=?",
                (str(path), text, source["source_id"]),
            )
        content = store.get_artifact(scope.goal_id)["content"]
        content.update(
            title=f"原创合成{goal_type}目标",
            goal_type=goal_type,
            deadline=(today + timedelta(days=28 if goal_type == "skill" else 7)).isoformat(),
        )
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?",
            (json.dumps(content, ensure_ascii=False), scope.goal_id),
        )
        revision = store.get_source_revision(scope.source_ids[0])
        for index, label in enumerate(("栈", "队列")):
            nid = f"synthetic-journey-node-{index}"
            conn.execute(
                "INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)",
                (nid, scope.course_id, label),
            )
            conn.execute(
                """INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                         concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'原创合成引用',0,6)""",
                ("e-" + nid, scope.course_id, scope.source_ids[0], revision, nid),
            )
    wrong = (
        store._conn()
        .execute(
            "SELECT wrong_id,artifact_id FROM wrong_questions WHERE source_id=? ORDER BY wrong_id LIMIT 1",
            (scope.source_ids[0],),
        )
        .fetchone()
    )
    coding = CodingRepository(store)
    submission = coding.create(
        PROBLEMS[0],
        "// synthetic fixture only\nint main(){ return 0 }",
        "synthetic_journey_submission",
    )
    coding.update(
        submission["submission_id"],
        status="completed",
        payload={
            "result": {"provider": "linux-gvisor-gcc", "verdict": "CE", "synthetic_fixture": True}
        },
    )
    interview_id, attempt_id = seed_feedback(store, scope.source_ids[0])
    selection: dict[str, Any] = {
        "concept_ids": [f"synthetic-journey-node-{i}" for i in range(2)],
        "wrong_ids": [wrong["wrong_id"]],
    }
    if goal_type in {"competition", "job"}:
        selection.update(
            interview_ids=[interview_id],
            feedback_refs=[
                {
                    "interview_id": interview_id,
                    "attempt_id": attempt_id,
                    "feedback_item_id": "logic",
                    "expected_revision": "synthetic-journey-feedback",
                }
            ],
        )
    if goal_type in {"skill", "job"}:
        selection["submission_ids"] = [submission["submission_id"]]
    if goal_type == "job":
        position = CareerRepository(store).create(
            {
                "company": "原创合成企业",
                "industry": "合成工程验收",
                "region": "合成地点",
                "title": "合成C++实习方向",
                "employment": "用户自定义",
                "description": "掌握C++基础，能够说明队列边界，并以项目实例进行沟通。",
                "requirements": [
                    {"label": "队列边界", "evidence": "能够说明队列边界", "category": "knowledge"}
                ],
                "source": "原创合成岗位资料",
                "source_kind": "user_import",
                "collected_at": (now - timedelta(seconds=1)).isoformat(),
            },
            "synthetic_journey_position",
        )
        selection.update(position_id=position["position_id"], requirement_indices=[0])
    other_source = (
        store._conn()
        .execute(
            "SELECT source_id FROM sources WHERE source_id != ? LIMIT 1", (scope.source_ids[0],)
        )
        .fetchone()[0]
    )
    old_artifact = store.save_artifact(
        artifact_type="study_plan", source_id=other_source, content={}
    )
    old_plan = store.create_study_plan(
        artifact_id=old_artifact,
        source_id=other_source,
        plan={
            "title": "原创合成旧计划",
            "exam_date": today.isoformat(),
            "daily_minutes": 10,
            "daily_plan": [
                {
                    "day": 1,
                    "date": today.isoformat(),
                    "tasks": ["已完成的另一课程任务"],
                    "duration_minutes": 10,
                }
            ],
        },
    )
    store.set_study_plan_day(old_plan["plan_id"], 0, True)
    body = CoachInput.model_validate(
        {
            "scope": scope.model_dump(),
            "selection": selection,
            "intent": "budget",
            "question": "根据已选择的合成训练记录，安排下一步并说明依据。",
            "days": [{"study_date": today.isoformat(), "options": {"available_minutes": 180}}],
        }
    )
    return {
        "store": store,
        "input": body,
        "now": now,
        "root": root,
        "wrong_artifact": wrong["artifact_id"],
        "original_submission_id": submission["submission_id"],
        "goal_type": goal_type,
        "data_type": "synthetic",
        "compiler_execution": "synthetic_record_only",
    }


def main(argv: list[str] | None = None) -> int:
    """Create a new fixture directory for local review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    out = output_path(args.output)
    case = seed_coach(out, "exam")
    try:
        write_json(
            out / "fixture.json",
            source_identity()
            | {
                "data_type": "synthetic",
                "schema": case["store"].get_schema_version(),
                "input": case["input"].model_dump(mode="json"),
                "compiler_execution": case["compiler_execution"],
                "exit_code": 0,
                "real_supplier_tested": False,
            },
        )
    finally:
        case["store"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
