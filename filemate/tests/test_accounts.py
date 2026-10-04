"""真实账户会话、恢复码轮换和资料所有权回归。"""

from __future__ import annotations

import importlib
import secrets
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from filemate.accounts import AccountError, AccountStore, validate_password
from filemate.execution.storage import SQLiteStorage

PASSWORD = secrets.token_urlsafe(24) + "a7"
NEW_PASSWORD = secrets.token_urlsafe(24) + "b8"
HEADERS = {"X-FileMate-Action": "account"}


def test_browser_credential_scope_is_private_and_stable_across_login(account_server):
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        guest = alice.get("/api/llm/status").json()["data"]["credential_scope"]
        assert register(alice, keep_guest_data=False).status_code == 200
        own = alice.get("/api/llm/status").json()["data"]["credential_scope"]
        assert own != guest
        assert register(bob, email="other@example.invalid").status_code == 200
        assert bob.get("/api/llm/status").json()["data"]["credential_scope"] != own
        alice.post("/api/auth/logout", headers=HEADERS, json={})
        assert alice.get("/api/llm/status").json()["data"]["credential_scope"] != own
        assert login(alice).status_code == 200
        assert alice.get("/api/llm/status").json()["data"]["credential_scope"] == own


@pytest.fixture
def account_server(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENV", "development")
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "anonymous")
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "data/filemate.db"))
    monkeypatch.setenv("FILEMATE_UPLOAD_DIR", str(tmp_path / "data/inbox"))
    monkeypatch.setenv("FILEMATE_ARCHIVE_DIR", str(tmp_path / "data/archive"))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module
    module._close_tenant_storages()
    module._local_storage.close()
    sys.modules.pop("server", None)


def register(client, email="synthetic@example.invalid", **kwargs):
    return client.post(
        "/api/auth/register",
        headers=HEADERS,
        json={
            "email": email,
            "display_name": "合成测试学生",
            "password": PASSWORD,
            **kwargs,
        },
    )


def login(client, email="synthetic@example.invalid", password=PASSWORD, **kwargs):
    return client.post(
        "/api/auth/login", headers=HEADERS, json={"email": email, "password": password, **kwargs}
    )


@pytest.mark.parametrize("password", ["Abcd12345", "abcd12345", "ABCD12345", "Abcd1234!", "中文ab12345", "Ab1" + "x" * 125])
def test_new_password_accepts_nine_characters_and_optional_symbols(password):
    validate_password(password)


@pytest.mark.parametrize("password", ["Abcd1234", "123456789", "abcdefghi", "abcdefg!@", "中文密码测试123", "a1" + "x" * 127, "aaaaaaa11", "password123456789"])
def test_new_password_rejects_short_unmixed_and_common_values(password):
    with pytest.raises(AccountError):
        validate_password(password)


def test_nine_character_registration_login_and_recovery(account_server):
    password = secrets.token_hex(3) + "ab7"
    replacement = secrets.token_hex(3) + "cd8"
    with TestClient(account_server.app) as client:
        for invalid in ["a1" * 4, "abcdefghi", "123456789"]:
            assert register(client, password=invalid).status_code == 400
        registered = register(client, password=password)
        assert registered.status_code == 200
        code = registered.json()["data"]["recovery_code"]
        client.post("/api/auth/logout", headers=HEADERS, json={})
        assert login(client, password=password).status_code == 200
        for invalid in ["a1" * 4, "abcdefghi", "123456789"]:
            response = client.post("/api/auth/recover", headers=HEADERS, json={
                "email": "synthetic@example.invalid", "recovery_code": code, "password": invalid,
            })
            assert response.status_code == 400
            assert client.get("/api/auth/me").json()["data"]["user"]["email"] == "synthetic@example.invalid"
        recovered = client.post("/api/auth/recover", headers=HEADERS, json={
            "email": "synthetic@example.invalid", "recovery_code": code, "password": replacement,
        })
        assert recovered.status_code == 200
        assert recovered.json()["data"]["recovery_code"] != code
        assert login(client, password=password).status_code == 401
        assert login(client, password=replacement).status_code == 200


