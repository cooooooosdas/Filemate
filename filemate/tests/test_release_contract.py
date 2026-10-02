"""发布版本、生产资源策略和真实演示网关合同回归。"""

from __future__ import annotations

import base64
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import pytest
from packaging.version import Version

from filemate import __version__

ROOT = Path(__file__).resolve().parents[2]
TEST_PASSWORD = secrets.token_urlsafe(24)
AUTHORIZATION = "Basic " + base64.b64encode(f"release-test:{TEST_PASSWORD}".encode()).decode()
HTTP_CLIENT = build_opener(ProxyHandler({}))


def _json_file(relative_path: str) -> dict[str, Any]:
    """读取仓库发布配置。"""
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "relative_path",
    [
        "filemate/web/package.json",
        "filemate/web/package-lock.json",
        "filemate/web/src-tauri/tauri.conf.json",
    ],
)
def test_release_json_versions_match_backend(relative_path: str) -> None:
    config = _json_file(relative_path)
    assert config["version"] == __version__
    if relative_path.endswith("package-lock.json"):
        assert config["packages"][""]["version"] == __version__


@pytest.mark.parametrize(
    ("relative_path", "package"),
    [
        ("uv.lock", "filemate-campus-twin"),
        ("filemate/web/src-tauri/Cargo.lock", "filemate-desktop"),
    ],
)
def test_release_lock_versions_match_backend(relative_path: str, package: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(rf'name = "{re.escape(package)}"\r?\nversion = "([^"]+)"', text)
    assert match is not None
    assert Version(match.group(1)) == Version(__version__)


@pytest.mark.parametrize(
    "relative_path",
    [
        "pyproject.toml",
        "filemate/web/src-tauri/Cargo.toml",
    ],
)
def test_release_manifest_versions_match_backend(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match is not None
    assert Version(match.group(1)) == Version(__version__)


@pytest.mark.parametrize("target", ["desktop", "caddy", "nginx"])
def test_release_csp_supports_local_vision_and_recording(target: str) -> None:
    if target == "desktop":
        csp = _json_file("filemate/web/src-tauri/tauri.conf.json")["app"]["security"]["csp"]
    else:
        config_path = "deploy/Caddyfile" if target == "caddy" else "deploy/nginx.filemate.conf"
        config = (ROOT / config_path).read_text(encoding="utf-8")
        csp = re.search(r'Content-Security-Policy "([^"]+)"', config).group(1)
    directives = {entry.split()[0]: entry.split()[1:] for entry in csp.split(";") if entry.strip()}
    assert "'wasm-unsafe-eval'" in directives["script-src"]
    assert "'unsafe-eval'" not in directives["script-src"]
    assert "blob:" in directives["media-src"]
    assert "'self'" in directives["worker-src"]
    assert directives["object-src"] == ["'none'"]


def test_nginx_vision_assets_do_not_match_interview_api_prefix() -> None:
    config = (ROOT / "deploy/nginx.filemate.conf").read_text(encoding="utf-8")
    assert "~^/interview 1;" not in config
    assert "~^/interview(/|$) 1;" in config
    for prefix in ("/interview-vision/", "/assets/"):
        block = re.search(r"location \^~ " + re.escape(prefix) + r"\s*\{([\s\S]*?)\n    \}", config)
        assert block is not None
        assert "try_files $uri =404;" in block.group(1)
        assert "proxy_pass" not in block.group(1)
        assert "gzip on;" in block.group(1)
    assert "application/wasm wasm;" in config
    assert "rate=120r/m" in config and "rate=6r/m" in config


def test_desktop_toolchain_uses_persistent_app_data() -> None:
    source = (ROOT / "filemate/web/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    assert '.env("FILEMATE_CPP_TOOLCHAIN_DIR", data_dir.join("cpp-toolchain"))' in source


def test_packaged_smoke_restores_loopback_proxy_setting() -> None:
    source = (ROOT / "scripts/smoke_sidecar.ps1").read_text(encoding="utf-8")
    assert "$previousProxy = [Net.WebRequest]::DefaultWebProxy" in source
    assert "[Net.WebRequest]::DefaultWebProxy = $null" in source
    assert source.rstrip().endswith("[Net.WebRequest]::DefaultWebProxy = $previousProxy\n}")


def test_sidecar_explicitly_bundles_report_assets_without_editable_install() -> None:
    source = (ROOT / "scripts/build_sidecar.ps1").read_text(encoding="utf-8")
    assert '"$interviewAssets;filemate/interview_review/assets"' in source
    assert (
        ROOT / "filemate/interview_review/assets/NotoSansSC-Regular.ttf"
    ).stat().st_size > 1_000_000


def test_sidecar_hash_evidence_does_not_require_parent_powershell_modules() -> None:
    source = (ROOT / "scripts/smoke_sidecar.ps1").read_text(encoding="utf-8")
    assert "Get-FileHash" not in source
    assert "$hasher.ComputeHash($stream)" in source


class _SyntheticBackend(BaseHTTPRequestHandler):
    """只用于验证路由转发的合成上游，不模拟学习功能。"""

    def do_GET(self) -> None:
        body = json.dumps({"synthetic_route_echo": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture()
def release_gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """启动真实网关进程和独立合成上游。"""
    node = shutil.which("node")
    assert node, "发布网关验收需要 Node.js；请先执行 scripts/dev.ps1 -Setup"
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>release-test-only</html>", encoding="utf-8")
    (static / "model.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
    backend = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticBackend)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    monkeypatch.setenv("FILEMATE_GATEWAY_PORT", "0")
    monkeypatch.setenv("FILEMATE_GATEWAY_BACKEND", f"http://127.0.0.1:{backend.server_port}")
    monkeypatch.setenv("FILEMATE_WEB_DIST", str(static))
    monkeypatch.setenv("FILEMATE_BASIC_USER", "release-test")
    monkeypatch.setenv("FILEMATE_BASIC_PASSWORD", TEST_PASSWORD)
    process = subprocess.Popen(
        [node, str(ROOT / "scripts/demo_gateway.mjs")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        # 端口由操作系统分配，不与真实服务争抢固定端口。
        startup = process.stdout.readline()
        match = re.search(r"http://127\.0\.0\.1:(\d+)", startup)
        assert match and int(match.group(1)) > 0, startup
        base = match.group(0)
        for _ in range(20):
            try:
                _gateway_get(base)
                break
            except URLError:
                time.sleep(0.05)
        yield base
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
        backend.shutdown()
        backend.server_close()


def _gateway_get(
    base: str,
    pathname: str = "/",
    accept: str = "application/json",
) -> HTTPResponse:
    """使用合成测试凭据请求临时网关。"""
    request = Request(base + pathname, headers={"Authorization": AUTHORIZATION, "Accept": accept})
    return HTTP_CLIENT.open(request, timeout=5)


@pytest.mark.parametrize("pathname", ["/goals", "/trust/overview", "/agents/memories/test"])
def test_release_gateway_routes_existing_modules(release_gateway: str, pathname: str) -> None:
    with _gateway_get(release_gateway, pathname) as response:
        assert json.loads(response.read())["synthetic_route_echo"] == pathname


def test_release_gateway_returns_frontend_for_navigation(release_gateway: str) -> None:
    with _gateway_get(release_gateway, "/goals", "text/html") as response:
        assert b"release-test-only" in response.read()


def test_release_gateway_wasm_mime_and_security_headers(release_gateway: str) -> None:
    with _gateway_get(release_gateway, "/model.wasm") as response:
        assert response.headers["Content-Type"] == "application/wasm"
        assert "'wasm-unsafe-eval'" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    with _gateway_get(release_gateway) as response:
        assert response.headers["Cache-Control"] == "no-cache"


def test_release_gateway_missing_static_asset_is_not_html(release_gateway: str) -> None:
    with pytest.raises(HTTPError) as missing:
        _gateway_get(release_gateway, "/missing.wasm")
    assert missing.value.code == 404


def test_release_gateway_survives_frontend_replacement(
    release_gateway: str, tmp_path: Path
) -> None:
    (tmp_path / "static/index.html").unlink()
    with pytest.raises(HTTPError) as unavailable:
        _gateway_get(release_gateway, accept="text/html")
    assert unavailable.value.code == 503
    with _gateway_get(release_gateway, "/goals") as response:
        assert response.status == 200


def test_release_gateway_requires_authentication(release_gateway: str) -> None:
    with pytest.raises(HTTPError) as denied:
        HTTP_CLIENT.open(release_gateway + "/api/health", timeout=5)
    assert denied.value.code == 401


def test_release_gateway_does_not_expose_internal_shutdown(release_gateway: str) -> None:
    request = Request(
        release_gateway + "/internal/shutdown",
        method="POST",
        headers={"Authorization": AUTHORIZATION},
    )
    with pytest.raises(HTTPError) as denied:
        HTTP_CLIENT.open(request, timeout=5)
    assert denied.value.code == 404
