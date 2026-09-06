"""SQLiteStorage 独立单元测试。"""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from filemate.execution.storage import _MIGRATIONS, SQLiteStorage
from filemate.understanding.interview_bank_seed import (
    DIFFICULTIES,
    SCENARIOS,
    SEED_QUESTIONS,
)


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


def _apply_migrations_upto(db_path: Path, upto: int) -> None:
    """手动应用 1..upto 迁移，模拟旧版本库。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL DEFAULT
                          (strftime('%Y-%m-%dT%H:%M:%S','now')))"""
    )
    conn.commit()
    for version, name, script in _MIGRATIONS:
        if version > upto:
            break
        conn.executescript(
            f"BEGIN IMMEDIATE;\n{script}\n"
            f"INSERT INTO schema_migrations (version, name) VALUES ({version}, '{name}');\n"
            "COMMIT;"
        )
    conn.close()


class TestMigrationUpgrade:
    def test_upgrade_from_old_version(self, tmp_path: Path) -> None:
        """v5 旧库逐级升级到 v15，且现役表和字段确实建立。"""
        db = tmp_path / "old.db"
        _apply_migrations_upto(db, 5)
        legacy = sqlite3.connect(db)
        legacy.execute(
            """INSERT INTO interview_sessions
               (interview_id, target_role, scenario, difficulty, questions)
               VALUES ('legacy-interview', '后端开发', '求职面试', '标准',
                       '["旧题一", "旧题二"]')"""
        )
        legacy.commit()
        legacy.close()

        s = SQLiteStorage(db)
        s.init_schema()

        assert s.get_schema_version() == 15
        assert [m["version"] for m in s.list_migrations()] == [
            1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15
        ]

        conn = s._conn()
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "study_plans" in tables       # v6
        assert "product_feedback" in tables  # v7
        assert "interview_questions" in tables  # v9
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(wrong_questions)")}
        assert "next_review_at" in cols       # v8 字段
        interview_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(interview_sessions)")
        }
        assert "question_ids" in interview_cols  # v9 字段
        turn_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(interview_turns)")
        }
        assert "fluency_metrics" in turn_cols  # v13 字段
        assert {"scoring_mode", "scoring_version"} <= turn_cols
        assert "agent_run_id" in interview_cols  # v14 字段
        assert {"agent_runs", "agent_steps", "agent_memories", "source_rights"} <= tables
        upgraded_interview = s.get_interview("legacy-interview")
        assert upgraded_interview is not None
        assert upgraded_interview["question_ids"] == [None, None]
        s.close()

    def test_repairs_unreleased_ai_learning_migration_collision(
        self, tmp_path: Path
    ) -> None:
        """实验分支占用 v9-v11 时仍补齐现役题库，不破坏旧记录。"""
        db = tmp_path / "migration-collision.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE schema_migrations (
                   version INTEGER PRIMARY KEY,
                   name TEXT NOT NULL,
                   applied_at TEXT NOT NULL DEFAULT
                              (strftime('%Y-%m-%dT%H:%M:%S','now')))"""
        )
        conn.executemany(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            [
                (9, "ai_learning"),
                (10, "ai_learning_llm_config"),
                (11, "ai_learning_message_mode"),
            ],
        )
        conn.commit()
        conn.close()

        storage = SQLiteStorage(db)
        storage.init_schema()

        assert storage.get_schema_version() == 15
        migrations = {item["version"]: item["name"] for item in storage.list_migrations()}
        assert migrations[9] == "ai_learning"
        assert migrations[12] == "interview_question_bank_compatibility"
        tables = {
            row["name"]
            for row in storage._conn().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "interview_questions" in tables
        interview_columns = {
            row["name"]
            for row in storage._conn().execute(
                "PRAGMA table_info(interview_sessions)"
            )
        }
        assert "question_ids" in interview_columns
        assert storage.list_interview_questions() == []
        storage.close()

    def test_failed_migration_rolls_back(self, tmp_path: Path) -> None:
        """v8 迁移失败时回滚，不留下 version 记录，可重试。"""
        db = tmp_path / "broken.db"
        _apply_migrations_upto(db, 7)

        # 破坏 v8 依赖：删掉 wrong_questions 表，让 ALTER 失败
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE wrong_questions")
        conn.commit()
        conn.close()

        s = SQLiteStorage(db)
        with pytest.raises(sqlite3.OperationalError):
            s.init_schema()

        assert s.get_schema_version() == 7
        assert [m["version"] for m in s.list_migrations()] == [1, 2, 3, 4, 5, 6, 7]
        s.close()


def test_legacy_interview_scores_preserved_but_not_reported(tmp_path):
    db = tmp_path / "v14.db"
    _apply_migrations_upto(db, 14)
    with sqlite3.connect(db) as conn:
        conn.execute("""INSERT INTO interview_sessions
            (interview_id, target_role, scenario, difficulty, questions, overall_score)
            VALUES ('old', '开发', '求职面试', '标准', '["题目"]', 90)""")
        conn.execute("""INSERT INTO interview_turns
            (turn_id, interview_id, question_index, question, answer, score, dimensions, feedback)
            VALUES ('turn', 'old', 0, '题目', '旧回答', 90, '{"内容":90}', '旧反馈')""")
    storage = SQLiteStorage(db)
    storage.init_schema()
    restored = storage.get_interview("old")
    assert restored["overall_score"] is None
    assert restored["turns"][0]["score"] is None
    assert restored["turns"][0]["dimensions"] == {}
    assert storage.get_learning_analytics()["average_interview_score"] is None
    assert storage._conn().execute("SELECT score FROM interview_turns").fetchone()[0] == 90
    storage.close()


def test_scoped_analytics_and_assessment_provenance(storage):
    first = storage.save_source(original_name="网络.txt", source_path="/local/网络.txt", raw_text="TCP")
    second = storage.save_source(original_name="数据库.txt", source_path="/local/数据库.txt", raw_text="SQL")
    artifact = storage.save_artifact(source_id=first, artifact_type="questions", content=[
        {"question": "TCP?", "answer": "可靠传输"},
    ])
    storage.record_quiz_attempt(artifact_id=artifact, question_index=0,
                                user_answer="错误", is_correct=False, score=0, feedback="重练")
    run = storage.create_agent_run(task_type="interview", goal="练习", selected_agents=["面试 Agent"],
                                   context_refs={"source_id": first})
    session = storage.create_interview(target_role="开发", scenario="求职面试", difficulty="标准",
                                       questions=["题一", "题二"], agent_run_id=run["run_id"])
    for index, (score, mode) in enumerate([(None, "local_fallback"), (0, "llm")]):
        storage.save_interview_turn(interview_id=session["interview_id"], question_index=index,
                                    question=f"题{index}", answer="回答", score=score,
                                    dimensions={"内容": 0} if mode == "llm" else {},
                                    feedback="反馈", scoring_mode=mode)
    focused = storage.get_learning_analytics(source_id=first)
    assert focused["pending_wrong_count"] == 1
    assert focused["assessed_interview_count"] == 1
    assert focused["average_interview_score"] == 0
    other = storage.get_learning_analytics(source_id=second)
    assert other["source_count"] == 1
    assert other["quiz_attempt_count"] == 0
    assert other["pending_wrong_count"] == 0
    assert other["interview_count"] == 0
    assert other["average_interview_score"] is None
    assert other["recent_interviews"] == []
    restored = storage.get_interview(session["interview_id"])
    assert restored["overall_score"] == 0
    assert restored["assessed_turn_count"] == 1


class TestSchemaInit:
    def test_init_is_idempotent(self, storage: SQLiteStorage) -> None:
        """init_schema 可重复调用不报错。"""
        storage.init_schema()  # 第二次调用
        # 不应抛异常
        sess = storage.get_session("any")
        assert sess is None

    def test_init_schema_leaves_no_dangling_transaction(
        self,
        storage: SQLiteStorage,
    ) -> None:
        """init_schema 后连接不处于事务中（回归 database is locked）。"""
        conn = storage._conn()
        assert conn.in_transaction is False

    def test_tables_exist(self, storage: SQLiteStorage) -> None:
        conn = storage._conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        for expected in ("sessions", "processed_files", "operation_log", "user_rules"):
            assert expected in names

    def test_versioned_migrations_applied(self, storage: SQLiteStorage) -> None:
        assert storage.get_schema_version() == 15
        migrations = storage.list_migrations()
        assert [item["version"] for item in migrations] == [
            1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15
        ]
        assert migrations[-1]["name"] == "interview_scoring_provenance"

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
            "interview_questions",
            "study_plans",
            "product_feedback",
            "agent_runs",
            "agent_steps",
            "agent_memories",
            "source_rights",
        } <= tables
        assert storage.get_workspace("local")["name"] == "本地工作区"


class TestTrustedAgentMemoryAndRights:
    def test_agent_run_records_only_references_and_summaries(
        self,
        storage: SQLiteStorage,
    ) -> None:
        run = storage.create_agent_run(
            task_type="interview_session",
            goal="完成一次后端岗位模拟面试",
            selected_agents=["面试 Agent", "评价 Agent"],
            context_refs={"interview_id": "demo"},
        )
        step = storage.append_agent_step(
            run_id=run["run_id"],
            agent_name="面试 Agent",
            input_refs={"question_id": "q-1"},
            output_summary="已选择一道结构化问题",
        )
        memory = storage.save_agent_memory(
            memory_type="growth",
            scope_id="demo",
            source_type="interview_turn",
            source_id="demo:0",
            summary="第 1 题得分 82，用于后续复盘",
            allowed_agents=["评价 Agent", "规划 Agent"],
        )
        assert storage.finish_agent_run(run["run_id"]) is True

        saved = storage.get_agent_run(run["run_id"])
        assert saved is not None
        assert saved["status"] == "completed"
        assert saved["selected_agents"] == ["面试 Agent", "评价 Agent"]
        assert saved["steps"][0]["step_id"] == step["step_id"]
        assert saved["steps"][0]["input_refs"] == {"question_id": "q-1"}
        assert storage.list_agent_memories()[0]["memory_id"] == memory["memory_id"]
        assert storage.soft_delete_agent_memory(memory["memory_id"]) is True
        assert storage.list_agent_memories() == []

    def test_unconfirmed_source_cannot_be_shared(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_id = storage.save_source(
            original_name="课程讲义.pdf",
            source_path="C:/资料/课程讲义.pdf",
            raw_text="仅供测试",
        )
        default_rights = storage.get_source_rights(source_id)
        assert default_rights is not None
        assert default_rights["rights_status"] == "unconfirmed"
        assert default_rights["sharing_scope"] == "private"

        with pytest.raises(ValueError, match="只能保持私有"):
            storage.set_source_rights(
                source_id=source_id,
                rights_status="unconfirmed",
                sharing_scope="shareable",
            )

        saved = storage.set_source_rights(
            source_id=source_id,
            rights_status="authorized",
            sharing_scope="restricted",
            note="课堂内部授权",
        )
        assert saved["confirmed_at"] is not None
        listed = storage.list_source_rights()
        assert listed[0]["original_name"] == "课程讲义.pdf"
        assert "raw_text" not in listed[0]


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
            model_used="deepseek-v4-flash",
            prompt_tokens=150,
            completion_tokens=20,
            latency_ms=1200,
        )
        ops = storage.get_operations("log-2")
        assert len(ops) == 1
        o = ops[0]
        assert o["action"] == "classify"
        assert o["input_snapshot"] == '{"category":"课件"}'
        assert o["model_used"] == "deepseek-v4-flash"
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
    def test_source_lineage_aggregates_real_learning_evidence(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_id = storage.save_source(
            original_name="操作系统讲义.pdf",
            source_path="C:/资料/操作系统讲义.pdf",
            raw_text="进程与线程。",
        )
        storage.replace_source_chunks(
            source_id,
            [{"chunk_index": 0, "page_number": 1, "content": "进程与线程。"}],
        )
        storage.save_artifact(
            source_id=source_id,
            artifact_type="summary",
            title="操作系统摘要",
            content="摘要内容",
        )
        question_artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="questions",
            title="操作系统练习",
            content=[{"question": "进程是什么？", "answer": "资源分配单位"}],
        )
        storage.record_quiz_attempt(
            artifact_id=question_artifact_id,
            question_index=0,
            user_answer="不知道",
            is_correct=False,
            score=0,
            feedback="请复习原文",
        )
        plan_artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="study_plan",
            title="操作系统计划",
            content={"daily_plan": []},
        )
        storage.create_study_plan(
            artifact_id=plan_artifact_id,
            source_id=source_id,
            plan={
                "title": "操作系统计划",
                "exam_date": "2026-10-01",
                "daily_minutes": 30,
                "goal": "完成复习",
                "daily_plan": [{"date": "2026-09-05"}],
            },
        )
        run = storage.create_agent_run(
            task_type="interview_session",
            goal="围绕讲义模拟答辩",
            selected_agents=["面试 Agent", "评价 Agent"],
            context_refs={"source_id": source_id},
        )
        interview = storage.create_interview(
            target_role="课程答辩",
            scenario="竞赛答辩",
            difficulty="标准",
            questions=["请解释进程与线程。"],
            agent_run_id=run["run_id"],
        )
        storage.save_interview_turn(
            interview_id=interview["interview_id"],
            question_index=0,
            question="请解释进程与线程。",
            answer="进程拥有资源，线程负责执行。",
            score=80,
            dimensions={"内容准确性": 80},
            feedback="继续补充例子",
        )

        lineage = storage.get_source_lineage(source_id)

        assert lineage is not None
        assert lineage["completed_stage_count"] == 6
        assert lineage["artifact_counts"] == {
            "questions": 1,
            "study_plan": 1,
            "summary": 1,
        }
        stages = {stage["key"]: stage for stage in lineage["stages"]}
        assert stages["source"]["secondary"] == "1 个可引用片段"
        assert stages["practice"]["primary"] == "1 次真实作答"
        assert stages["review"]["primary"] == "1 道错题进入闭环"
        assert stages["plan"]["primary"] == "1 份学习计划"
        assert stages["interview"]["primary"] == "1 场资料关联面试"

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

    def test_list_document_contexts(self, storage: SQLiteStorage) -> None:
        for index in range(3):
            storage.save_document_context(
                ctx_id=f"ctx-list-{index}",
                context_text=f"上下文 {index}",
                chat_history=[{"role": "user", "content": f"问题 {index}"}],
            )

        sessions = storage.list_document_contexts(limit=10)

        assert len(sessions) == 3
        assert "问题 2" in [session["title"] for session in sessions]
        assert all(session["message_count"] == 1 for session in sessions)

    def test_list_document_contexts_filters_by_source(
        self, storage: SQLiteStorage
    ) -> None:
        source_a = storage.save_source(
            original_name="src-a.txt",
            source_path="/managed/src-a.txt",
            raw_text="A",
        )
        source_b = storage.save_source(
            original_name="src-b.txt",
            source_path="/managed/src-b.txt",
            raw_text="B",
        )
        storage.save_document_context(
            ctx_id="ctx-a", source_id=source_a, context_text="A"
        )
        storage.save_document_context(
            ctx_id="ctx-b", source_id=source_b, context_text="B"
        )

        sessions = storage.list_document_contexts(source_id=source_a)

        assert len(sessions) == 1
        assert sessions[0]["ctx_id"] == "ctx-a"

    def test_list_document_contexts_clamps_invalid_limit(
        self, storage: SQLiteStorage
    ) -> None:
        for index in range(3):
            storage.save_document_context(
                ctx_id=f"ctx-limit-{index}",
                context_text="很长的上下文" * 1000,
                chat_history=[{"role": "user", "content": f"问题 {index}"}],
            )

        sessions = storage.list_document_contexts(limit=-1)

        assert len(sessions) == 1
        assert "context_text" not in sessions[0]
        assert "chat_history" not in sessions[0]


class TestSourceDeletion:
    def _seed_source(self, storage: SQLiteStorage, *, name: str) -> str:
        source_id = storage.save_source(
            original_name=name,
            source_path=f"/managed/{name}",
            raw_text="正文",
            file_hash=name,
        )
        artifact_id = storage.save_artifact(
            source_id=source_id,
            artifact_type="summary",
            content="摘要",
        )
        storage.save_document_context(
            ctx_id=f"ctx-{name}",
            source_id=source_id,
            artifact_id=artifact_id,
            context_text="上下文",
        )
        storage.replace_source_chunks(
            source_id,
            [{"chunk_index": 0, "content": "片段"}],
        )
        return source_id

    def test_preview_nonexistent_returns_none(
        self,
        storage: SQLiteStorage,
    ) -> None:
        assert storage.preview_source_deletion("missing") is None

    def test_preview_counts_derived_data(self, storage: SQLiteStorage) -> None:
        source_id = self._seed_source(storage, name="a.txt")
        preview = storage.preview_source_deletion(source_id)
        assert preview is not None
        assert preview["original_name"] == "a.txt"
        assert preview["affected"]["artifacts"] == 1
        assert preview["affected"]["chunks"] == 1
        assert preview["affected"]["contexts"] == 1

    def test_delete_source_cascades_and_spares_others(
        self,
        storage: SQLiteStorage,
    ) -> None:
        source_a = self._seed_source(storage, name="a.txt")
        source_b = self._seed_source(storage, name="b.txt")

        result = storage.delete_source(source_a)
        assert result is not None
        assert storage.get_source(source_a) is None
        assert storage.list_artifacts(source_id=source_a) == []
        assert storage.list_source_chunks(source_a) == []
        # 其他资料源不受影响
        assert storage.get_source(source_b) is not None
        assert len(storage.list_artifacts(source_id=source_b)) == 1
        assert len(storage.list_source_chunks(source_b)) == 1

    def test_delete_source_nonexistent_returns_none(
        self,
        storage: SQLiteStorage,
    ) -> None:
        assert storage.delete_source("missing") is None


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


class TestInterviewQuestionBank:
    def test_crud_and_unique(self, storage: SQLiteStorage) -> None:
        qid = storage.create_interview_question(
            scenario="求职面试",
            difficulty="入门",
            text="请做一分钟自我介绍。",
        )
        assert storage.get_interview_question(qid)["text"] == "请做一分钟自我介绍。"

        with pytest.raises(ValueError, match="题目已存在"):
            storage.create_interview_question(
                scenario="求职面试",
                difficulty="入门",
                text="请做一分钟自我介绍。",
            )

        assert storage.update_interview_question(
            qid, text="请做两分钟自我介绍。"
        )
        assert storage.get_interview_question(qid)["text"] == "请做两分钟自我介绍。"
        assert storage.delete_interview_question(qid)
        assert storage.get_interview_question(qid) is None

    @pytest.mark.parametrize(
        ("updates", "message"),
        [
            ({"text": "  "}, "不能为空"),
            ({"scenario": "自由讨论"}, "不支持的面试场景"),
            ({"difficulty": "困难"}, "不支持的面试难度"),
        ],
    )
    def test_update_rejects_invalid_values(
        self,
        storage: SQLiteStorage,
        updates: dict[str, object],
        message: str,
    ) -> None:
        qid = storage.create_interview_question(
            scenario="求职面试",
            difficulty="入门",
            text="请做一分钟自我介绍。",
        )

        with pytest.raises(ValueError, match=message):
            storage.update_interview_question(qid, **updates)

    def test_select_filters_enabled(self, storage: SQLiteStorage) -> None:
        disabled_id = storage.create_interview_question(
            scenario="竞赛答辩",
            difficulty="标准",
            text="请介绍项目团队分工。",
            enabled=0,
        )
        created_ids = [
            storage.create_interview_question(
                scenario="竞赛答辩",
                difficulty="标准",
                text=f"维护题目 {index}",
            )
            for index in range(6)
        ]
        selected = storage.select_interview_questions(
            scenario="竞赛答辩",
            difficulty="标准",
            limit=5,
        )
        ids = {item["id"] for item in selected}
        assert len(ids) == 5
        assert created_ids[-1] in ids
        assert created_ids[0] not in ids
        assert disabled_id not in ids

    def test_seed_is_idempotent(self, storage: SQLiteStorage) -> None:
        first_ids = storage.ensure_interview_questions(SEED_QUESTIONS)
        repeated_ids = storage.ensure_interview_questions(SEED_QUESTIONS)
        questions = storage.list_interview_questions()

        assert first_ids == repeated_ids
        assert len(first_ids) == len(questions) == 72
        for scenario in SCENARIOS:
            for difficulty in DIFFICULTIES:
                matching = [
                    item
                    for item in questions
                    if item["scenario"] == scenario
                    and item["difficulty"] == difficulty
                ]
                assert len(matching) == 8