def test_existing_password_without_digits_still_logs_in(account_server, monkeypatch):
    legacy = "legacy phrase only"
    with TestClient(account_server.app) as client:
        with monkeypatch.context() as previous_policy:
            previous_policy.setattr("filemate.accounts.validate_password", lambda _: None)
            assert register(client, password=legacy).status_code == 200
        client.post("/api/auth/logout", headers=HEADERS, json={})
        assert login(client, password=legacy).status_code == 200


def test_register_claims_guest_without_leaving_cookie_backdoor(account_server):
    with TestClient(account_server.app) as owner, TestClient(account_server.app) as old_guest:
        imported = owner.post(
            "/knowledge/import",
            files={"file": ("synthetic.txt", b"Synthetic owned learning notes")},
        )
        assert imported.status_code == 200
        source_id = imported.json()["data"]["source_id"]
        old_guest.cookies.update(owner.cookies)
        result = register(owner)
        assert result.status_code == 200
        assert len(result.json()["data"]["recovery_code"]) == 43
        assert "password" not in result.text
        assert "httponly" in result.headers["set-cookie"].lower()
        assert "samesite=lax" in result.headers["set-cookie"].lower()
        assert "max-age=2592000" in result.headers["set-cookie"].lower()
        assert owner.get(f"/knowledge/sources/{source_id}").status_code == 200
        assert old_guest.get(f"/knowledge/sources/{source_id}").status_code == 404
        assert old_guest.delete(f"/knowledge/sources/{source_id}").status_code == 404
        assert owner.post("/api/auth/logout", headers=HEADERS, json={}).status_code == 200
        assert owner.get(f"/knowledge/sources/{source_id}").status_code == 404
        assert owner.post("/api/auth/logout", headers=HEADERS, json={}).status_code == 200
        assert login(owner).status_code == 200
        assert owner.get(f"/knowledge/sources/{source_id}").status_code == 200


def test_separate_accounts_and_devices_keep_owner_scope(account_server):
    with (
        TestClient(account_server.app) as first,
        TestClient(account_server.app) as second,
        TestClient(account_server.app) as device,
    ):
        assert register(first).status_code == 200
        source_id = first.post(
            "/knowledge/import", files={"file": ("synthetic.txt", b"Synthetic private source")}
        ).json()["data"]["source_id"]
        assert register(second, "other@example.invalid").status_code == 200
        assert second.get(f"/knowledge/sources/{source_id}").status_code == 404
        assert login(device, remember=False).status_code == 200
        assert device.get(f"/knowledge/sources/{source_id}").status_code == 200
        assert (
            device.get("/api/auth/me").json()["data"]["user"]["email"]
            == "synthetic@example.invalid"
        )
        assert first.post("/api/auth/logout", headers=HEADERS, json={}).status_code == 200
        assert device.get(f"/knowledge/sources/{source_id}").status_code == 200


def test_guest_data_can_stay_separate_when_registration_opts_out(account_server):
    with TestClient(account_server.app) as client:
        source_id = client.post(
            "/knowledge/import", files={"file": ("synthetic.txt", b"Synthetic guest source")}
        ).json()["data"]["source_id"]
        assert register(client, keep_guest_data=False).status_code == 200
        assert client.get(f"/knowledge/sources/{source_id}").status_code == 404
        client.post("/api/auth/logout", headers=HEADERS, json={})
        assert client.get(f"/knowledge/sources/{source_id}").status_code == 200


def test_recovery_rotates_code_and_revokes_all_old_sessions(account_server):
    with TestClient(account_server.app) as first, TestClient(account_server.app) as device:
        code = register(first).json()["data"]["recovery_code"]
        login(device)
        result = device.post(
            "/api/auth/recover",
            headers=HEADERS,
            json={
                "email": "synthetic@example.invalid",
                "password": NEW_PASSWORD,
                "recovery_code": code,
            },
        )
        assert result.status_code == 200
        new_code = result.json()["data"]["recovery_code"]
        assert new_code != code
        assert first.get("/api/auth/me").json()["data"]["expired"] is True
        assert device.get("/knowledge/sources").status_code == 401
        assert (
            first.post(
                "/knowledge/import", files={"file": ("synthetic.txt", b"expired write")}
            ).status_code
            == 401
        )
        assert login(first).status_code == 401
        assert login(first, password=NEW_PASSWORD).status_code == 200
        payload = {
            "email": "synthetic@example.invalid",
            "password": PASSWORD,
            "recovery_code": code,
        }
        assert first.post("/api/auth/recover", headers=HEADERS, json=payload).status_code == 401
        payload["recovery_code"] = new_code
        assert first.post("/api/auth/recover", headers=HEADERS, json=payload).status_code == 200


