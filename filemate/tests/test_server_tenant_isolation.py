"""公网匿名身份的数据隔离回归测试。"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from filemate.core.session import ProcessingSession, SessionStatus
from filemate.execution.storage import SQLiteStorage


@pytest.fixture()
def isolated_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ModuleType]:
    """以匿名隔离模式加载服务。"""
    monkeypatch.setenv("FILEMATE_ENV", "development")
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "anonymous")
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "legacy.db"))
    monkeypatch.setenv("FILEMATE_UPLOAD_DIR", str(tmp_path / "legacy-inbox"))
    monkeypatch.setenv("FILEMATE_ARCHIVE_DIR", str(tmp_path / "legacy-archive"))
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module
    module._close_tenant_storages()
    module._storage.close()
    sys.modules.pop("server", None)


def test_anonymous_clients_cannot_read_or_mutate_each_others_data(
    isolated_server: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """资料的列表、详情、派生写入和删除均不能跨身份。"""
    module = isolated_server
    from filemate.perception import FileParser

    monkeypatch.setattr(
        FileParser,
        "parse",
        lambda self, path: {"raw_text": "光合作用将光能转化为化学能。"},
    )

    with TestClient(module.app) as alice, TestClient(module.app) as bob:
        source_response = alice.post(
            "/knowledge/import",
            files={"file": ("alice.txt", b"alice-private")},
        )
        assert source_response.status_code == 200
        source_id = source_response.json()["data"]["source_id"]

        assert [
            item["source_id"]
            for item in alice.get("/knowledge/sources").json()["data"]
        ] == [source_id]
        assert bob.get("/knowledge/sources").json()["data"] == []

        assert bob.get(f"/knowledge/sources/{source_id}").status_code == 404
        assert bob.get(
            f"/knowledge/sources/{source_id}/lineage"
        ).status_code == 404
        assert bob.get(
            f"/knowledge/sources/{source_id}/artifacts"
        ).status_code == 404
        assert bob.post(
            f"/knowledge/sources/{source_id}/contexts"
        ).status_code == 404
        assert bob.put(
            f"/knowledge/sources/{source_id}/rights",
            json={"rights_status": "self_owned", "sharing_scope": "private"},
        ).status_code == 404
        assert bob.delete(f"/knowledge/sources/{source_id}").status_code == 404

        assert alice.get(f"/knowledge/sources/{source_id}").status_code == 200
        assert alice.delete(f"/knowledge/sources/{source_id}").status_code == 200


def test_anonymous_clients_cannot_access_session_execution_routes(
    isolated_server: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session 的列表、详情、编辑、确认和撤销必须使用同一身份。"""
    module = isolated_server
    main_module = importlib.import_module("main")

    async def fake_process_single(
        file_path: str,
        *,
        skip_calendar: bool,
        db_path: str,
    ) -> ProcessingSession:
        del skip_calendar
        storage = SQLiteStorage(db_path)
        storage.init_schema()
        session = ProcessingSession(
            session_id="alice-session",
            source_path=file_path,
            status=SessionStatus.DONE,
            category="参考资料",
            suggested_name="alice.txt",
        )
        storage.create_session(session.session_id, file_path)
        storage.update_session(
            session.session_id,
            status="done",
            category=session.category,
            suggested_name=session.suggested_name,
        )
        storage.close()
        return session

    monkeypatch.setattr(main_module, "process_single", fake_process_single)

    with TestClient(module.app) as alice, TestClient(module.app) as bob:
        created = alice.post(
            "/process",
            files={"file": ("alice.txt", b"private-session")},
        )
        assert created.status_code == 200
        session_id = created.json()["data"]["session_id"]

        assert [
            item["session_id"] for item in alice.get("/sessions").json()["data"]
        ] == [session_id]
        assert bob.get("/sessions").json()["data"] == []

        assert bob.get(f"/sessions/{session_id}").status_code == 404
        assert bob.patch(
            f"/sessions/{session_id}",
            json={"edits": {"category": "作业"}},
        ).status_code == 404
        assert bob.post(
            f"/sessions/{session_id}/confirm",
            json={"accepted": False},
        ).status_code == 404
        assert bob.post(f"/sessions/{session_id}/undo").status_code == 404
        assert bob.get(
            f"/sessions/{session_id}/executions"
        ).status_code == 404
        assert bob.get(f"/sessions/{session_id}/ics").status_code == 404
        assert alice.get(f"/sessions/{session_id}").status_code == 200


def test_invalid_or_forged_identity_cookie_cannot_select_another_tenant(
    isolated_server: ModuleType,
) -> None:
    """伪造 cookie 必须被替换，不能将访客路由到指定目录。"""
    module = isolated_server
    with TestClient(module.app) as client:
        response = client.get(
            "/api/health",
            cookies={module.IDENTITY_COOKIE_NAME: "u_" + "a" * 32 + ".forged"},
        )
        assert response.status_code == 200
        issued = response.cookies.get(module.IDENTITY_COOKIE_NAME)
        assert issued
        assert issued != "u_" + "a" * 32 + ".forged"
        assert module._verify_identity_cookie(issued) is not None


def test_health_issues_identity_without_creating_tenant_database(
    isolated_server: ModuleType,
) -> None:
    """健康检查不应被无 cookie 请求滥用来批量创建数据库。"""
    module = isolated_server
    for _ in range(20):
        with TestClient(module.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert response.cookies.get(module.IDENTITY_COOKIE_NAME)

    users_root = module.DATA_DIR / "users"
    assert not users_root.exists()
    assert module._tenant_storages == {}


def test_tenant_storage_cache_is_bounded_and_closes_lru(
    isolated_server: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """匿名访客数增长时，打开的 SQLite 连接数仍受上限约束。"""
    module = isolated_server
    monkeypatch.setattr(module, "MAX_OPEN_TENANT_STORAGES", 8)

    for _ in range(12):
        with TestClient(module.app) as client:
            assert client.get("/knowledge/sources").status_code == 200

    assert len(module._tenant_storages) == 8
