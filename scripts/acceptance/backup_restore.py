"""用合成匿名访客和实际HTTP服务演练完整快照及恢复。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """只操作新建的_working目录和自己启动的进程。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8032)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / "_working").resolve()) or out.exists():
        raise ValueError("输出必须为项目_working下尚未存在的新目录")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    python = shutil.which("python")
    if python is None:
        raise ValueError("需要项目Python运行时")
    out.mkdir(parents=True)
    runtime = out / "runtime"
    runtime.mkdir()
    base = f"http://127.0.0.1:{args.port}"
    env = os.environ.copy()
    env.update(
        PYTHONUTF8="1",
        FILEMATE_ENV="development",
        FILEMATE_IDENTITY_MODE="anonymous",
        FILEMATE_IDENTITY_SECRET="",
        FILEMATE_DATA_DIR=str(runtime),
        FILEMATE_DB_PATH=str(runtime / "filemate.db"),
        FILEMATE_UPLOAD_DIR=str(runtime / "inbox"),
        FILEMATE_ARCHIVE_DIR=str(runtime / "archive"),
        FILEMATE_INTERVIEW_LOCAL_ONLY="1",
    )
    process = None
    log = None
    results = []

    def check(name: str, passed: bool) -> None:
        results.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    def start(name: str) -> None:
        nonlocal process, log
        log = (out / (name + ".log")).open("w", encoding="utf-8")
        process = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("自有测试API提前退出")
            try:
                if httpx.get(base + "/api/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise TimeoutError("测试API未就绪")

    def stop() -> None:
        nonlocal process, log
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if log is not None:
            log.close()
        process, log = None, None

    def cli(name: str, *arguments: str, expected: int = 0) -> dict[str, Any]:
        completed = subprocess.run(
            [python, "-m", "filemate.operations.backup", *arguments],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False,
        )
        (out / (name + ".json")).write_text(completed.stdout, encoding="utf-8")
        check(name, completed.returncode == expected)
        return json.loads(completed.stdout)

    try:
        start("api-before")
        with (
            httpx.Client(base_url=base, timeout=15) as first,
            httpx.Client(base_url=base, timeout=15) as second,
        ):
            sources, contexts = [], []
            for index, client in enumerate((first, second)):
                text = f"原创合成运维资料{index}：有序数组的二分查找每轮缩小搜索区间。"
                response = client.post(
                    "/knowledge/import",
                    files={"file": (f"synthetic-{index}.txt", text.encode(), "text/plain")},
                )
                response.raise_for_status()
                source = response.json()["data"]
                sources.append(source)
                context = client.post(f"/knowledge/sources/{source['source_id']}/contexts")
                context.raise_for_status()
                contexts.append(context.json()["data"])
            check(
                "two real anonymous imports and contexts", len(sources) == 2 and len(contexts) == 2
            )
            check(
                "anonymous isolation before snapshot",
                first.get(f"/knowledge/sources/{sources[1]['source_id']}").status_code == 404,
            )
            stop()
            plan = cli("backup-plan", "plan", "--data-dir", str(runtime))
            snapshot = out / "snapshot"
            cli(
                "quiescence-required",
                "create",
                "--data-dir",
                str(runtime),
                "--out",
                str(snapshot),
                "--confirm",
                plan["confirmation"],
                expected=1,
            )
            check("refusal did not create output", not snapshot.exists())
            created = cli(
                "backup-create",
                "create",
                "--data-dir",
                str(runtime),
                "--out",
                str(snapshot),
                "--confirm",
                plan["confirmation"],
                "--quiesced",
            )
            check("root and both anonymous databases retained", created["database_count"] == 3)
            cli("backup-verify", "verify", "--backup", str(snapshot))
            cli(
                "backup-repeat-rejected",
                "create",
                "--data-dir",
                str(runtime),
                "--out",
                str(snapshot),
                "--confirm",
                plan["confirmation"],
                "--quiesced",
                expected=1,
            )
            staged = out / "staged"
            restore = cli(
                "restore-plan", "restore-plan", "--backup", str(snapshot), "--target", str(staged)
            )
            check("restore preview did not write", not staged.exists())
            cli(
                "restore-create",
                "restore",
                "--backup",
                str(snapshot),
                "--target",
                str(staged),
                "--confirm",
                restore["confirmation"],
            )
            cli(
                "restore-repeat-rejected",
                "restore",
                "--backup",
                str(snapshot),
                "--target",
                str(staged),
                "--confirm",
                restore["confirmation"],
                expected=1,
            )
            preserved = out / "original-runtime-preserved"
            for path in (runtime, staged, preserved):
                if not path.resolve().is_relative_to(out) or not out.is_relative_to(
                    (ROOT / "_working").resolve()
                ):
                    raise ValueError("自有恢复演练路径越界")
            if preserved.exists():
                raise ValueError("原目录保留目标已存在")
            runtime.rename(preserved)
            staged.rename(runtime)
            start("api-restored")
            for index, client in enumerate((first, second)):
                response = client.get(f"/knowledge/sources/{sources[index]['source_id']}")
                response.raise_for_status()
                context = client.get(f"/ai/contexts/{contexts[index]['ctx_id']}")
                context.raise_for_status()
                check(
                    f"visitor {index} original cookie source and context survive restart",
                    response.json()["data"]["raw_text"] == sources[index]["raw_text"]
                    and context.json()["data"]["ctx_id"] == contexts[index]["ctx_id"],
                )
            check(
                "anonymous isolation after restoration",
                first.get(f"/knowledge/sources/{sources[1]['source_id']}").status_code == 404,
            )
            stop()
            check("original synthetic data retained for rollback", preserved.is_dir())
            copied = out / "corrupted-snapshot"
            shutil.copytree(snapshot, copied)
            attachment = next((copied / "data/users").rglob("*.txt"))
            attachment.write_bytes(b"explicit synthetic corruption")
            cli(
                "corruption-rejected",
                "restore-plan",
                "--backup",
                str(copied),
                "--target",
                str(out / "must-not-exist"),
                expected=1,
            )
            check("corruption refusal did not write", not (out / "must-not-exist").exists())
    except (
        AssertionError,
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        httpx.HTTPError,
        subprocess.SubprocessError,
        TimeoutError,
    ) as error:
        results.append({"name": "runner", "passed": False, "error_type": type(error).__name__})
    finally:
        stop()
    report = {
        "sample_kind": "synthetic_regression",
        "passed": all(item["passed"] for item in results),
        "checks": results,
        "notice": "实际匿名HTTP及CLI；仅新建合成目录，未操作线上或私人数据，无外部模型调用",
    }
    (out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], "checks": len(results)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
