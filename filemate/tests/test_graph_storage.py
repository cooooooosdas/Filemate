"""知识图谱持久化的合成生命周期回归。"""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.study.knowledge_graph import build_graph, extract_local, validate_graph


def test_edited_questions_do_not_transfer_old_mastery(storage: SQLiteStorage):
    text = "矩阵：按行列排列的数表。向量：具有大小和方向的量。"
    source = storage.save_source(original_name="数学笔记.txt", source_path="synthetic.txt", raw_text=text)
    batch = storage.save_graph_batch(
        source, storage.get_source_revision(source), "local", validate_graph(extract_local(text), text, source, []),
    )
    storage.transition_graph_batch(batch["batch_id"], "confirm")
    artifact = storage.save_artifact(
        artifact_type="questions", source_id=source,
        content=[{"knowledge_point": "矩阵", "question": "矩阵是什么？", "answer": "数表"}],
        metadata={"origin": "self_authored"},
    )
    storage.record_quiz_attempt(
        artifact_id=artifact, question_index=0, user_answer="数表", is_correct=True, score=1, feedback="正确",
    )
    assert next(n for n in build_graph(storage)["nodes"] if n["label"] == "矩阵")["metrics"]["sample_count"] == 1
    replacement = [{"knowledge_point": "向量", "question": "向量具有什么？", "answer": "大小和方向"}]
    storage.update_artifact(artifact, title="改为向量练习", content=replacement)
    node = next(n for n in build_graph(storage)["nodes"] if n["label"] == "向量")
    assert node["metrics"]["sample_count"] == 0
    assert node["metrics"]["correct_rate"] is None
    assert node["metrics"]["excluded_sample_count"] == 0
    old_node = next(n for n in build_graph(storage)["nodes"] if n["label"] == "矩阵")
    assert old_node["metrics"]["sample_count"] == 1
    snapshots = [a for a in storage.list_artifacts(source_id=source) if a["metadata"].get("read_only_snapshot")]
    assert len(snapshots) == 1
    assert snapshots[0]["metadata"]["question_revision_parent"] == artifact
    assert storage.get_artifact(artifact)["metadata"]["origin"] == "self_authored"
    storage.record_quiz_attempt(
        artifact_id=artifact, question_index=0, user_answer="不知道", is_correct=False, score=0, feedback="错误",
    )
    storage.update_artifact(artifact, title="只改标题", content=replacement)
    node = next(n for n in build_graph(storage)["nodes"] if n["label"] == "向量")
    assert node["metrics"]["sample_count"] == 1 and node["metrics"]["correct_rate"] == 0
    assert node["metrics"]["pending_wrong_count"] == 1


def test_wrong_history_is_versioned_and_remains_reviewable(storage: SQLiteStorage):
    source = seed_source(storage)
    old_question = {"knowledge_point": "矩阵", "question": "矩阵是什么？", "answer": "数表"}
    new_question = {"knowledge_point": "向量", "question": "向量具有什么？", "answer": "方向"}
    artifact = storage.save_artifact(artifact_type="questions", source_id=source, content=[old_question])
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="不会",
                                is_correct=False, score=0, feedback="错")
    old_wrong = storage.list_wrong_questions()[0]
    storage.update_wrong_diagnosis(old_wrong["wrong_id"], error_cause="careless", note="旧题注释")
    storage.update_artifact(artifact, title="向量", content=[new_question])
    old_saved = storage.get_wrong_question(old_wrong["wrong_id"])
    assert old_saved["artifact_id"] != artifact
    assert old_saved["question"] == old_question
    assert old_saved["error_cause_note"] == "旧题注释"
    assert old_saved["knowledge_label"] == "矩阵"
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="不会",
                                is_correct=False, score=0, feedback="错", expected_question=new_question)
    wrongs = storage.list_wrong_questions()
    assert len(wrongs) == 2
    new_wrong = next(w for w in wrongs if w["artifact_id"] == artifact)
    assert new_wrong["question"] == new_question and new_wrong["knowledge_label"] == "向量"
    assert new_wrong["error_count"] == 1 and new_wrong["error_cause_note"] == ""
    for _ in range(2):
        storage.record_quiz_attempt(artifact_id=old_saved["artifact_id"], question_index=0,
                                    user_answer="数表", is_correct=True, score=1, feedback="对",
                                    expected_question=old_question)
    assert storage.get_wrong_question(old_wrong["wrong_id"])["mastered"] == 1
    assert storage.get_wrong_question(new_wrong["wrong_id"])["mastered"] == 0
    storage.update_artifact(artifact, title="再修订", content=[old_question])
    evidence = storage.get_graph_learning_evidence(source)
    assert len(evidence["attempts"]) == 4 and len(evidence["artifacts"]) == 3
    assert len({a["attempt_id"] for a in evidence["attempts"]}) == 4
    reopened = SQLiteStorage(storage.db_path)
    reopened.init_schema()
    try:
        assert reopened.get_graph_learning_evidence(source) == evidence
    finally:
        reopened.close()


