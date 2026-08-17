"""SQLiteStorage 独立单元测试。TODO(徐书和)"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from filemate.execution.storage import SQLiteStorage


@pytest.fixture()
def storage(tmp_path: Path) -> SQLiteStorage:
    db = tmp_path / "test.db"
    s = SQLiteStorage(db)
    s.init_schema()
    yield s
    s.close()


# ──────────────────────────────────────────────
#  Schema
# ──────────────────────────────────────────────


class TestSchemaInit:
    def test_init_is_idempotent(self, storage: SQLiteStorage) -> None:
        """init_schema 可重复调用不报错。"""
        storage.init_schema()  # 第二次调用
        # 不应抛异常
        sess = storage.get_session("any")
        assert sess is None

    def test_tables_exist(self, storage: SQLiteStorage) -> None:
        conn = storage._conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        for expected in ("sessions", "processed_files", "operation_log", "user_rules"):
            assert expected in names

    def test_versioned_migrations_applied(self, storage: SQLiteStorage) -> None:
        assert storage.get_schema_version() == 8
        migrations = storage.list_migrations()
        assert [item["version"] for item in migrations] == [1, 2, 3, 4, 5, 6, 7, 8]
        assert migrations[-1]["name"] == "spaced_repetition"

    def test_knowledge_tables_and_local_workspace_exist(
        self,
        storage: SQLiteStorage,
    ) -> None:
        conn = storage._conn()
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "workspaces",
            "sources",
            "artifacts",
            "document_contexts",
            "execution_records",
            "document_chunks",
            "quiz_attempts",
            "wrong_questions",
            "interview_sessions",
            "interview_turns",
            "study_plans",
            "product_feedback",
        } <= tables
        assert storage.get_workspace("local")["name"] == "本地工作区"


# ──────────────────────────────────────────────
#  sessions
# ──────────────────────────────────────────────


class TestSessions:
    def test_create_and_get(self, storage: SQLiteStorage) -> None:
        storage.create_session("s1", "/tmp/file.pdf")
        row = storage.get_session("s1")
        assert row is not None
        assert row["source_path"] == "/tmp/file.pdf"
        assert row["status"] == "pending"
        assert row["user_modified"] == 0

    def test_update_session(self, storage: SQLiteStorage) -> None:
        storage.create_session("s2", "/tmp/a.docx")
        storage.update_session("s2", category="作业", confidence=0.88, user_modified=1)
        row = storage.get_session("s2")
        assert row["category"] == "作业"
        assert abs(row["confidence"] - 0.88) < 1e-6
        assert row["user_modified"] == 1

    def test_update_nonexistent(self, storage: SQLiteStorage) -> None:
        """更新不存在的 session 不抛异常（0 行受影响）。"""
        storage.update_session("nonexist", category="课件")

    def test_list_sessions_limit(self, storage: SQLiteStorage) -> None:
        for i in range(5):
            storage.create_session(f"ls-{i}", f"/tmp/{i}.pdf")
        rows = storage.list_sessions(limit=3)
        assert len(rows) == 3

    def test_list_sessions_by_status(self, storage: SQLiteStorage) -> None:
        storage.create_session("st-1", "/tmp/a.pdf")
        storage.create_session("st-2", "/tmp/b.pdf")
        storage.update_session("st-1", status="done")
        done = storage.list_sessions("done")
        assert len(done) == 1
        assert done[0]["session_id"] == "st-1"

    def test_delete_session_cascade(self, storage: SQLiteStorage) -> None:
        storage.create_session("del-1", "/tmp/x.pdf")
        storage.log_operation("del-1", "parse")
        storage.record_hash("abcdef", "del-1")

        deleted = storage.delete_session("del-1")
        assert deleted
        assert storage.get_session("del-1") is None
        # 关联日志也应一并清理
        assert storage.get_operations("del-1") == []

    def test_delete_nonexistent(self, storage: SQLiteStorage) -> None:
        assert not storage.delete_session("never-existed")

    def test_update_invalid_column_raises(self, storage: SQLiteStorage) -> None:
        """传入无效列名应抛出 ValueError 而非 SQLite OperationalError。"""
        storage.create_session("bad-col", "/tmp/x.pdf")
        with pytest.raises(ValueError, match="无效字段"):
            storage.update_session("bad-col", nonexistent_field="oops")


# ──────────────────────────────────────────────
#  processed_files
# ──────────────────────────────────────────────


class TestProcessedFiles:
    def test_duplicate_detection(self, storage: SQLiteStorage) -> None:
        assert not storage.is_duplicate("hash-xyz")
        storage.record_hash("hash-xyz", "s1")
        assert storage.is_duplicate("hash-xyz")

    def test_record_hash_updates_counter(self, storage: SQLiteStorage) -> None:
        storage.record_hash("dup-hash", "s1")
        storage.record_hash("dup-hash", "s2")  # 同一哈希再次出现
        info = storage.get_file_info("dup-hash")
        assert info is not None
        assert info["process_count"] == 2

    def test_get_file_info_nonexistent(self, storage: SQLiteStorage) -> None:
        assert storage.get_file_info("no-such-hash") is None


# ──────────────────────────────────────────────
#  operation_log
# ──────────────────────────────────────────────


class TestOperationLog:
    def test_basic_log(self, storage: SQLiteStorage) -> None:
        storage.create_session("log-1", "/tmp/x.pdf")
        log_id = storage.log_operation("log-1", "parse", "test detail")
        assert isinstance(log_id, int)
        assert log_id > 0

    def test_log_with_llm_metadata(self, storage: SQLiteStorage) -> None:
        storage.create_session("log-2", "/tmp/y.pdf")
        storage.log_operation(
            "log-2", "classify",
            input_snapshot='{"category":"课件"}',
            model_used="step-3.7-speed",
            prompt_tokens=150,
            completion_tokens=20,
            latency_ms=1200,
        )
        ops = storage.get_operations("log-2")
        assert len(ops) == 1
        o = ops[0]
        assert o["action"] == "classify"
        assert o["input_snapshot"] == '{"category":"课件"}'
        assert o["model_used"] == "step-3.7-speed"
        assert o["prompt_tokens"] == 150
        assert o["completion_tokens"] == 20
        assert o["latency_ms"] == 1200

    def test_log_with_user_override(self, storage: SQLiteStorage) -> None:
        storage.create_session("log-3", "/tmp/z.pdf")
        storage.log_operation(
            "log-3", "confirm",
            user_override='{"category":"作业"}',
        )
        ops = storage.get_operations("log-3")
        assert ops[0]["user_override"] == '{"category":"作业"}'

    def test_get_operations_empty(self, storage: SQLiteStorage) -> None:
        # 不存在的 session 返回空列表
        assert storage.get_operations("no-session") == []


# ──────────────────────────────────────────────
#  user_rules
# ──────────────────────────────────────────────


class TestUserRules:
    def test_add_and_list(self, storage: SQLiteStorage) -> None:
        rid = storage.add_rule("category_override", "实验.*", "作业", priority=10)
        assert rid > 0
        rules = storage.list_rules()
        assert len(rules) == 1
        assert rules[0]["rule_type"] == "category_override"
        assert rules[0]["pattern"] == "实验.*"
        assert rules[0]["priority"] == 10
        assert rules[0]["enabled"] == 1

    def test_list_disabled_rules(self, storage: SQLiteStorage) -> None:
        rid = storage.add_rule("naming_template", "作业-", "[作业]", priority=1)
        storage.update_rule(rid, enabled=0)
        assert len(storage.list_rules(enabled_only=True)) == 0
        assert len(storage.list_rules(enabled_only=False)) == 1

    def test_list_by_type(self, storage: SQLiteStorage) -> None:
        storage.add_rule("category_override", "a", "A")
        storage.add_rule("naming_template", "b", "B")
        cats = storage.list_rules(rule_type="category_override")
        assert len(cats) == 1
        assert cats[0]["rule_type"] == "category_override"

    def test_update_rule(self, storage: SQLiteStorage) -> None:
        rid = storage.add_rule("course_alias", "OS", "操作系统")
        ok = storage.update_rule(rid, replacement="操作系统原理", priority=5)
        assert ok
        rules = storage.list_rules(rule_type="course_alias")
        assert rules[0]["replacement"] == "操作系统原理"
        assert rules[0]["priority"] == 5

    def test_update_nonexistent(self, storage: SQLiteStorage) -> None:
        assert not storage.update_rule(99999, priority=1)

    def test_delete_rule(self, storage: SQLiteStorage) -> None:
        rid = storage.add_rule("course_alias", "x", "y")
        assert storage.delete_rule(rid)
        assert len(storage.list_rules()) == 0

    def test_delete_nonexistent(self, storage: SQLiteStorage) -> None:
        assert not storage.delete_rule(99999)

    def test_rules_sorted_by_priority(self, storage: SQLiteStorage) -> None:
        storage.add_rule("category_override", "low", "L", priority=1)
        storage.add_rule("category_override", "high", "H", priority=100)
        storage.add_rule("category_override", "mid", "M", priority=50)
        rules = storage.list_rules(rule_type="category_override")
        priorities = [r["priority"] for r in rules]
        assert priorities == [100, 50, 1]

    def test_update_invalid_column_raises(self, storage: SQLiteStorage) -> None:
        """传入无效列名应抛出 ValueError。"""
        rid = storage.add_rule("t", "p", "r")
        with pytest.raises(ValueError, match="无效字段"):
            storage.update_rule(rid, bogus_column="x")


# ──────────────────────────────────────────────
#  knowledge persistence
# ──────────────────────────────────────────────


class TestKnowledgePersistence:
    def test_source_is_stable_for_same_file_hash(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_id = storage.save_source(
            original_name="lesson.pdf",
            source_path="/tmp/lesson.pdf",
            raw_text="第一版",
            media_type="application/pdf",
            file_hash="hash-lesson",
            metadata={"pages": 10},
        )
        same_id = storage.save_source(
            original_name="lesson.pdf",
            source_path="/tmp/new/lesson.pdf",
            raw_text="第二版",
            media_type="application/pdf",
            file_hash="hash-lesson",
            metadata={"pages": 11},
        )

        assert same_id == source_id
        source = storage.get_source(source_id)
        assert source["raw_text"] == "第二版"
        assert source["metadata"] == {"pages": 11}
        assert len(storage.list_sources()) == 1

    def test_source_requires_existing_workspace(
        self,
        storage: SQLiteStorage,
    ) -> None:
        with pytest.raises(ValueError, match="工作区不存在"):
            storage.save_source(
                workspace_id="missing",
                original_name="x.txt",
                source_path="/tmp/x.txt",
            )

    def test_artifact_round_trip_and_filters(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_id = storage.save_source(
            original_name="course.txt",
            source_path="/tmp/course.txt",
            raw_text="知识点",
        )
        artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="knowledge_cards",
            title="课程知识卡",
            content=[{"front": "问题", "back": "答案"}],
            metadata={"count": 1},
        )

        artifact = storage.get_artifact(artifact_id)
        assert artifact["content"][0]["front"] == "问题"
        assert artifact["metadata"] == {"count": 1}
        filtered = storage.list_artifacts(
            source_id=source_id,
            artifact_type="knowledge_cards",
        )
        assert [item["artifact_id"] for item in filtered] == [artifact_id]

    def test_artifact_can_be_edited(self, storage: SQLiteStorage) -> None:
        source_id = storage.save_source(
            original_name="editable.txt",
            source_path="/tmp/editable.txt",
        )
        artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="notes",
            title="初稿",
            content={"sections": ["旧内容"]},
        )

        updated = storage.update_artifact(
            artifact_id,
            title="修订稿",
            content={"sections": ["新内容"]},
        )

        assert updated is not None
        assert updated["title"] == "修订稿"
        assert updated["content"] == {"sections": ["新内容"]}
        assert storage.update_artifact("missing", title="x", content="y") is None

    def test_document_context_survives_reopen(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_id = storage.save_source(
            original_name="notes.txt",
            source_path="/tmp/notes.txt",
            raw_text="持久上下文",
        )
        artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="summary",
            content="摘要",
        )
        storage.save_document_context(
            ctx_id="ctx-persist",
            source_id=source_id,
            artifact_id=artifact_id,
            context_text="持久上下文",
            metadata={"filename": "notes.txt"},
        )
        history = storage.append_context_messages(
            "ctx-persist",
            [
                {"role": "user", "content": "问题"},
                {"role": "assistant", "content": "回答"},
            ],
        )
        assert len(history) == 2

        db_path = storage.db_path
        storage.close()
        reopened = SQLiteStorage(db_path)
        reopened.init_schema()
        try:
            context = reopened.get_document_context("ctx-persist")
            assert context["context_text"] == "持久上下文"
            assert context["metadata"]["filename"] == "notes.txt"
            assert context["chat_history"][-1]["content"] == "回答"
        finally:
            reopened.close()

    def test_delete_document_context(self, storage: SQLiteStorage) -> None:
        storage.save_document_context(
            ctx_id="ctx-delete",
            context_text="临时上下文",
        )
        assert storage.delete_document_context("ctx-delete")
        assert storage.get_document_context("ctx-delete") is None
        assert not storage.delete_document_context("ctx-delete")


class TestPersistentStudyPlans:
    def _create_plan(self, storage: SQLiteStorage) -> dict:
        source_id = storage.save_source(
            original_name="math.txt",
            source_path="/tmp/math.txt",
            raw_text="线性代数",
        )
        artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="study_plan",
            content={"title": "线性代数复习"},
        )
        return storage.create_study_plan(
            artifact_id=artifact_id,
            source_id=source_id,
            plan={
                "title": "线性代数复习",
                "exam_date": "2026-09-01",
                "daily_minutes": 60,
                "goal": "通过考试",
                "daily_plan": [
                    {"date": "2026-08-10", "tasks": ["矩阵"]},
                    {"date": "2026-08-11", "tasks": ["特征值"]},
                ],
            },
        )

    def test_progress_survives_reopen(self, storage: SQLiteStorage) -> None:
        plan = self._create_plan(storage)
        updated = storage.set_study_plan_day(plan["plan_id"], 0, True)
        assert updated["completed_days"] == [0]
        assert updated["status"] == "active"

        db_path = storage.db_path
        storage.close()
        reopened = SQLiteStorage(db_path)
        reopened.init_schema()
        try:
            restored = reopened.get_study_plan(plan["plan_id"])
            assert restored is not None
            assert restored["completed_days"] == [0]
            assert restored["plan_data"]["daily_plan"][0]["tasks"] == ["矩阵"]
        finally:
            reopened.close()

    def test_completion_updates_analytics(self, storage: SQLiteStorage) -> None:
        plan = self._create_plan(storage)
        storage.set_study_plan_day(plan["plan_id"], 0, True)
        completed = storage.set_study_plan_day(plan["plan_id"], 1, True)
        assert completed["status"] == "completed"

        analytics = storage.get_learning_analytics()
        assert analytics["study_plan_count"] == 1
        assert analytics["completed_study_plan_count"] == 1
        assert analytics["completed_study_days"] == 2
        assert analytics["total_study_days"] == 2
        assert analytics["study_completion_rate"] == 100.0

    def test_invalid_day_is_rejected(self, storage: SQLiteStorage) -> None:
        plan = self._create_plan(storage)
        with pytest.raises(ValueError, match="学习日序号无效"):
            storage.set_study_plan_day(plan["plan_id"], 99, True)


class TestAnonymousProductFeedback:
    def test_feedback_is_hashed_and_can_be_updated(
        self,
        storage: SQLiteStorage,
    ) -> None:
        created = storage.record_product_feedback(
            area="retrieval",
            target_id="敏感问题文本:chunk-1",
            rating=1,
            context={"rank": 1, "score": 2.5},
        )
        updated = storage.record_product_feedback(
            area="retrieval",
            target_id="敏感问题文本:chunk-1",
            rating=-1,
            context={"rank": 2, "score": 1.5},
        )

        assert created["feedback_id"] == updated["feedback_id"]
        assert "敏感问题文本" not in updated["target_hash"]
        assert updated["rating"] == -1
        assert updated["context"] == {"rank": 2, "score": 1.5}
        assert len(storage.list_product_feedback()) == 1

    def test_feedback_summary_groups_areas(self, storage: SQLiteStorage) -> None:
        storage.record_product_feedback(
            area="retrieval", target_id="a", rating=1,
        )
        storage.record_product_feedback(
            area="retrieval", target_id="b", rating=-1,
        )
        storage.record_product_feedback(
            area="tutor", target_id="c", rating=1,
        )

        summary = storage.get_product_feedback_summary()
        assert summary["total"] == 3
        assert summary["positive"] == 2
        assert summary["positive_rate"] == 66.67
        assert summary["by_area"]["retrieval"]["positive_rate"] == 50.0


class TestSpacedRepetition:
    def _question_artifact(self, storage: SQLiteStorage) -> str:
        source_id = storage.save_source(
            original_name="算法.txt",
            source_path="/tmp/算法.txt",
        )
        return storage.save_artifact(
            source_id=source_id,
            artifact_type="questions",
            content=[{"question": "BFS 使用什么结构？", "answer": "队列"}],
        )

    def test_correct_review_schedules_next_day(
        self,
        storage: SQLiteStorage,
    ) -> None:
        artifact_id = self._question_artifact(storage)
        storage.record_quiz_attempt(
            artifact_id=artifact_id,
            question_index=0,
            user_answer="栈",
            is_correct=False,
            score=0,
            feedback="错误",
        )
        assert len(storage.list_wrong_questions(mastered=False, due_only=True)) == 1

        storage.record_quiz_attempt(
            artifact_id=artifact_id,
            question_index=0,
            user_answer="队列",
            is_correct=True,
            score=1,
            feedback="正确",
        )
        scheduled = storage.list_wrong_questions(mastered=False)[0]
        assert scheduled["interval_days"] == 1
        assert scheduled["review_count"] == 2
        assert scheduled["correct_streak"] == 1
        assert datetime.fromisoformat(scheduled["next_review_at"]) > datetime.now(
            tz=timezone.utc
        )
        assert storage.list_wrong_questions(mastered=False, due_only=True) == []

    def test_second_correct_review_marks_mastered(
        self,
        storage: SQLiteStorage,
    ) -> None:
        artifact_id = self._question_artifact(storage)
        for is_correct, answer in ((False, "栈"), (True, "队列"), (True, "队列")):
            storage.record_quiz_attempt(
                artifact_id=artifact_id,
                question_index=0,
                user_answer=answer,
                is_correct=is_correct,
                score=1 if is_correct else 0,
                feedback="正确" if is_correct else "错误",
            )

        mastered = storage.list_wrong_questions(mastered=True)[0]
        assert mastered["mastered"] == 1
        assert mastered["interval_days"] >= 3
        assert mastered["review_count"] == 3


# ──────────────────────────────────────────────
# reversible execution
# ──────────────────────────────────────────────


class TestReversibleExecutionStorage:
    def test_start_execution_is_idempotent(
        self,
        storage: SQLiteStorage,
    ) -> None:
        storage.create_session("exec-1", "/tmp/source.pdf")
        first, created = storage.start_execution(
            session_id="exec-1",
            source_path="/tmp/source.pdf",
            dest_path="/tmp/archive/source.pdf",
            input_snapshot={"hash": "abc"},
        )
        repeated, repeated_created = storage.start_execution(
            session_id="exec-1",
            source_path="/tmp/source.pdf",
            dest_path="/tmp/other.pdf",
            input_snapshot={"hash": "different"},
        )

        assert created is True
        assert repeated_created is False
        assert repeated["execution_id"] == first["execution_id"]
        assert repeated["dest_path"] == "/tmp/archive/source.pdf"
        assert repeated["input_snapshot"] == {"hash": "abc"}

    def test_finalize_and_undo_are_atomic(
        self,
        storage: SQLiteStorage,
    ) -> None:
        storage.create_session("exec-2", "/tmp/source.pdf")
        record, _ = storage.start_execution(
            session_id="exec-2",
            source_path="/tmp/source.pdf",
            dest_path="/tmp/archive/source.pdf",
            input_snapshot={"before": True},
        )
        storage.finalize_execution(
            execution_id=record["execution_id"],
            session_id="exec-2",
            entities={"archived_path": "/tmp/archive/source.pdf"},
            dest_path="/tmp/archive/source.pdf",
            ics_path=None,
            output_snapshot={"after": True},
        )

        assert storage.get_session("exec-2")["status"] == "confirmed"
        active = storage.get_active_execution("exec-2")
        assert active["status"] == "applied"
        assert active["output_snapshot"] == {"after": True}
        assert storage.get_operations("exec-2")[-1]["action"] == "execute"

        storage.finalize_undo(
            execution_id=record["execution_id"],
            session_id="exec-2",
            entities={},
        )
        assert storage.get_active_execution("exec-2") is None
        assert storage.get_latest_execution("exec-2")["status"] == "undone"
        assert storage.get_session("exec-2")["status"] == "done"
        assert storage.get_operations("exec-2")[-1]["action"] == "undo"

    def test_concurrent_start_creates_one_open_execution(
        self,
        storage: SQLiteStorage,
    ) -> None:
        storage.create_session("exec-concurrent", "/tmp/source.pdf")

        def start() -> tuple[str, bool]:
            record, created = storage.start_execution(
                session_id="exec-concurrent",
                source_path="/tmp/source.pdf",
                dest_path="/tmp/archive/source.pdf",
                input_snapshot={},
            )
            return record["execution_id"], created

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: start(), range(8)))

        assert len({execution_id for execution_id, _ in results}) == 1
        assert sum(created for _, created in results) == 1

    def test_failed_execution_releases_idempotency_slot(
        self,
        storage: SQLiteStorage,
    ) -> None:
        storage.create_session("exec-3", "/tmp/source.pdf")
        failed, _ = storage.start_execution(
            session_id="exec-3",
            source_path="/tmp/source.pdf",
            dest_path="/tmp/archive/source.pdf",
            input_snapshot={},
        )
        storage.fail_execution(
            execution_id=failed["execution_id"],
            session_id="exec-3",
            error="目标冲突",
        )
        retried, created = storage.start_execution(
            session_id="exec-3",
            source_path="/tmp/source.pdf",
            dest_path="/tmp/archive/source-2.pdf",
            input_snapshot={},
        )

        assert created is True
        assert retried["execution_id"] != failed["execution_id"]
        assert storage.get_session("exec-3")["status"] == "failed"
