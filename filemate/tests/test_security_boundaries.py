"""公网与桌面端必须共同遵守的安全边界回归测试。"""

from __future__ import annotations

import importlib
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import SQLiteStorage


@pytest.fixture()
def audit_server_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, SQLiteStorage]]:
    """使用临时数据库和上传目录加载服务。"""
    runtime_dir = tmp_path / "runtime"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FILEMATE_ENV", "development")
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(runtime_dir))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(runtime_dir / "bootstrap.db"))
    monkeypatch.setenv("FILEMATE_UPLOAD_DIR", str(runtime_dir / "inbox"))
    monkeypatch.setenv("FILEMATE_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    module._storage.close()

    storage = SQLiteStorage(tmp_path / "audit.db")
    storage.init_schema()
    module._storage = storage
    module.UPLOAD_ROOT = runtime_dir / "inbox"
    module.ARCHIVE_DIR = tmp_path / "archive"
    module._sessions.clear()
    yield module, storage

    module._sessions.clear()
    storage.close()
    sys.modules.pop("server", None)


@pytest.fixture()
def anonymous_server_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ModuleType]:
    """在临时目录中启用公网匿名隔离模式。"""
    runtime_dir = tmp_path / "anonymous-runtime"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FILEMATE_ENV", "development")
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "anonymous")
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(runtime_dir))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(runtime_dir / "local.db"))
    monkeypatch.setenv("FILEMATE_UPLOAD_DIR", str(runtime_dir / "inbox"))
    monkeypatch.setenv("FILEMATE_ARCHIVE_DIR", str(runtime_dir / "archive"))
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module

    close_tenants = getattr(module, "_close_tenant_storages", None)
    if close_tenants is not None:
        close_tenants()
    local_storage = getattr(module, "_local_storage", None)
    if local_storage is not None:
        local_storage.close()
    sys.modules.pop("server", None)


def test_ics_endpoint_rejects_entity_path_injection(
    audit_server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """Session 可编辑字段不得成为任意本地文件读取入口。"""
    module, storage = audit_server_module
    secret = tmp_path / "private.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")
    session_id = "security-ics-path"
    storage.create_session(session_id, tmp_path / "source.txt")

    with TestClient(module.app) as client:
        patched = client.patch(
            f"/sessions/{session_id}",
            json={"edits": {"entities": {"ics_path": str(secret)}}},
        )
        assert patched.status_code == 200
        response = client.get(f"/sessions/{session_id}/ics")

    assert response.status_code in {403, 404}
    assert "TOP-SECRET-CONTENT" not in response.text


@pytest.mark.parametrize(
    ("path", "form"),
    [
        ("/ai/summarize", {"max_length": "500"}),
        ("/ai/knowledge-cards", {"num_cards": "5"}),
        ("/ai/questions", {"num_questions": "5"}),
        ("/ai/notes", {"format": "outline"}),
        (
            "/ai/study-plan",
            {"exam_date": "2026-12-31", "daily_minutes": "60"},
        ),
    ],
)
def test_failed_ai_upload_does_not_leave_orphaned_copy(
    audit_server_module: tuple[ModuleType, SQLiteStorage],
    path: str,
    form: dict[str, str],
) -> None:
    """解析或模型失败后必须回收未入库的托管副本。"""
    module, _ = audit_server_module

    with TestClient(module.app) as client:
        response = client.post(
            path,
            data=form,
            files={"file": ("blank.txt", io.BytesIO(b"   "), "text/plain")},
        )

    assert response.status_code in {401, 403, 422, 502}
    assert not [item for item in module.UPLOAD_ROOT.rglob("*") if item.is_file()]


def test_untrusted_browser_origin_cannot_mutate_local_sidecar(
    audit_server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    """CORS 不是 CSRF 防护；恶意网页的 simple POST 必须在入库前被拒绝。"""
    module, storage = audit_server_module

    with TestClient(module.app) as client:
        response = client.post(
            "/knowledge/import",
            headers={"Origin": "https://attacker.example"},
            files={
                "file": (
                    "poison.txt",
                    io.BytesIO("恶意网页注入的资料".encode()),
                    "text/plain",
                )
            },
        )

    assert response.status_code in {401, 403}
    assert storage.list_sources() == []


def test_source_detail_never_exposes_server_filesystem_path(
    audit_server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """公共 API 只返回业务字段，不暴露服务器绝对路径。"""
    module, storage = audit_server_module
    source_id = storage.save_source(
        original_name="course.txt",
        source_path=str(tmp_path / "runtime" / "inbox" / "private" / "course.txt"),
        raw_text="course body",
        file_hash="security-source-path",
    )

    with TestClient(module.app) as client:
        response = client.get(f"/knowledge/sources/{source_id}")

    if response.status_code == 200:
        payload = response.json()["data"]
        assert "source_path" not in payload
        assert "workspace_id" not in payload


def test_cross_origin_preflight_does_not_advertise_mutation_access(
    audit_server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    """未信任 Origin 的预检不得返回允许头。"""
    module, _ = audit_server_module

    with TestClient(module.app) as client:
        response = client.options(
            "/knowledge/import",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code in {400, 401, 403}
    assert "access-control-allow-origin" not in response.headers


def test_health_check_does_not_create_anonymous_tenant(
    anonymous_server_module: ModuleType,
) -> None:
    """健康检查和掉 cookie 客户不应制造空租户数据库。"""
    module = anonymous_server_module
    for _ in range(3):
        with TestClient(module.app) as client:
            client.cookies.clear()
            response = client.get("/api/health")
            assert response.status_code == 200

    users_root = module.DATA_DIR / "users"
    tenant_databases = list(users_root.rglob("filemate.db")) if users_root.exists() else []
    assert tenant_databases == []


def test_anonymous_tenant_storage_cache_is_bounded(
    anonymous_server_module: ModuleType,
) -> None:
    """长时运行时租户存储缓存不得无限持有数据库连接。"""
    module = anonymous_server_module
    expected_limit = int(getattr(module, "TENANT_STORAGE_CACHE_LIMIT", 32))
    for index in range(expected_limit + 5):
        module._tenant_storage(f"u_{index:032x}")

    tenant_cache = getattr(module, "_tenant_storages", {})
    assert len(tenant_cache) <= expected_limit