def test_title_edit_preserves_original_or_legacy_evidence_boundary(storage: SQLiteStorage):
    source = seed_source(storage)
    questions = [{"knowledge_point": "矩阵", "question": "定义？", "answer": "数表"}]
    artifact = storage.save_artifact(artifact_type="questions", source_id=source, content=questions)
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="数表",
                                is_correct=True, score=1, feedback="对")
    storage.update_artifact(artifact, title="只改标题", content=questions)
    assert storage.get_artifact(artifact)["metadata"]["graph_attempt_cutoff"] == 0
    assert len(storage.list_artifacts(source_id=source)) == 1
    legacy = storage.save_artifact(artifact_type="questions", source_id=source, content=questions)
    conn = storage._conn()
    conn.execute("UPDATE artifacts SET updated_at='2026-09-01T00:00:00' WHERE artifact_id=?", (legacy,))
    conn.commit()
    storage.update_artifact(legacy, title="旧库标题", content=questions)
    metadata = storage.get_artifact(legacy)["metadata"]
    assert metadata["question_evidence_since"] == "2026-09-01T00:00:00"
    storage.update_artifact(legacy, title="再改标题", content=questions)
    assert storage.get_artifact(legacy)["metadata"] == metadata


def test_question_snapshot_is_immutable_and_stale_grade_is_rejected(storage: SQLiteStorage):
    source = seed_source(storage)
    old = {"knowledge_point": "矩阵", "question": "定义？", "answer": "数表"}
    new = {"knowledge_point": "向量", "question": "定义？", "answer": "方向"}
    artifact = storage.save_artifact(artifact_type="questions", source_id=source, content=[old])
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="数表",
                                is_correct=True, score=1, feedback="对")
    storage.update_artifact(artifact, title="新版", content=[new])
    with pytest.raises(QuestionRevisionConflict):
        storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="数表",
                                    is_correct=True, score=1, feedback="对", expected_question=old)
    assert len(storage.get_graph_learning_evidence(source)["attempts"]) == 1
    snapshot = next(a for a in storage.list_artifacts(source_id=source) if a["artifact_id"] != artifact)
    with pytest.raises(ValueError, match="只读"):
        storage.update_artifact(snapshot["artifact_id"], title="覆盖", content=[new])
    with pytest.raises(ValueError, match="只读"):
        storage.save_artifact(artifact_id=snapshot["artifact_id"], artifact_type="questions", content=[new])
    with pytest.raises(ValueError, match="修订"):
        storage.save_artifact(artifact_id=artifact, artifact_type="questions", content=[old])


