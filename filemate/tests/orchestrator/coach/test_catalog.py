"""Paged selection metadata never exposes complete interview answers."""

import json

import pytest

from filemate.tests.orchestrator.conftest import wrong

from .conftest import coach_module, graph_evidence, submission


def catalog(case, **kwargs):
    model = coach_module("models").CoachCatalogRequest
    return coach_module("catalog").read_coach_catalog(
        case["storage"],
        model.model_validate({"scope": case["input_data"]["scope"], "kind": "interview", **kwargs}),
    )


def test_catalog_pages_metadata_only(coach_case):
    store = coach_case["storage"]
    for i in range(65):
        store.create_interview(
            target_role=f"目录合成{i:02}",
            scenario="求职面试",
            difficulty="标准",
            questions=["private-question"],
        )
    pages = [catalog(coach_case, q="目录合成", offset=offset) for offset in (0, 30, 60)]
    assert [len(p.items) for p in pages] == [30, 30, 5]
    assert all(p.total == 65 and p.limit == 30 for p in pages)
    assert len({item.id for p in pages for item in p.items}) == 65
    assert "private-question" not in json.dumps([p.model_dump() for p in pages])
    assert all(
        set(item.model_dump()) == {"id", "label", "updated_at", "revision", "valid", "source_id"}
        for p in pages
        for item in p.items
    )


@pytest.mark.parametrize("needle", ["100%", "x_y", "x' OR 1=1 --", "a\\b"])
def test_catalog_search_is_literal(coach_case, needle):
    coach_case["storage"].create_interview(
        target_role="查询-" + needle, scenario="求职面试", difficulty="标准", questions=["private"]
    )
    assert catalog(coach_case, q=needle).total == 1


def test_catalog_rejects_other_course_records_and_stays_read_only(coach_case):
    store = coach_case["storage"]
    run = store.create_agent_run(
        task_type="interview_session",
        goal="另课程",
        selected_agents=[],
        context_refs={"source_id": coach_case["world"]["sources"][1]},
    )
    store.create_interview(
        target_role="其他课程记录",
        scenario="答辩",
        difficulty="标准",
        questions=["private"],
        agent_run_id=run["run_id"],
    )
    changes = store._conn().total_changes
    assert catalog(coach_case).total == 0
    assert store._conn().total_changes == changes


def test_missing_scope_catalog_does_not_list_workspace(coach_case):
    with pytest.raises(coach_module("models").OrchestratorError):
        catalog(coach_case, scope={"goal_id": "missing"})


def test_damaged_position_catalog_retains_invalid_item(coach_case):
    store = coach_case["storage"]
    store._conn().execute(
        "INSERT INTO career_positions(position_id,request_key,payload,created_at,updated_at) VALUES ('damaged','damaged-key','{','2026-10-30','2026-10-30')"
    )
    store._conn().commit()
    result = catalog(coach_case, kind="position")
    assert result.total == 1 and result.items[0].id == "damaged"
    assert result.items[0].valid is False


def test_submission_catalog_marks_damaged_content_invalid(coach_case):
    store = coach_case["storage"]
    item = submission(store)
    result = catalog(coach_case, kind="submission")
    assert result.items[0].id == item["submission_id"] and result.items[0].valid
    store._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", ("{", item["artifact_id"])
    )
    store._conn().commit()
    assert catalog(coach_case, kind="submission").items[0].valid is False


def test_submission_catalog_only_validates_returned_page(coach_case, monkeypatch):
    store = coach_case["storage"]
    original = submission(store)
    row = dict(
        store._conn()
        .execute(
            "SELECT * FROM coding_submissions WHERE submission_id=?", (original["submission_id"],)
        )
        .fetchone()
    )
    artifact = store.get_artifact(row["artifact_id"])
    for index in range(64):
        aid = store.save_artifact(
            artifact_type="coding_submission", title="合成判题", content=artifact["content"]
        )
        clone = row | {
            "submission_id": f"coach-page-{index}",
            "request_key": f"coach-page-key-{index}",
            "artifact_id": aid,
        }
        store._conn().execute(
            "INSERT INTO coding_submissions ("
            + ",".join(clone)
            + ") VALUES ("
            + ",".join("?" for _ in clone)
            + ")",
            tuple(clone.values()),
        )
    store._conn().commit()
    module = coach_module("catalog")
    original_reader = module.selected_submissions
    seen = []

    def counted(read, selection):
        seen.extend(selection.submission_ids)
        return original_reader(read, selection)

    monkeypatch.setattr(module, "selected_submissions", counted)
    result = catalog(coach_case, kind="submission")
    assert result.total == 65 and len(result.items) == len(seen) == 30
    assert set(seen) == {item.id for item in result.items}


def test_concept_catalog_marks_stale_source_invalid(coach_case):
    graph_evidence(coach_case)
    assert all(item.valid for item in catalog(coach_case, kind="concept").items)
    store = coach_case["storage"]
    store._conn().execute(
        "UPDATE sources SET raw_text=? WHERE source_id=?",
        ("变更后的原文", coach_case["world"]["sources"][0]),
    )
    store._conn().commit()
    assert all(not item.valid for item in catalog(coach_case, kind="concept").items)


def test_wrong_catalog_marks_broken_question_invalid(coach_case):
    store = coach_case["storage"]
    identifier = wrong(coach_case["world"])
    assert catalog(coach_case, kind="wrong").items[0].valid
    store._conn().execute(
        "UPDATE wrong_questions SET question=? WHERE wrong_id=?", ("{", identifier)
    )
    store._conn().commit()
    assert catalog(coach_case, kind="wrong").items[0].valid is False


def test_interview_catalog_marks_blank_role_invalid(coach_case):
    store = coach_case["storage"]
    row = store.create_interview(
        target_role="合成面试", scenario="求职面试", difficulty="标准", questions=["private"]
    )
    store._conn().execute(
        "UPDATE interview_sessions SET target_role=? WHERE interview_id=?",
        ("", row["interview_id"]),
    )
    store._conn().commit()
    assert catalog(coach_case).items[0].valid is False
