"""SQLiteStorage 独立单元测试。TODO(徐书和)"""
from __future__ import annotations

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
