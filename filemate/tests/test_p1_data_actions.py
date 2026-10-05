# ruff: noqa: F811
"""资料删除的真实事务、确认凭据和失败回滚回归。"""

import json

import pytest
from fastapi.testclient import TestClient

from filemate.execution import data_actions
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_source_delete_requires_preview_and_detects_same_count_edit(server_module):
    module, store = server_module
    sid = store.save_source(original_name="secret.txt", source_path="/outside/secret.txt", raw_text="private")
    aid = store.save_artifact(artifact_type="notes", source_id=sid, content="first")
    with TestClient(module.app) as client:
        assert client.delete(f"/knowledge/sources/{sid}").status_code == 422
        preview = client.get(f"/knowledge/sources/{sid}/delete-preview").json()["data"]
        assert "source_path" not in preview and "path" not in preview["managed_file"]
        body = {"confirmed": True, "confirmation_token": preview["confirmation_token"]}
        assert client.request("DELETE", f"/knowledge/sources/{sid}", json={**body, "confirmed": False}).status_code == 422
        store.update_artifact(aid, title="edited", content="second")
        assert client.request("DELETE", f"/knowledge/sources/{sid}", json=body).status_code == 409
        assert store.get_source(sid)
        body["confirmation_token"] = client.get(f"/knowledge/sources/{sid}/delete-preview").json()["data"]["confirmation_token"]
        result = client.request("DELETE", f"/knowledge/sources/{sid}", json=body)
        assert result.status_code == 200
        assert client.request("DELETE", f"/knowledge/sources/{sid}", json=body).json() == result.json()
        rows = store._conn().execute("SELECT * FROM data_action_audit").fetchall()
        assert len(rows) == 1
        audit = json.dumps([dict(row) for row in rows])
        assert "secret.txt" not in audit and "private" not in audit and body["confirmation_token"] not in audit


def test_source_delete_file_and_database_rollback(server_module, monkeypatch):
    module, store = server_module
    module.UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    path = module.UPLOAD_ROOT / "keep.txt"
    path.write_bytes(b"keep this data")
    sid = store.save_source(original_name="keep.txt", source_path=str(path), raw_text="keep")
    with TestClient(module.app) as client:
        preview = client.get(f"/knowledge/sources/{sid}/delete-preview").json()["data"]
        def fail(*args):
            raise RuntimeError("injected transaction failure")
        monkeypatch.setattr(data_actions, "finish", fail)
        with pytest.raises(RuntimeError, match="injected"):
            client.request("DELETE", f"/knowledge/sources/{sid}", json={"confirmed": True, "confirmation_token": preview["confirmation_token"]})
    assert store.get_source(sid) and path.read_bytes() == b"keep this data"
    assert not list(module.UPLOAD_ROOT.glob(".delete-*"))
    assert store._conn().execute("SELECT COUNT(*) FROM data_action_audit").fetchone()[0] == 0


def test_source_delete_preserves_shared_upload(server_module):
    module, store = server_module
    module.UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    path = module.UPLOAD_ROOT / "shared.txt"
    path.write_bytes(b"shared")
    sid = store.save_source(original_name="shared.txt", source_path=str(path))
    other = store.save_source(original_name="other.txt", source_path=str(path))
    with TestClient(module.app) as client:
        token = client.get(f"/knowledge/sources/{sid}/delete-preview").json()["data"]["confirmation_token"]
        assert client.request("DELETE", f"/knowledge/sources/{sid}", json={"confirmed": True, "confirmation_token": token}).status_code == 200
    assert path.exists() and store.get_source(other)