def test_expired_session_never_silently_falls_back_to_guest(account_server):
    with TestClient(account_server.app) as client:
        register(client)
        with sqlite3.connect(account_server.DATABASE_PATH) as db:
            db.execute("UPDATE account_sessions SET expires_at=0")
        assert client.get("/knowledge/sources").status_code == 401
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/auth/me").json()["data"]["expired"] is True
        client.post("/api/auth/logout", headers=HEADERS, json={})
        assert client.get("/knowledge/sources").status_code == 200


def test_auth_csrf_invalid_fields_and_secret_redaction(account_server):
    with TestClient(account_server.app) as client:
        payload = {"email": "synthetic@example.invalid", "password": PASSWORD}
        assert client.post("/api/auth/login", json=payload).status_code == 403
        assert (
            client.post(
                "/api/auth/login",
                headers={**HEADERS, "Origin": "https://untrusted.invalid"},
                json=payload,
            ).status_code
            == 403
        )
        assert register(client, password="short").status_code == 400
        response = register(client, password=PASSWORD * 10)
        assert response.status_code == 422
        assert PASSWORD not in response.text
        assert register(client).status_code == 200
        assert register(client).status_code == 409
        response = login(client, password="incorrect password")
        assert response.status_code == 401 and "incorrect password" not in response.text
        client.post("/api/auth/logout", headers=HEADERS, json={})
        assert register(client, email="SYNTHETIC@EXAMPLE.INVALID").status_code == 409


def test_login_attempt_budget_persists_and_does_not_run_hash_after_limit(
    account_server, monkeypatch
):
    with TestClient(account_server.app) as client:
        for _ in range(10):
            assert login(client, password="wrong").status_code == 401
        monkeypatch.setattr(
            "filemate.accounts._verify_password",
            lambda *args: pytest.fail("rate limit must precede hashing"),
        )
        response = login(client, password="wrong")
        assert response.status_code == 429 and response.headers["retry-after"] == "900"


def test_password_and_tokens_are_hashed_and_backup_is_usable(account_server, tmp_path):
    with TestClient(account_server.app) as client:
        code = register(client).json()["data"]["recovery_code"]
        token = client.cookies.get("filemate_session")
        backup = tmp_path / "restored.db"
        with (
            sqlite3.connect(account_server.DATABASE_PATH) as db,
            sqlite3.connect(backup) as restored,
        ):
            row = db.execute("SELECT password_hash,recovery_hash FROM accounts").fetchone()
            assert row[0].startswith("scrypt-v1$")
            assert PASSWORD not in row[0] and code != row[1]
            assert db.execute("SELECT token_hash FROM account_sessions").fetchone()[0] != token
            db.backup(restored)
        store = AccountStore(backup)
        assert store.resolve_session(token)["user"]["email"] == "synthetic@example.invalid"
        assert store.recover("synthetic@example.invalid", code, NEW_PASSWORD)


def test_concurrent_registration_and_recovery_are_single_use(tmp_path):
    db = tmp_path / "accounts.db"
    storage = SQLiteStorage(db)
    storage.init_schema()
    store = AccountStore(db)

    def attempt_register():
        try:
            return store.register(
                "race@example.invalid", PASSWORD, "合成测试", "u_" + "a" * 32, True
            )[2]
        except AccountError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt_register(), range(2)))
    codes = [item for item in results if item]
    assert len(codes) == 1

    def attempt_recover():
        try:
            return store.recover("race@example.invalid", codes[0], NEW_PASSWORD)
        except AccountError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt_recover(), range(2)))
    assert len([item for item in results if item]) == 1
    storage.close()
