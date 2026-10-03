"""用原创合成数据验证分库快照、故障和恢复边界。"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.operations import backup


@pytest.fixture
def managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """建立三个合成数据库和托管附件。"""
    monkeypatch.delenv("FILEMATE_IDENTITY_SECRET", raising=False)
    root = tmp_path / "managed"
    root.mkdir()
    (root / "identity.secret").write_bytes(b"synthetic-only-identity-signing-key-000000")
    for suffix in ("", "users/u_" + "a" * 32, "users/u_" + "b" * 32):
        scope = root / suffix
        (scope / "inbox").mkdir(parents=True)
        (scope / "archive/empty").mkdir(parents=True)
        source = scope / "inbox/原创复习资料.txt"
        source.write_text("合成资料：数组下标范围为0至n-1。", encoding="utf-8")
        (scope / "archive/已确认.txt").write_text("原创合成归档", encoding="utf-8")
        storage = SQLiteStorage(scope / "filemate.db")
        storage.init_schema()
        storage.create_session("synthetic-session", str(source.resolve()))
        storage.close()
    return root


def _create(root: Path, target: Path) -> dict:
    """预览确认后创建合成快照。"""
    plan = backup.plan_backup(root)
    return backup.create_backup(root, target, plan["confirmation"], quiesced=True)


def test_preview_and_three_databases_restore(managed: Path, tmp_path: Path) -> None:
    original = {
        file.relative_to(managed): file.read_bytes()
        for file in managed.rglob("*")
        if file.is_file()
    }
    plan = backup.plan_backup(managed)
    assert len([entry for entry in plan["entries"] if entry["kind"] == "database"]) == 3
    assert plan == backup.plan_backup(managed)
    assert original == {
        file.relative_to(managed): file.read_bytes()
        for file in managed.rglob("*")
        if file.is_file()
    }
    snapshot = tmp_path / "backup"
    report = _create(managed, snapshot)
    assert report["passed"] is True
    assert {
        entry["database"]["schema_version"]
        for entry in report["manifest"]["entries"]
        if entry["kind"] == "database"
    } == {24}
    target = tmp_path / "staged"
    restore_plan = backup.plan_restore(snapshot, target)
    assert not target.exists()
    result = backup.restore_backup(snapshot, target, restore_plan["confirmation"])
    assert result["passed"] and not result["activated"]
    for relative, content in original.items():
        if relative.suffix != ".db":
            assert (target / relative).read_bytes() == content
    assert (target / "archive/empty").is_dir()
    with closing(sqlite3.connect(target / "filemate.db")) as conn:
        assert conn.execute("SELECT source_path FROM sessions").fetchone()[0] == str(
            (managed / "inbox/原创复习资料.txt").resolve()
        )
    assert original == {
        file.relative_to(managed): file.read_bytes()
        for file in managed.rglob("*")
        if file.is_file()
    }


def test_committed_wal_is_included(managed: Path, tmp_path: Path) -> None:
    with closing(sqlite3.connect(managed / "filemate.db")) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            "INSERT INTO sessions(session_id, source_path) VALUES (?, ?)",
            ("wal-record", "synthetic://note"),
        )
        writer.commit()
        assert (managed / "filemate.db-wal").stat().st_size > 0
        snapshot = tmp_path / "wal-backup"
        report = _create(managed, snapshot)
        assert not any(
            entry["path"].endswith(("-wal", "-shm")) for entry in report["manifest"]["entries"]
        )
        with closing(sqlite3.connect(snapshot / "data/filemate.db")) as restored:
            assert restored.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


def test_confirmation_quiescence_and_stale_preview(managed: Path, tmp_path: Path) -> None:
    plan = backup.plan_backup(managed)
    target = tmp_path / "forbidden"
    with pytest.raises(ValueError, match="停写"):
        backup.create_backup(managed, target, plan["confirmation"], quiesced=False)
    with pytest.raises(ValueError, match="指纹"):
        backup.create_backup(managed, target, "wrong", quiesced=True)
    (managed / "inbox/原创复习资料.txt").write_text("新的合成材料", encoding="utf-8")
    with pytest.raises(ValueError, match="指纹"):
        backup.create_backup(managed, target, plan["confirmation"], quiesced=True)
    assert not target.exists()


def test_existing_and_nested_targets_never_overwrite(managed: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "backup"
    _create(managed, snapshot)
    with pytest.raises(ValueError, match="存在"):
        _create(managed, snapshot)
    with pytest.raises(ValueError, match="嵌套"):
        _create(managed, managed / "backup")
    with pytest.raises(ValueError, match="存在"):
        backup.plan_restore(snapshot, managed)
    with pytest.raises(ValueError, match="嵌入"):
        backup.plan_restore(snapshot, managed / "inbox/restored")
    target = tmp_path / "restore"
    plan = backup.plan_restore(snapshot, target)
    with pytest.raises(ValueError, match="指纹|变化"):
        backup.restore_backup(snapshot, target, "wrong")
    assert not target.exists()
    backup.restore_backup(snapshot, target, plan["confirmation"])
    with pytest.raises(ValueError, match="存在"):
        backup.restore_backup(snapshot, target, plan["confirmation"])


@pytest.mark.parametrize(
    "fault",
    [
        "changed",
        "missing",
        "extra",
        "duplicate",
        "traversal",
        "absolute",
        "version",
        "database",
    ],
)
def test_corrupt_backup_never_restores(managed: Path, tmp_path: Path, fault: str) -> None:
    snapshot = tmp_path / "backup"
    _create(managed, snapshot)
    file = snapshot / "data/inbox/原创复习资料.txt"
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if fault == "changed":
        file.write_bytes(b"corrupted")
    elif fault == "missing":
        file.unlink()
    elif fault == "extra":
        (snapshot / "data/inbox/extra.txt").write_text("unexpected", encoding="utf-8")
    elif fault == "duplicate":
        manifest["entries"].append(manifest["entries"][-1])
    elif fault == "traversal":
        manifest["entries"][0]["path"] = "../outside.txt"
    elif fault == "absolute":
        manifest["entries"][0]["path"] = "C:/outside.txt"
    elif fault == "version":
        manifest["format_version"] = 100
    else:
        entry = next(entry for entry in manifest["entries"] if entry["kind"] == "database")
        entry["database"]["table_counts"]["sessions"] = 1000
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / "never-created"
    with pytest.raises((ValueError, OSError)):
        backup.plan_restore(snapshot, target)
    assert not target.exists()


def test_change_during_copy_leaves_incomplete_evidence(
    managed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_copy = backup._copy

    def mutating_copy(source: Path, destination: Path) -> None:
        original_copy(source, destination)
        (managed / "inbox/原创复习资料.txt").write_text("写入竞争：合成变化", encoding="utf-8")

    monkeypatch.setattr(backup, "_copy", mutating_copy)
    target = tmp_path / "incomplete"
    with pytest.raises(ValueError, match="变化"):
        _create(managed, target)
    assert target.is_dir() and not (target / "manifest.json").exists()
    with pytest.raises(OSError):
        backup.verify_backup(target)


def test_restore_rechecks_backup_after_preview(managed: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "backup"
    _create(managed, snapshot)
    target = tmp_path / "restore"
    plan = backup.plan_restore(snapshot, target)
    (snapshot / "data/inbox/原创复习资料.txt").write_text("变化", encoding="utf-8")
    with pytest.raises(ValueError, match="校验"):
        backup.restore_backup(snapshot, target, plan["confirmation"])
    assert not target.exists()


def test_missing_identity_and_unknown_layout_fail(managed: Path) -> None:
    (managed / "identity.secret").unlink()
    with pytest.raises(ValueError, match="密钥"):
        backup.plan_backup(managed)
    (managed / "identity.secret").write_bytes(b"synthetic-only-identity-signing-key-000000")
    (managed / ".env").write_text("SYNTHETIC_KEY=test-only", encoding="utf-8")
    with pytest.raises(ValueError, match="布局"):
        backup.plan_backup(managed)


def test_environment_identity_is_preserved_and_not_printed(
    managed: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    secret = "synthetic-environment-identity-key-00000000"
    monkeypatch.setenv("FILEMATE_IDENTITY_SECRET", secret)
    snapshot = tmp_path / "backup"
    report = _create(managed, snapshot)
    assert report["manifest"]["identity_origin"] == "environment"
    assert (snapshot / "data/identity.secret").read_bytes() == secret.encode()
    monkeypatch.setattr("sys.argv", ["backup", "verify", "--backup", str(snapshot)])
    assert backup.main() == 0
    output = capsys.readouterr().out
    assert secret not in output and "u_" + "a" * 32 not in output
    assert json.loads(output)["database_count"] == 3


def test_external_file_references_are_not_silently_omitted(managed: Path, tmp_path: Path) -> None:
    with closing(sqlite3.connect(managed / "filemate.db")) as conn:
        conn.execute("UPDATE sessions SET source_path=?", (str(tmp_path / "external.txt"),))
        conn.commit()
    plan = backup.plan_backup(managed)
    assert (
        next(entry for entry in plan["entries"] if entry["path"] == "filemate.db")[
            "external_reference_count"
        ]
        == 1
    )
    with pytest.raises(ValueError, match="目录外"):
        _create(managed, tmp_path / "incomplete-local-backup")


def test_links_are_rejected(managed: Path, tmp_path: Path) -> None:
    external = tmp_path / "outside.txt"
    external.write_text("原创合成外部文件", encoding="utf-8")
    link = managed / "inbox/link.txt"
    try:
        link.symlink_to(external)
    except OSError:
        os.link(external, link)
    with pytest.raises(ValueError, match="链接|重解析"):
        backup.plan_backup(managed)


@pytest.mark.parametrize("fault", ["corrupt", "future", "gap", "foreign_key"])
def test_invalid_database_is_not_backed_up(managed: Path, tmp_path: Path, fault: str) -> None:
    path = managed / "filemate.db"
    if fault == "corrupt":
        path.write_bytes(b"not a database")
    else:
        with closing(sqlite3.connect(path)) as conn:
            if fault == "future":
                conn.execute(
                    "INSERT INTO schema_migrations(version, name) VALUES (25, 'synthetic-future')"
                )
            elif fault == "gap":
                conn.execute("DELETE FROM schema_migrations WHERE version=2")
            else:
                conn.execute(
                    "INSERT INTO processed_files(file_hash, session_id) VALUES ('synthetic', 'missing-session')"
                )
            conn.commit()
    with pytest.raises((ValueError, sqlite3.Error)):
        _create(managed, tmp_path / "invalid-backup")
    assert not (tmp_path / "invalid-backup").exists()
