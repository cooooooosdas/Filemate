"""Isolated course and goal records, with no external model access."""

import importlib

import pytest


def coach_module(name):
    assert importlib.util.find_spec("filemate.study.orchestrator.coach"), (
        "Learning coach evidence is not implemented"
    )
    return importlib.import_module("filemate.study.orchestrator.coach." + name)


@pytest.fixture
def coach_case(world):
    return {
        "storage": world["store"],
        "clock": lambda: world["now"][0],
        "world": world,
        "input_data": {
            "scope": {
                "goal_id": world["goal"],
                "course_id": world["courses"][0],
                "source_ids": [world["sources"][0]],
            },
            "selection": {},
            "intent": "budget",
            "question": "只有40分钟，先做什么？",
            "days": [{"study_date": "2026-10-31", "options": {"available_minutes": 40}}],
        },
    }


def read_context(case, **changes):
    model = coach_module("models").CoachInput
    return (
        coach_module("context")
        .CoachContextReader(case["storage"], clock=case["clock"])
        .read(model.model_validate(case["input_data"] | changes))
    )


def short_plan(store, goal, *, source=None, dependencies=()):
    aid = store.save_artifact(
        artifact_type="study_plan",
        source_id=source,
        content={},
        metadata={"learning_coach": {"goal_id": goal}},
    )
    result = store.create_study_plan(
        artifact_id=aid,
        source_id=source,
        plan={
            "exam_date": "2026-11-05",
            "daily_minutes": 20,
            "daily_plan": [
                {"day": 1, "date": "2026-10-31", "tasks": ["原创短任务"], "duration_minutes": 20}
            ],
        },
    )
    store._conn().executemany(
        "INSERT INTO kg_learning_artifact_sources VALUES (?,?)",
        [(aid, sid) for sid in dependencies],
    )
    store._conn().commit()
    return result["plan_id"]


def submission(store, *, provider="linux-gvisor-gcc"):
    from filemate.programming.problems import PROBLEMS
    from filemate.programming.repository import CodingRepository

    repo = CodingRepository(store)
    item = repo.create(PROBLEMS[0], "// synthetic-secret-code", "coach_submission_test_key")
    return repo.update(
        item["submission_id"],
        status="completed",
        payload={"result": {"provider": provider, "verdict": "CE"}, "review": {"score": 99}},
    )


def graph_evidence(case):
    store, w = case["storage"], case["world"]
    cid, sid = w["courses"][0], w["sources"][0]
    revision = store.get_source_revision(sid)
    with store._conn() as conn:
        conn.executemany(
            "INSERT INTO kg_concepts(concept_id,course_id,label) VALUES (?,?,?)",
            [("coach-stack", cid, "栈"), ("coach-dfs", cid, "DFS")],
        )
        conn.execute(
            "INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES ('coach-edge',?,'coach-stack','coach-dfs','prerequisite')",
            (cid,),
        )
        for key, concept, relation in [
            ("s", "coach-stack", None),
            ("d", "coach-dfs", None),
            ("r", None, "coach-edge"),
        ]:
            conn.execute(
                "INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,concept_id,relation_id,excerpt,char_start,char_end) VALUES (?,?,?,?,?,?,?,?,?)",
                ("coach-e-" + key, cid, sid, revision, concept, relation, "原创合成引用", 0, 6),
            )
    return ["coach-stack", "coach-dfs"]
