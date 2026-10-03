"""在独立数据库与自有进程中复跑五大模块的浏览器验收。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def available(port: int) -> None:
    """拒绝占用已有服务端口。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def wait_ready(url: str, process: subprocess.Popen, timeout: int = 60) -> None:
    """等待自己启动的服务就绪，启动失败立即报告。"""
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"服务退出：{process.returncode}")
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
    raise TimeoutError(f"服务未就绪：{url}")


def stop(process: subprocess.Popen) -> None:
    """只停止本脚本创建并持有的进程。"""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> int:
    """顺序复跑写入场景，每个脚本使用新数据库并保留证据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--api-port", type=int, default=8028)
    parser.add_argument("--web-port", type=int, default=5198)
    parser.add_argument("--cases", nargs="*")
    args = parser.parse_args()
    out, web_root = args.out.resolve(), args.web_root.resolve()
    if not out.is_relative_to(ROOT / "_working") or out.exists():
        raise ValueError("输出须为项目 _working 下尚未存在的新目录，避免覆盖旧证据")
    if not web_root.is_relative_to(ROOT / "_working"):
        raise ValueError("使用已通过门禁的隔离前端副本")
    vite = web_root / "node_modules/vite/bin/vite.js"
    python = ROOT / ".venv/Scripts/python.exe"
    node = shutil.which("node")
    if not python.is_file() or not vite.is_file() or node is None:
        raise ValueError("需要已有 Python、Node、Playwright 与通过门禁的前端")
    available(args.api_port)
    available(args.web_port)
    out.mkdir(parents=True)
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://127.0.0.1:{args.web_port}"
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", FILEMATE_IDENTITY_MODE="local",
               FILEMATE_INTERVIEW_LOCAL_ONLY="1", FILEMATE_API_URL=api,
               VITE_API_URL=api, FILEMATE_WEB_URL=web, FILEMATE_DISABLED_WEB_URL=web,
               FILEMATE_DISABLED_API_URL=api, FILEMATE_CORS_ORIGINS=web,
               FILEMATE_FACE_FIXTURE=str(ROOT / "_working/v2-4-20261001/astronaut.png"))
    results = []
    cases = ["browser_smoke", "digital_human", "knowledge_graph", "programming", "interview_review",
             "career", "career_state", "career_growth", "career_planning",
             "career_production", "career_planning_production", "interview_vision_production",
             "digital_human_disabled", "knowledge_graph_disabled", "programming_disabled", "interview_review_disabled", "career_disabled"]
    if args.cases:
        if not set(args.cases) <= {*cases, "evidence_profile", "frontend_production"}:
            raise ValueError("未知验收脚本")
        cases = args.cases
    for name in cases:
        print(f"RUN {name}", flush=True)
        folder = out / name
        folder.mkdir()
        runtime = folder / "runtime"
        runtime.mkdir()
        current = env.copy()
        current.update(FILEMATE_DATA_DIR=str(runtime), FILEMATE_DB_PATH=str(runtime / "acceptance.db"),
                       FILEMATE_ACCEPTANCE_DB=str(runtime / "acceptance.db"),
                       FILEMATE_UPLOAD_DIR=str(runtime / "inbox"), FILEMATE_ARCHIVE_DIR=str(runtime / "archive"),
                       FILEMATE_EVIDENCE_DIR=str(folder), FILEMATE_ENV="development")
        # 独立关闭一个模块，其他模块保留默认状态。
        for key in ["DIGITAL_HUMAN", "KNOWLEDGE_GRAPH", "PROGRAMMING", "INTERVIEW_REVIEW", "CAREER"]:
            current[f"FILEMATE_ENABLE_{key}"] = "1"
            current[f"VITE_ENABLE_{key}"] = "true"
        if name.endswith("_disabled"):
            flag = name.removesuffix("_disabled").upper()
            current[f"FILEMATE_ENABLE_{flag}"] = "0"
            current[f"VITE_ENABLE_{flag}"] = "false"
        production = name.endswith("_production") or name == "career_production"
        script = "career_planning" if name == "career_planning_production" else name
        if production:
            current["FILEMATE_PRODUCTION_PROXY"] = "1"
        api_process = web_process = None
        started = time.monotonic()
        try:
            if name == "digital_human":
                subprocess.run([str(python), "scripts/acceptance/seed_digital_human.py", "--db", current["FILEMATE_DB_PATH"]],
                               cwd=ROOT, env=current, check=True, capture_output=True)
            with (folder / "api.log").open("w", encoding="utf-8") as api_log, (folder / "web.log").open("w", encoding="utf-8") as web_log:
                api_process = subprocess.Popen([str(python), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
                                               cwd=ROOT, env=current, stdout=api_log, stderr=subprocess.STDOUT)
                wait_ready(api + "/api/health", api_process)
                command = [node, str(vite)] + (["preview"] if production else [])
                web_process = subprocess.Popen(command + ["--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"],
                                               cwd=web_root, env=current, stdout=web_log, stderr=subprocess.STDOUT)
                wait_ready(web, web_process)
                with (folder / "run.log").open("w", encoding="utf-8") as run_log:
                    completed = subprocess.run([node, f"scripts/acceptance/{script}.mjs"], cwd=ROOT, env=current,
                                               stdout=run_log, stderr=subprocess.STDOUT, timeout=720, check=False)
                results.append({"name": name, "passed": completed.returncode == 0, "exit_code": completed.returncode,
                                "elapsed_seconds": round(time.monotonic() - started, 2), "evidence": str(folder.relative_to(ROOT))})
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            results.append({"name": name, "passed": False, "error": f"{type(error).__name__}: {error}"})
        finally:
            if web_process is not None:
                stop(web_process)
            if api_process is not None:
                stop(api_process)
        (out / "summary.json").write_text(json.dumps({"cases": results, "passed": all(row["passed"] for row in results)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{'PASS' if results[-1]['passed'] else 'FAIL'} {name}", flush=True)
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