def test_revision_failure_rolls_back_snapshot_and_evidence(storage: SQLiteStorage):
    source = seed_source(storage)
    original = [{"knowledge_point": "矩阵", "question": "定义？", "answer": "数表"}]
    artifact = storage.save_artifact(artifact_type="questions", source_id=source, content=original)
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="不会",
                                is_correct=False, score=0, feedback="错")
    before = storage.get_graph_learning_evidence(source)
    conn = storage._conn()
    conn.execute("""CREATE TEMP TRIGGER reject_revision BEFORE UPDATE OF content ON artifacts
                    BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        storage.update_artifact(artifact, title="失败", content=[])
    assert storage.get_graph_learning_evidence(source) == before
    conn.execute("DROP TRIGGER reject_revision")
    conn.commit()
    storage.update_artifact(artifact, title="成功", content=[])
    assert len(storage.list_artifacts(source_id=source)) == 2


@pytest.fixture()
def storage(tmp_path: Path):
    store = SQLiteStorage(tmp_path / "graph.db")
    store.init_schema()
    yield store
    store.close()


def seed_source(storage: SQLiteStorage) -> str:
    return storage.save_source(
        original_name="图谱合成测试.txt", source_path="synthetic.txt", raw_text="矩阵乘法",
    )


def draft(storage: SQLiteStorage, source: str) -> dict:
    return storage.save_graph_batch(
        source, storage.get_source_revision(source), "local",
        {"nodes": [{"id": "matrix", "label": "矩阵"}], "edges": []},
    )


def test_batch_lifecycle_persistence_and_immutable_payload(storage: SQLiteStorage):
    source = seed_source(storage)
    batch = draft(storage, source)
    assert batch["status"] == "draft"
    assert batch["module_version"] == "2.2"
    assert batch["stale"] is False
    batch_id = batch["batch_id"]
    for action, expected in [("confirm", "confirmed"), ("undo", "undone"),
                             ("restore", "confirmed")]:
        changed = storage.transition_graph_batch(batch_id, action)
        repeated = storage.transition_graph_batch(batch_id, action)
        assert changed == repeated
        assert changed["status"] == expected
        assert changed["payload"] == batch["payload"]
    assert [event["action"] for event in storage.list_graph_events()] == ["restore", "undo", "confirm", "extract"]
    reopened = SQLiteStorage(storage.db_path)
    reopened.init_schema()
    try:
        assert reopened.get_graph_batch(batch_id) == changed
        assert reopened.list_graph_batches() == [changed]
    finally:
        reopened.close()
    with pytest.raises(KeyError):
        storage.transition_graph_batch("absent", "undo")
    with pytest.raises(ValueError):
        storage.transition_graph_batch(batch_id, "other")


def test_confirm_rejects_conflicting_labels_across_batches(storage: SQLiteStorage):
    source = seed_source(storage)
    first = draft(storage, source)
    storage.transition_graph_batch(first["batch_id"], "confirm")
    second = storage.save_graph_batch(
        source, storage.get_source_revision(source), "llm",
        {"nodes": [{"id": "matrix", "label": "另一个知识点"}], "edges": []},
    )
    with pytest.raises(ValueError, match="冲突"):
        storage.transition_graph_batch(second["batch_id"], "confirm")
    assert storage.get_graph_batch(second["batch_id"])["status"] == "draft"


def test_batch_stale_failure_and_cascade(storage: SQLiteStorage):
    source = seed_source(storage)
    batch = draft(storage, source)
    failed = storage.save_graph_batch(
        source, storage.get_source_revision(source), "llm", {}, "provider_error",
    )
    assert failed["status"] == "failed"
    with pytest.raises(ValueError):
        storage.transition_graph_batch(failed["batch_id"], "confirm")
    storage.replace_source_chunks(source, [{"chunk_index": 0, "content": "资料新版"}])
    assert storage.get_graph_batch(batch["batch_id"])["stale"] is True
    with pytest.raises(ValueError, match="版本"):
        storage.transition_graph_batch(batch["batch_id"], "confirm")
    storage.transition_graph_batch(batch["batch_id"], "undo")
    with pytest.raises(ValueError, match="版本"):
        storage.transition_graph_batch(batch["batch_id"], "restore")
    with pytest.raises(ValueError, match="版本"):
        storage.save_graph_batch(source, batch["source_revision"], "local", {})
    assert storage.preview_source_deletion(source)["affected"]["knowledge_graph_batches"] == 2
    storage.delete_source(source)
    assert storage.list_graph_batches() == []
    assert storage.list_graph_events() == []
    with pytest.raises(ValueError, match="删除"):
        storage.save_graph_batch(source, batch["source_revision"], "local", {})


def plan_data() -> dict:
    return {
        "title": "矩阵复习", "daily_minutes": 20,
        "daily_plan": [{"date": "2026-09-29", "tasks": ["复习矩阵"]}],
    }


def test_graph_plan_atomic_idempotent_and_reversible(storage: SQLiteStorage):
    source = seed_source(storage)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: storage.save_graph_study_plan(source, "matrix", "rev1", plan_data()),
            range(8),
        ))
    assert all(item == results[0] for item in results)
    assert [event["action"] for event in storage.list_graph_events()] == ["plan_create"]
    ids = results[0]
    assert len(storage.list_study_plans()) == 1
    assert len(storage.list_artifacts(source_id=source)) == 1
    replacement = plan_data() | {"title": "不得覆盖"}
    assert storage.save_graph_study_plan(source, "matrix", "rev1", replacement) == ids
    assert storage.get_study_plan(ids["plan_id"])["title"] == "矩阵复习"
    completed = storage.set_study_plan_day(ids["plan_id"], 0, True)
    assert completed["status"] == "completed"
    archived = storage.undo_graph_study_plan(ids["plan_id"])
    assert archived == storage.undo_graph_study_plan(ids["plan_id"])
    assert archived["status"] == "archived"
    with pytest.raises(ValueError, match="撤销"):
        storage.set_study_plan_day(ids["plan_id"], 0, False)
    restored = storage.restore_graph_study_plan(ids["plan_id"])
    assert restored["status"] == "completed"
    assert restored["completed_days"] == [0]
    assert restored == storage.restore_graph_study_plan(ids["plan_id"])
    another = storage.save_graph_study_plan(source, "matrix", "rev2", plan_data())
    assert another != ids
    storage.delete_source(source)
    assert storage.get_study_plan(ids["plan_id"]) is None
    assert storage.get_artifact(ids["artifact_id"]) is None
    assert storage.list_graph_events() == []


def test_plan_failure_rolls_back_artifact_and_rejects_non_graph(storage: SQLiteStorage):
    source = seed_source(storage)
    with pytest.raises(ValueError):
        storage.save_graph_study_plan(
            source, "matrix", "bad", plan_data() | {"daily_minutes": "not a number"},
        )
    assert storage.list_artifacts(source_id=source) == []
    assert storage.list_study_plans() == []
    assert storage.list_graph_events() == []
    artifact = storage.save_artifact(artifact_type="study_plan", source_id=source, content={})
    regular = storage.create_study_plan(artifact_id=artifact, source_id=source, plan=plan_data())
    with pytest.raises(ValueError, match="不是由知识图谱"):
        storage.undo_graph_study_plan(regular["plan_id"])
    assert storage.get_study_plan(regular["plan_id"])["status"] == "active"
    with pytest.raises(KeyError):
        storage.undo_graph_study_plan("missing")
    with pytest.raises(ValueError, match="删除"):
        storage.save_graph_study_plan("missing", "matrix", "revision", plan_data())


def test_evidence_is_complete_decoded_and_source_scoped(storage: SQLiteStorage):
    source = seed_source(storage)
    other = seed_source(storage)
    questions = [{"knowledge_point": "矩阵", "question": "什么是矩阵？", "answer": "数表"}]
    artifact = storage.save_artifact(
        artifact_type="questions", source_id=source, content=questions,
    )
    storage.save_artifact(artifact_type="notes", source_id=source, content={})
    storage.save_artifact(artifact_type="questions", source_id=other, content=questions)
    for _ in range(3):
        storage.record_quiz_attempt(
            artifact_id=artifact, question_index=0, user_answer="不知道",
            is_correct=False, score=0, feedback="需要复习",
        )
    evidence = storage.get_graph_learning_evidence(source)
    assert len(evidence["artifacts"]) == 1
    assert evidence["artifacts"][0]["content"] == questions
    assert len(evidence["attempts"]) == 3
    assert len(evidence["wrong_questions"]) == 1
    assert evidence["wrong_questions"][0]["question"] == questions[0]
    assert evidence["wrong_questions"][0]["knowledge_label"] == "矩阵"
    assert storage.get_graph_learning_evidence("missing") == {
        "artifacts": [], "attempts": [], "wrong_questions": [],
    }


def test_corrupt_batch_is_quarantined_without_changing_stored_payload(storage: SQLiteStorage):
    source = seed_source(storage)
    batch = draft(storage, source)
    storage._conn().execute("UPDATE knowledge_graph_batches SET payload='broken' WHERE batch_id=?",
                            (batch["batch_id"],))
    storage._conn().commit()
    damaged = storage.list_graph_batches()[0]
    assert damaged["data_error"] is True
    assert damaged["payload"] == {"nodes": [], "edges": []}
    with pytest.raises(ValueError, match="数据异常"):
        storage.transition_graph_batch(batch["batch_id"], "confirm")
    storage.transition_graph_batch(batch["batch_id"], "undo")
    assert storage._conn().execute("SELECT payload FROM knowledge_graph_batches").fetchone()[0] == "broken"
