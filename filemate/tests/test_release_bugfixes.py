"""合成回归：上传落盘失败与独立就绪探针，不涉及真实学习资料。"""

import io
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from filemate.tests import test_accounts, test_digital_human

account_server = test_accounts.account_server
local_server = test_digital_human.local_server


@pytest.mark.parametrize("filename", ["a" * 256 + ".txt", "课程" * 45 + ".txt",
                                      "NUL.txt", "lesson:one.txt", "lesson?.txt"])
def test_upload_rejects_unportable_names_without_creating_files(local_server, filename, monkeypatch, tmp_path):
    module, _ = local_server
    root = tmp_path / "inbox"
    monkeypatch.setattr(module, "UPLOAD_ROOT", root)
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": (filename, b"synthetic lesson", "text/plain")})
        assert response.status_code == 400
        assert not root.exists()


def test_valid_chinese_upload_and_windows_path_remain_readable(local_server, monkeypatch, tmp_path):
    module, _ = local_server
    monkeypatch.setattr(module, "UPLOAD_ROOT", tmp_path / "inbox")
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": (
            "C:\\fakepath\\数据结构课程.txt", "合成资料：栈采用后进先出。".encode(), "text/plain",
        )})
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert len(list(module.UPLOAD_ROOT.glob("*/数据结构课程.txt"))) == 1


@pytest.mark.asyncio
async def test_upload_disk_failure_cleans_partial_file(local_server, monkeypatch, tmp_path):
    module, _ = local_server
    root = tmp_path / "inbox"
    monkeypatch.setattr(module, "UPLOAD_ROOT", root)
    original_open = Path.open

    def fail_write(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.suffix == ".txt" and mode == "xb":
            stream.write(b"partial")
            stream.close()
            raise OSError("synthetic-sensitive-disk-error")
        return stream

    monkeypatch.setattr(Path, "open", fail_write)
    with pytest.raises(HTTPException) as error:
        await module._save_upload(UploadFile(filename="课程.txt", file=io.BytesIO(b"synthetic data")))
    assert error.value.status_code == 503
    assert "sensitive" not in error.value.detail
    assert list(root.iterdir()) == []


def test_readiness_is_read_only_and_independent_of_account_resolution(account_server, monkeypatch):
    module = account_server

    def unavailable(*args):
        raise sqlite3.OperationalError("synthetic-private-session-error")

    monkeypatch.setattr(module._accounts, "resolve_session", unavailable)
    with TestClient(module.app) as client:
        client.cookies.set(module.ACCOUNT_COOKIE_NAME, "synthetic-expired-session")
        health = client.get("/api/health")
        ready = client.get("/api/ready")
        assert health.status_code == ready.status_code == 200
        assert ready.json()["data"]["checks"] == {
            "database": "ready", "accounts": "ready", "governance": "ready",
        }
        assert ready.headers["cache-control"] == "no-store"
        assert "set-cookie" not in ready.headers and "set-cookie" not in health.headers
        assert not (module.DATA_DIR / "users").exists()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "schema"])
def test_readiness_fails_without_creating_or_repairing_database(local_server, monkeypatch, tmp_path, failure):
    module, storage = local_server
    broken = tmp_path / "broken.db"
    if failure == "corrupt":
        broken.write_bytes(b"synthetic corrupt database")
    elif failure == "schema":
        with sqlite3.connect(broken) as connection:
            connection.execute("CREATE TABLE schema_migrations(version INTEGER)")
            connection.execute("INSERT INTO schema_migrations VALUES(1)")
    before = broken.read_bytes() if broken.exists() else None
    monkeypatch.setattr(storage, "db_path", broken)
    with TestClient(module.app) as client:
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.json()["data"]["checks"]["database"] == "unavailable"
        assert "broken.db" not in response.text
        assert client.get("/api/health").status_code == 200
    assert (broken.read_bytes() if broken.exists() else None) == before


def test_governance_outage_is_not_reported_as_ready(local_server, monkeypatch, tmp_path):
    module, _ = local_server
    broken = tmp_path / "broken-ledger.db"
    broken.write_bytes(b"synthetic corrupt ledger")
    with TestClient(module.app) as client:
        monkeypatch.setattr(module._model_budget, "path", broken)
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.json()["data"]["checks"]["governance"] == "unavailable"
        assert client.get("/api/health").status_code == 200
    assert broken.read_bytes() == b"synthetic corrupt ledger"
