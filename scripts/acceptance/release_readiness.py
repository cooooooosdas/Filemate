"""只读汇集 RC 工程证据和待人工完成项，不发布或修改版本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.analyze_study import analyze_user_study
from evaluation.calibrate_interview import DIMENSIONS, calibrate
from filemate import __version__
from filemate.execution.storage import _MIGRATIONS

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {".py", ".vue", ".ts", ".mjs", ".ps1", ".toml", ".json", ".yml", ".yaml", ".csv"}


def snapshot(root: Path = ROOT) -> dict[str, Any]:
    """记录代码、配置和评测合同指纹，避开密钥、数据库和运行资料。"""
    inventory = (
        subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if (root / ".git").exists()
        else None
    )
    if inventory is not None and inventory.returncode == 0:
        paths = [
            root / name
            for name in inventory.stdout.decode("utf-8").split("\0")
            if name
            and (
                name.split("/")[0] in {"filemate", "evaluation", "scripts", ".github"}
                or name in {"server.py", "main.py", "pyproject.toml", "uv.lock"}
            )
        ]
    else:
        paths = [
            path
            for folder in ("filemate", "evaluation", "scripts", ".github")
            if (root / folder).exists()
            for path in (root / folder).rglob("*")
        ]
    resources = []
    for path in sorted(set(paths)):
        if not path.is_file() or (path.suffix not in EXTENSIONS and path.name != "uv.lock"):
            continue
        if any(
            part
            in {
                "node_modules",
                "dist",
                "target",
                "__pycache__",
                "data",
                "archive",
                "raw",
                "_working",
            }
            for part in path.relative_to(root).parts
        ):
            continue
        resources.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    fingerprint = hashlib.sha256(json.dumps(resources, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": fingerprint,
        "resource_count": len(resources),
        "resources": resources,
        "scope": "source/config/tests/evaluation contracts; excludes secrets, databases, raw inputs and Markdown",
    }


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _reference(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def readiness(
    baseline: Path,
    gate: Path,
    browser: Path,
    synthetic: Path,
    study: Path | None = None,
    expert: Path | None = None,
) -> dict[str, Any]:
    """分开报告已验证工程状态、真实研究门槛和待人工冻结事项。"""
    baseline_data, current = _json(baseline), snapshot()
    source_matches = baseline_data.get("source_fingerprint") == current["source_fingerprint"]
    log = gate.read_text(encoding="utf-8-sig", errors="replace")
    backend = re.search(r"(\d+) passed, (\d+) skipped, (\d+) deselected", log)
    frontend = re.search(r"(?:Tests\s+(\d+) passed|pass (\d+))", log)
    frontend_count = int(frontend[1] or frontend[2]) if frontend else None
    gate_ok = bool(
        backend
        and frontend_count
        and "fail 0" in log
        and "All checks passed!" in log
        and "built in" in log
        and not re.search(r"\d+ failed|failed with exit code", log)
    )
    browser_data = _json(browser)
    cases = browser_data.get("cases", [])
    browser_ok = (
        bool(cases)
        and browser_data.get("passed") is True
        and all(row.get("passed") is True and row.get("exit_code") == 0 for row in cases)
    )
    synthetic_data = _json(synthetic)
    checks = synthetic_data.get("checks", [])
    synthetic_ok = (
        bool(checks)
        and synthetic_data.get("sample_kind") == "synthetic"
        and synthetic_data.get("status") == "passed"
        and all(row.get("passed") is True for row in checks)
    )
    engineering_ok = source_matches and gate_ok and browser_ok and synthetic_ok
    study_report = analyze_user_study(study, "real") if study else None
    expert_report = calibrate(expert) if expert else None
    real_rows = study_report["participant_count"] if study_report else 0
    real_disciplines = study_report["discipline_count"] if study_report else 0
    actual_comparisons = (
        [row for row in expert_report["comparisons"] if row["sample_kind"] == "expert_real"]
        if expert_report
        else []
    )
    calibrated = {
        row["dimension"]
        for row in actual_comparisons
        if row["paired_count"] >= 5 and row["spearman"] is not None
    }
    human_pending = [
        "团队核实招募、知情同意、课程资料授权及研究结论使用范围",
        "按协议完成100份授权资料、300次引用标注与各组对照审查",
        "提交并冻结版本、对当前提交运行远端CI、核对发布说明",
        "网站与本地版本同步后验收，再由团队确认发布",
    ]
    blockers = []
    if not engineering_ok:
        blockers.append("当前代码指纹或工程门禁证据未通过")
    if not study_report or study_report["status"] != "real_sample_ready_for_review":
        blockers.append("正式研究待采集：30名、3专业，平行对照每条件15名")
    if calibrated != DIMENSIONS:
        blockers.append("实际导师配对评分待校准：逐维度至少5对且可计算相关")
    blockers.extend(human_pending)
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_team_release_review",
        "engineering_status": "passed" if engineering_ok else "pending_or_failed",
        "version": __version__,
        "schema_version": max(row[0] for row in _MIGRATIONS),
        "git_head": git_head,
        "uncommitted_changes": dirty,
        "source_fingerprint": current["source_fingerprint"],
        "source_matches_verified_baseline": source_matches,
        "gate": {
            "passed": gate_ok,
            "backend_passed": int(backend[1]) if backend else None,
            "skipped": int(backend[2]) if backend else None,
            "deselected": int(backend[3]) if backend else None,
            "frontend_passed": frontend_count,
        },
        "browser": {
            "passed": browser_ok,
            "cases": [row["name"] for row in cases],
            "scope": "本次指定场景；历史全量浏览器和原生结果见总验收，不冒充当前提交全量覆盖",
        },
        "synthetic_model": {
            "passed": synthetic_ok,
            "checks": len(checks),
            "model_calls": synthetic_data.get("model_calls"),
            "sample_kind": "synthetic",
        },
        "real_study": {
            "participant_count": real_rows,
            "discipline_count": real_disciplines,
            "beta_10_sample_threshold": real_rows >= 10,
            "formal_30_sample_threshold": bool(
                study_report and study_report["status"] == "real_sample_ready_for_review"
            ),
            "report": study_report,
        },
        "expert_calibration": {
            "real_expert_pairs": expert_report["real_expert_pairs"] if expert_report else 0,
            "calibrated_dimensions": sorted(calibrated),
        },
        "blockers": blockers,
        "human_review": "pending; 本工具只准备验收证据，不能自动批准研究结论或正式发布",
        "evidence": {
            "baseline": _reference(baseline),
            "gate": _reference(gate),
            "browser": _reference(browser),
            "synthetic": _reference(synthetic),
            "study": _reference(study) if study else None,
            "expert": _reference(expert) if expert else None,
        },
    }


def main() -> int:
    """保存新证据文件；require-ready 对尚未人工冻结的 RC 返回非零。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-baseline", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--gate-log", type=Path)
    parser.add_argument("--browser-summary", type=Path)
    parser.add_argument("--synthetic-report", type=Path)
    parser.add_argument("--study", type=Path)
    parser.add_argument("--expert", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    if args.capture_baseline:
        path, report = args.capture_baseline, snapshot()
    else:
        if not all(
            (args.baseline, args.gate_log, args.browser_summary, args.synthetic_report, args.output)
        ):
            parser.error(
                "需指定 baseline、gate-log、browser-summary、synthetic-report 和新 output 文件"
            )
        path = args.output
        report = readiness(
            args.baseline,
            args.gate_log,
            args.browser_summary,
            args.synthetic_report,
            args.study,
            args.expert,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in ("status", "engineering_status", "source_fingerprint")
            },
            ensure_ascii=False,
        )
    )
    return 1 if args.require_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
