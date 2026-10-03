"""以实际TLS网关核对生产包、全部API路由及本地视觉资源。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

import httpx

ROOT = Path(__file__).resolve().parents[2]


def api_paths() -> list[str]:
    """从现役入口提取真实路由，避免手写清单遗漏新增API。"""
    found = set()
    for node in ast.walk(ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.func.attr
                    in {"get", "post", "put", "patch", "delete", "head", "options"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    path = decorator.args[0].value
                    if isinstance(path, str) and path != "/" and not path.startswith("/internal/"):
                        found.add(re.sub(r"\{[^}]+\}", "preflight-missing-record", path))
    return sorted(found)


def main() -> int:
    """只启动自有服务并使用独立合成匿名数据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddy", required=True, type=Path)
    parser.add_argument("--web-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--api-port", type=int, default=8034)
    parser.add_argument("--web-port", type=int, default=5202)
    parser.add_argument("--visual-checks", action="store_true")
    parser.add_argument("--review-checks", action="store_true")
    parser.add_argument("--workspace-checks", action="store_true")
    parser.add_argument("--layout-checks", action="store_true")
    parser.add_argument("--fixture-port", type=int, default=8036)
    args = parser.parse_args()
    out, web = args.out.resolve(), args.web_root.resolve()
    working = (ROOT / "_working").resolve()
    if out.exists() or not out.is_relative_to(working) or not web.is_relative_to(working):
        raise ValueError("使用已验收的隔离前端和尚不存在的新证据目录")
    caddy = args.caddy.resolve()
    node = shutil.which("node")
    curl = shutil.which("curl")
    if not caddy.is_file() or node is None or not (web / "dist/.vite/manifest.json").is_file():
        raise ValueError("需要可信Caddy、Node及完整生产构建")
    if curl is None:
        raise ValueError("需要curl验证Expect: 100-continue超限拒绝")
    fingerprint_paths = [
        ROOT / "server.py",
        ROOT / "deploy/Caddyfile",
        Path(__file__),
        ROOT / "scripts/acceptance/gateway_production.mjs",
        ROOT / "scripts/acceptance/interview_vision_production.mjs",
        web / "package.json",
        web / "package-lock.json",
        web / "dist/.vite/manifest.json",
    ]
    if args.visual_checks:
        fingerprint_paths.append(ROOT / "scripts/acceptance/visual_upgrade.mjs")
    if args.review_checks:
        fingerprint_paths.append(ROOT / "scripts/acceptance/file_review.mjs")
    if args.review_checks or args.workspace_checks or args.layout_checks:
        fingerprint_paths.append(ROOT / "scripts/acceptance/workspace_model_fixture.py")
    if args.workspace_checks:
        fingerprint_paths.append(ROOT / "scripts/acceptance/workspace.mjs")
    if args.layout_checks:
        fingerprint_paths.append(ROOT / "scripts/acceptance/knowledge_layout.mjs")
    fingerprints = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fingerprint_paths
    }
    ports = [args.api_port, args.web_port] + ([args.fixture_port] if args.review_checks or args.workspace_checks or args.layout_checks else [])
    if len(set(ports)) != len(ports):
        raise ValueError("验收服务端口必须各不相同")
    for port in ports:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    out.mkdir(parents=True)
    runtime = out / "runtime"
    runtime.mkdir()
    temporary = out / "tmp"
    temporary.mkdir()
    base = f"https://127.0.0.1:{args.web_port}"
    api = f"http://127.0.0.1:{args.api_port}"
    password = "synthetic-" + secrets.token_urlsafe(24)
    hashed = subprocess.run(
        [str(caddy), "hash-password", "--plaintext", password],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    env = os.environ.copy()
    env.update(
        PYTHONUTF8="1",
        PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
        FILEMATE_DOMAIN=base,
        FILEMATE_BASIC_USER="synthetic",
        FILEMATE_BASIC_PASSWORD_HASH=hashed,
        FILEMATE_ACCEPTANCE_BASIC_USER="synthetic",
        FILEMATE_ACCEPTANCE_BASIC_PASSWORD=password,
        FILEMATE_ENV="production",
        FILEMATE_HOST="0.0.0.0",
        FILEMATE_ALLOWED_HOSTS="localhost,127.0.0.1",
        FILEMATE_CORS_ORIGINS=base,
        FILEMATE_IDENTITY_MODE="anonymous",
        FILEMATE_IDENTITY_SECRET="",
        FILEMATE_INTERVIEW_LOCAL_ONLY="1",
        FILEMATE_DATA_DIR=str(runtime),
        FILEMATE_DB_PATH=str(runtime / "filemate.db"),
        FILEMATE_UPLOAD_DIR=str(runtime / "inbox"),
        FILEMATE_ARCHIVE_DIR=str(runtime / "archive"),
        LLM_API_KEY="",
        FILEMATE_WEB_URL=base,
        FILEMATE_API_URL=base,
        FILEMATE_PRODUCTION_GATEWAY="1",
        FILEMATE_ACCEPTANCE_INSECURE_TLS="1",
        FILEMATE_FACE_FIXTURE=str(ROOT / "_working/v2-4-20261001/astronaut.png"),
        TEMP=str(temporary),
        TMP=str(temporary),
    )
    if args.review_checks or args.workspace_checks or args.layout_checks:
        fixture_base = f"http://127.0.0.1:{args.fixture_port}"
        fixture_token = "synthetic-" + secrets.token_urlsafe(24)
    source = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8")
    config = source.replace(
        "admin off",
        f'admin off\n\tpersist_config off\n\tskip_install_trust\n\tauto_https disable_redirects\n\tstorage file_system {{\n\t\troot "{(out / "tls-storage").as_posix()}"\n\t}}',
    )
    config = config.replace("{$FILEMATE_DOMAIN} {", "{$FILEMATE_DOMAIN} {\n\tbind 127.0.0.1")
    config = config.replace("api:8001", f"127.0.0.1:{args.api_port}").replace(
        "root * /srv", f'root * "{(web / "dist").as_posix()}"'
    )
    config_file = out / "Caddyfile"
    config_file.write_text(config, encoding="utf-8")
    results, routes, assets = [], [], []
    capacity = None
    processes, logs = [], []

    def check(name: str, passed: bool) -> None:
        results.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    def command(name: str, arguments: list[str], timeout: int = 120) -> None:
        with (out / (name + ".log")).open("w", encoding="utf-8") as output:
            completed = subprocess.run(
                arguments,
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
            )
        check(name, completed.returncode == 0)

    def stop(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def start(name: str, arguments: list[str], url: str, secure: bool = False) -> subprocess.Popen:
        output = (out / (name + ".log")).open("w", encoding="utf-8")
        logs.append(output)
        process = subprocess.Popen(
            arguments, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT
        )
        processes.append(process)
        deadline = time.monotonic() + 45
        with httpx.Client(
            verify=not secure, auth=("synthetic", password), timeout=2, trust_env=False
        ) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("自有验收服务提前退出")
                try:
                    if client.get(url).status_code == 200:
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise TimeoutError("自有验收服务未就绪")

    try:
        command(
            "credential-isolation",
            [sys.executable, "-c", "import os; from filemate.llm_client.credential_store import resolve_api_key; key, origin = resolve_api_key(); assert key == os.environ['LLM_API_KEY']; assert origin == ('environment' if key else 'none')"],
        )
        command(
            "bundle-budget",
            [node, str(web / "scripts/check-bundle.mjs"), "--dist", str(web / "dist")],
        )
        command(
            "caddy-validate",
            [str(caddy), "validate", "--config", str(config_file), "--adapter", "caddyfile"],
        )
        api_process = start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            api + "/api/health",
        )
        start(
            "gateway",
            [str(caddy), "run", "--config", str(config_file), "--adapter", "caddyfile"],
            base + "/api/health",
            True,
        )
        with httpx.Client(
            base_url=base, verify=False, timeout=25, auth=("synthetic", password), trust_env=False
        ) as client:
            for path in api_paths():
                response = client.get(
                    path,
                    headers={
                        "Accept": (
                            "text/html"
                            if path
                            not in {"/knowledge", "/wrongbook", "/interview", "/goals", "/trust"}
                            else "application/json"
                        )
                    },
                )
                with httpx.Client(base_url=api, trust_env=False, timeout=25) as upstream:
                    direct = upstream.get(
                        path,
                        headers={
                            "Accept": response.request.headers["Accept"],
                            "Cookie": response.request.headers.get("Cookie", ""),
                        },
                    )
                media_type = response.headers.get("content-type", "").split(";", 1)[0]
                upstream_type = direct.headers.get("content-type", "").split(";", 1)[0]
                routes.append(
                    {
                        "path": path,
                        "status": response.status_code,
                        "media_type": media_type,
                        "upstream_status": direct.status_code,
                        "upstream_media_type": upstream_type,
                        "upstream_matches": media_type == upstream_type
                        and response.status_code == direct.status_code,
                    }
                )
            check(
                "all current API paths match actual upstream status and media type",
                all(row["upstream_matches"] for row in routes),
            )
            for path in (
                "/knowledge",
                "/wrongbook",
                "/interview",
                "/goals",
                "/trust",
                "/programming",
                "/career",
            ):
                response = client.get(path, headers={"Accept": "text/html"})
                check(
                    "HTML navigation " + path,
                    response.status_code == 200
                    and "text/html" in response.headers.get("content-type", ""),
                )
            for path in ("/internal/shutdown", "/internal/metrics", "/docs", "/openapi.json"):
                response = client.get(path)
                check("private endpoint blocked " + path, response.status_code == 404)
            health = client.get("/api/health")
            check(
                "gateway and candidate API version agree",
                health.json()["data"]["version"]
                == json.loads((web / "package.json").read_text())["version"],
            )
            home = client.get("/")
            check(
                "security headers and WASM CSP",
                home.headers.get("strict-transport-security") is not None
                and home.headers.get("x-content-type-options") == "nosniff"
                and home.headers.get("x-frame-options") == "DENY"
                and "'wasm-unsafe-eval'" in home.headers.get("content-security-policy", ""),
            )
            check(
                "HTML cannot cache an obsolete release",
                home.headers.get("cache-control") == "no-store",
            )
            for file in sorted((web / "dist/interview-vision").rglob("*")):
                if file.is_file():
                    path = "/" + file.relative_to(web / "dist").as_posix()
                    response = client.get(path)
                    passed = (
                        response.status_code == 200
                        and hashlib.sha256(response.content).digest()
                        == hashlib.sha256(file.read_bytes()).digest()
                    )
                    assets.append(
                        {
                            "path": path,
                            "status": response.status_code,
                            "bytes": len(response.content),
                            "exact": passed,
                        }
                    )
                    if file.suffix == ".wasm":
                        passed = passed and response.headers.get("content-type", "").startswith(
                            "application/wasm"
                        )
                    check(
                        "exact local vision asset " + path,
                        passed and response.headers.get("cache-control") == "no-cache",
                    )
            asset_path = re.search(r'(?:src|href)="(/assets/[^\"]+\.js)"', home.text)[1]
            check(
                "hashed assets cache immutably",
                "immutable" in client.get(asset_path).headers.get("cache-control", ""),
            )
            upload = client.post(
                "/knowledge/import",
                files={
                    "file": (
                        "synthetic.txt",
                        "原创合成网关资料：二分查找缩小区间。".encode(),
                        "text/plain",
                    )
                },
            )
            check(
                "real HTTPS anonymous import persists",
                upload.status_code == 200 and upload.json()["success"] is True,
            )
            source_id = upload.json()["data"]["source_id"]
            check(
                "original secure cookie reads imported source",
                client.get("/knowledge/sources/" + source_id).status_code == 200,
            )
            before = len(client.get("/knowledge/sources").json()["data"])
            oversized = client.post(
                "/knowledge/import",
                files={
                    "file": (
                        "synthetic-oversize.txt",
                        b"x" * (26 * 1024 * 1024),
                        "text/plain",
                    )
                },
            )
            check("25MiB file limit returns 413 through gateway", oversized.status_code == 413)
            check(
                "rejected oversized import creates no source",
                len(client.get("/knowledge/sources").json()["data"]) == before,
            )
            # 超大请求应在传输正文前拒绝；Expect避免客户端仍在写正文时被关闭连接。
            body_fixture = temporary / "synthetic-gateway-limit.txt"
            body_fixture.write_bytes(b"x" * (33 * 1024 * 1024))
            body_result = out / "gateway-body-limit.json"
            rejected = subprocess.run(
                [
                    curl,
                    "--silent",
                    "--show-error",
                    "--insecure",
                    "--noproxy",
                    "*",
                    "--max-time",
                    "30",
                    "--user",
                    "synthetic:" + password,
                    "--header",
                    "Expect: 100-continue",
                    "--form",
                    "file=@" + str(body_fixture),
                    "--output",
                    str(body_result),
                    "--write-out",
                    "%{http_code}",
                    base + "/knowledge/import",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=40,
                check=False,
            )
            check(
                "32MiB declared gateway body returns explicit 413 before upload",
                rejected.returncode == 0
                and rejected.stdout.strip() == "413"
                and json.loads(body_result.read_text(encoding="utf-8"))["success"] is False,
            )
            check(
                "gateway rejection creates no source",
                len(client.get("/knowledge/sources").json()["data"]) == before,
            )
            chunk_result = out / "gateway-chunked-limit.txt"
            chunked = subprocess.run(
                [
                    curl,
                    "--silent",
                    "--show-error",
                    "--insecure",
                    "--noproxy",
                    "*",
                    "--http1.1",
                    "--max-time",
                    "30",
                    "--user",
                    "synthetic:" + password,
                    "--header",
                    "Expect: 100-continue",
                    "--header",
                    "Transfer-Encoding: chunked",
                    "--form",
                    "file=@" + str(body_fixture),
                    "--output",
                    str(chunk_result),
                    "--write-out",
                    "%{http_code}",
                    base + "/knowledge/import",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=40,
                check=False,
            )
            (out / "chunked-transport.json").write_text(
                json.dumps(
                    {
                        "exit": chunked.returncode,
                        "http_status": chunked.stdout.strip(),
                        "stderr": chunked.stderr.strip(),
                        "synthetic_body_bytes": body_fixture.stat().st_size,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            check(
                "chunked oversized body returns 413",
                chunked.returncode == 0 and chunked.stdout.strip() == "413",
            )
            check(
                "chunked rejection creates no source",
                len(client.get("/knowledge/sources").json()["data"]) == before,
            )
            check("health survives oversized bodies", client.get("/api/health").status_code == 200)
            with httpx.Client(
                base_url=base, verify=False, auth=("synthetic", password), trust_env=False
            ) as second:
                check(
                    "second HTTPS visitor cannot access source",
                    second.get("/knowledge/sources/" + source_id).status_code == 404,
                )
            # 未认证请求不进入API，避免创建匿名工作区。
            with httpx.Client(verify=False, trust_env=False) as unauthenticated:
                check(
                    "private preview requires authentication",
                    unauthenticated.get(base + "/").status_code == 401,
                )
        endpoints = [
            "/api/health",
            "/knowledge/sources",
            "/analytics/overview",
            "/api/career/status",
        ]

        def visitor(_number: int) -> list[dict]:
            records = []
            with httpx.Client(
                base_url=base,
                verify=False,
                timeout=15,
                trust_env=False,
                auth=("synthetic", password),
            ) as client:
                client.get("/api/health").raise_for_status()
                for index in range(16):
                    endpoint = endpoints[index % len(endpoints)]
                    started = time.perf_counter()
                    response = client.get(endpoint)
                    records.append(
                        {
                            "endpoint": endpoint,
                            "status": response.status_code,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                            "healthy": response.status_code == 200
                            and response.json().get("success") is True,
                        }
                    )
            return records

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as executor:
            records = [
                record
                for visitor_records in executor.map(visitor, range(8))
                for record in visitor_records
            ]
        wall = time.perf_counter() - started
        timings = sorted(record["elapsed_ms"] for record in records)
        capacity = {
            "visitors": 8,
            "requests": len(records),
            "healthy": sum(record["healthy"] for record in records),
            "wall_seconds": round(wall, 3),
            "requests_per_second": round(len(records) / wall, 2),
            "latency_ms": {
                "p50": median(timings),
                "p95_nearest_rank": timings[(95 * len(timings) + 99) // 100 - 1],
                "max": max(timings),
            },
            "p95_budget_ms": 5000,
            "records": records,
            "scope": "8 independent synthetic anonymous visitors, loopback TLS, read APIs; development hardware, excludes model generation, uploads and compilation; not production capacity or SLA",
        }
        (out / "capacity.json").write_text(
            json.dumps(capacity, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        check(
            "bounded 8-visitor 128-request API workload stays healthy",
            capacity["healthy"] == 128
            and capacity["latency_ms"]["p95_nearest_rank"] <= capacity["p95_budget_ms"],
        )
        browser_cases = ["gateway_production", "interview_vision_production"]
        if args.visual_checks:
            browser_cases.append("visual_upgrade")
        if args.review_checks:
            browser_cases.append("file_review")
        if args.workspace_checks:
            browser_cases.append("workspace")
        if args.layout_checks:
            browser_cases.append("knowledge_layout")
        fixture_started = False
        for name in browser_cases:
            if name in {"file_review", "workspace", "knowledge_layout"} and not fixture_started:
                # 现役/process必须初始化模型；写入专项使用明确合成合同，不读取真实凭据。
                stop(api_process)
                env.update(
                    LLM_API_KEY=fixture_token,
                    LLM_BASE_URL=fixture_base + "/v1",
                    LLM_PROVIDER="openai_compatible",
                    LLM_MODEL="synthetic-ui-fixture",
                    FILEMATE_UI_FIXTURE_BASE=fixture_base,
                    FILEMATE_UI_FIXTURE_TOKEN=fixture_token,
                    NO_PROXY="127.0.0.1,localhost",
                )
                command("fixture-credential-isolation", [sys.executable, "-c", "import os; from filemate.llm_client.credential_store import resolve_api_key; key, origin = resolve_api_key(); assert key == os.environ['LLM_API_KEY'] and origin == 'environment'"])
                start("workspace-model-fixture", [sys.executable, "scripts/acceptance/workspace_model_fixture.py", "--port", str(args.fixture_port)], fixture_base + "/health")
                start("api-model-fixture", [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(args.api_port)], api + "/api/health")
                fixture_started = True
            if name == "workspace":
                with httpx.Client(base_url=fixture_base, trust_env=False, headers={"Authorization": "Bearer " + fixture_token}) as fixture_client:
                    previous = fixture_client.get("/stats")
                    previous.raise_for_status()
                    (out / "fixture-before-workspace.json").write_text(json.dumps(previous.json(), indent=2), encoding="utf-8")
                    fixture_client.post("/control", json={"reset_calls": True}).raise_for_status()
            folder = out / name
            folder.mkdir()
            env["FILEMATE_EVIDENCE_DIR"] = str(folder)
            command(name, [node, f"scripts/acceptance/{name}.mjs"], 180)
    except (
        AssertionError,
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        httpx.HTTPError,
        subprocess.SubprocessError,
        TimeoutError,
    ) as error:
        results.append({"name": "runner", "passed": False, "error_type": type(error).__name__})
    finally:
        for process in reversed(processes):
            stop(process)
        for output in logs:
            output.close()
    report = {
        "passed": all(item["passed"] for item in results),
        "checks": results,
        "api_route_count": len(routes),
        "routes": routes,
        "assets": assets,
        "capacity": (
            {key: value for key, value in capacity.items() if key != "records"}
            if capacity
            else None
        ),
        "source_caddy_sha256": hashlib.sha256((ROOT / "deploy/Caddyfile").read_bytes()).hexdigest(),
        "fingerprints_before": fingerprints,
        "sources_unchanged": all(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
            for name, digest in fingerprints.items()
        ),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "caddy": subprocess.run(
                [str(caddy), "version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout.strip(),
        },
        "scope": "actual TLS Caddy, FastAPI production anonymous mode and compiled Vue; local synthetic test, no API bridge or system trust install; not Docker/live deployment",
    }
    report["passed"] = report["passed"] and report["sources_unchanged"]
    (out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({"passed": report["passed"], "checks": len(results), "api_routes": len(routes)})
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
