"""V2.1 数字人元数据、租户隔离与关闭边界回归。"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import SQLiteStorage


@pytest.fixture()
def local_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, SQLiteStorage]]:
    """为 API 测试建立隔离数据库。"""
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "filemate.db"))
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "local")
    monkeypatch.delenv("FILEMATE_ENABLE_DIGITAL_HUMAN", raising=False)
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module, module._local_storage
    module._close_tenant_storages()
    module._local_storage.close()
    sys.modules.pop("server", None)


def _request(length: int, **extra: object) -> dict[str, object]:
    return {
        "text_length": length,
        "avatar_id": "filemate-campus",
        "voice_id": "default",
        "provider": "web_speech",
        **extra,
    }


def test_playback_lifecycle_and_minimal_storage(
    local_server: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = local_server
    with TestClient(module.app) as client:
        for length in (50, 500):
            created = client.post("/api/digital-human/playbacks", json=_request(length))
            assert created.status_code == 200
            playback = created.json()["data"]
            assert playback["text_length"] == length
            assert playback["module_version"] == "2.1"
            assert playback["status"] == "started"
            assert "content" not in playback and "audio" not in playback
            playback_id = playback["playback_id"]
            finished = client.patch(
                f"/api/digital-human/playbacks/{playback_id}",
                json={"status": "completed"},
            )
            assert finished.status_code == 200
            repeated = client.patch(
                f"/api/digital-human/playbacks/{playback_id}",
                json={"status": "failed", "error_code": "late_event"},
            )
            assert repeated.json()["data"]["status"] == "completed"
        listed = client.get("/api/digital-human/playbacks")
        assert len(listed.json()["data"]) == 2
        assert client.delete(
            f"/api/digital-human/playbacks/{playback_id}",
        ).json()["data"]["deleted"] is True
        assert client.delete(
            f"/api/digital-human/playbacks/{playback_id}",
        ).json()["data"]["deleted"] is False
        assert len(client.get("/api/digital-human/playbacks").json()["data"]) == 1
        assert client.post(
            f"/api/digital-human/playbacks/{playback_id}/restore",
        ).json()["data"]["restored"] is True
        assert client.post(
            f"/api/digital-human/playbacks/{playback_id}/restore",
        ).json()["data"]["restored"] is False
        assert len(client.get("/api/digital-human/playbacks").json()["data"]) == 2
    reopened = SQLiteStorage(storage.db_path)
    reopened.init_schema()
    assert reopened.get_schema_version() == 21
    assert len(reopened.list_digital_human_playbacks()) == 2
    assert "digital_human_playbacks" in {
        row["name"] for row in reopened._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    reopened.close()


def test_rejects_invalid_and_non_assistant_context(
    local_server: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = local_server
    storage.save_document_context(
        ctx_id="lecture-context", context_text="资料片段",
        chat_history=[
            {"role": "user", "content": "问题"},
            {"role": "assistant", "content": "讲解内容"},
        ],
    )
    with TestClient(module.app) as client:
        assert client.post("/api/digital-human/playbacks", json=_request(0)).status_code == 422
        assert client.post("/api/digital-human/playbacks", json=_request(5001)).status_code == 422
        assert client.post("/api/digital-human/playbacks", json=_request(2, context_id="lecture-context", message_index=0)).status_code == 422
        assert client.post("/api/digital-human/playbacks", json=_request(3, context_id="lecture-context", message_index=1)).status_code == 409
        assert client.post("/api/digital-human/playbacks", json=_request(4, context_id="lecture-context", message_index=1)).status_code == 200
        assert client.post("/api/digital-human/playbacks", json=_request(4, context_id="other", message_index=1)).status_code == 404
        assert client.post("/api/digital-human/playbacks", json=_request(4, context_id="lecture-context")).status_code == 422


def test_feature_can_be_disabled_without_breaking_health(
    local_server: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _ = local_server
    with TestClient(module.app) as client:
        monkeypatch.setenv("FILEMATE_ENABLE_DIGITAL_HUMAN", "0")
        assert client.get("/api/digital-human/playbacks").status_code == 503
        assert client.post("/api/digital-human/playbacks", json=_request(50)).status_code == 503
        assert client.get("/api/health").status_code == 200


def test_anonymous_browsers_do_not_share_playback_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "tenant-data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "bootstrap.db"))
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "anonymous")
    monkeypatch.delenv("FILEMATE_ENABLE_DIGITAL_HUMAN", raising=False)
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    try:
        with TestClient(module.app) as alice, TestClient(module.app) as bob:
            first = alice.post("/api/digital-human/playbacks", json=_request(50))
            assert first.status_code == 200
            assert len(alice.get("/api/digital-human/playbacks").json()["data"]) == 1
            assert bob.get("/api/digital-human/playbacks").json()["data"] == []
            identifier = first.json()["data"]["playback_id"]
            assert bob.patch(
                f"/api/digital-human/playbacks/{identifier}",
                json={"status": "stopped"},
            ).status_code == 404
            assert bob.delete(
                f"/api/digital-human/playbacks/{identifier}",
            ).json()["data"]["deleted"] is False
            assert bob.post(
                f"/api/digital-human/playbacks/{identifier}/restore",
            ).json()["data"]["restored"] is False
    finally:
        module._close_tenant_storages()
        module._local_storage.close()
        sys.modules.pop("server", None)


@pytest.mark.parametrize("overrides", [
    {"text_length": -1},
    {"text_length": 5001},
    {"text_length": "invalid"},
    {"avatar_id": "unpublished"},
    {"voice_id": ""},
    {"voice_id": "x" * 161},
    {"provider": "unknown"},
    {"message_index": -1},
])
def test_invalid_metadata_never_writes_records(
    local_server: tuple[ModuleType, SQLiteStorage],
    overrides: dict[str, object],
) -> None:
    module, storage = local_server
    with TestClient(module.app) as client:
        response = client.post(
            "/api/digital-human/playbacks", json=_request(50, **overrides),
        )
        assert response.status_code == 422
        assert response.json()["success"] is False
        assert storage.list_digital_human_playbacks() == []


def test_maximum_length_unicode_and_original_answer_survive_failure_and_delete(
    local_server: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = local_server
    answer = "𠮷" * 5000
    messages = [{"role": "assistant", "content": f"  {answer}\n"}]
    storage.save_document_context(
        ctx_id="unicode-answer", context_text="合成回归资料", chat_history=messages,
    )
    with TestClient(module.app) as client:
        response = client.post(
            "/api/digital-human/playbacks",
            json=_request(5000, context_id="unicode-answer", message_index=0),
        )
        assert response.status_code == 200
        playback_id = response.json()["data"]["playback_id"]
        result = client.patch(
            f"/api/digital-human/playbacks/{playback_id}",
            json={"status": "failed", "error_code": "speech_error"},
        )
        assert result.json()["data"]["error_code"] == "speech_error"
        client.delete(f"/api/digital-human/playbacks/{playback_id}")
        client.post(f"/api/digital-human/playbacks/{playback_id}/restore")
        assert storage.get_document_context("unicode-answer")["chat_history"] == messages
        assert storage.get_digital_human_playback(playback_id)["status"] == "failed"


def test_disabled_feature_blocks_all_mutations_but_keeps_saved_answers(
    local_server: tuple[ModuleType, SQLiteStorage], monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, storage = local_server
    storage.save_document_context(
        ctx_id="retained-answer", context_text="资料",
        chat_history=[{"role": "assistant", "content": "原有答案"}],
    )
    with TestClient(module.app) as client:
        playback_id = client.post(
            "/api/digital-human/playbacks", json=_request(50),
        ).json()["data"]["playback_id"]
        monkeypatch.setenv("FILEMATE_ENABLE_DIGITAL_HUMAN", "0")
        path = f"/api/digital-human/playbacks/{playback_id}"
        assert client.patch(path, json={"status": "stopped"}).status_code == 503
        assert client.delete(path).status_code == 503
        assert client.post(f"{path}/restore").status_code == 503
        assert client.get("/ai/contexts/retained-answer").status_code == 200
        assert client.get("/knowledge/sources").status_code == 200
        assert storage.get_digital_human_playback(playback_id)["status"] == "started"
