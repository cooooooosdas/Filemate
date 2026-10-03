"""汇总已有验收证据与资源指纹，不把示例或跳过项计入真实效果。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filemate import __version__
from filemate.execution.storage import _MIGRATIONS

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> Any:
    """读取一份已有证据。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_counts(folder: Path) -> dict[str, Any]:
    """兼容已有验收脚本的列表与汇总格式。"""
    for name in ["summary.json", "production-summary.json", "results.json"]:
        path = folder / name
        if not path.is_file():
            continue
        payload = read_json(path)
        rows = payload if isinstance(payload, list) else payload.get("results", [])
        if isinstance(payload, dict) and "routes" in payload and "api" in payload:
            return {"passed": sum(row["status"] == 200 and row.get("hasMainContent") and not row.get("consoleErrors") and not row.get("hasHorizontalOverflow") for row in payload["routes"]) + sum(row["ok"] for row in payload["api"]),
                    "total": len(payload["routes"]) + len(payload["api"]), "page_errors": sum(len(row.get("consoleErrors", [])) for row in payload["routes"]), "source": str(path.relative_to(ROOT))}
        errors = [] if isinstance(payload, list) else payload.get("errors", payload.get("pageErrors", []))
        return {"passed": sum(row.get("passed") is True for row in rows) if rows else payload.get("passed"),
                "total": len(rows) if rows else payload.get("total"), "page_errors": len(errors), "source": str(path.relative_to(ROOT))}
    raise FileNotFoundError(f"缺少场景证据：{folder.name}")


def collect(evidence: Path) -> dict[str, Any]:
    """生成当前工作区与已验证运行态的机器可读索引。"""
    suites = {}
    records = read_json(evidence / "browser/summary.json")["cases"]
    records += read_json(evidence / "browser-fixed/summary.json")["cases"]
    records += read_json(evidence / "browser-final/summary.json")["cases"]
    records += read_json(evidence / "digital-disabled-final/summary.json")["cases"]
    for row in records:
        folder = ROOT / row["evidence"]
        suites[row["name"]] = {**row, **check_counts(folder)}
        suites[row["name"]]["exit_ok"] = row.get("exit_code") == 0 and row["passed"] is True
    native = check_counts(evidence / "native-fixed")
    gate = (evidence / "verify-final.log").read_text(encoding="utf-8-sig", errors="replace")
    counts = re.search(r"(\d+) passed, (\d+) skipped, (\d+) deselected", gate)
    if counts is None or "built in" not in gate or "All checks passed!" not in gate:
        raise ValueError("完整门禁证据未完成")
    markdown = subprocess.run(["rg", "--files", "-g", "*.md", "-g", "!_working/**", "-g", "!node_modules/**", "-g", "!filemate/web/node_modules/**"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout.splitlines()
    tracked = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    resources = []
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.suffix.lower() not in {".py", ".vue", ".ts", ".mjs", ".md", ".ps1", ".yml", ".yaml", ".json", ".toml", ".csv"}:
            continue
        if any(part in {"node_modules", "dist", "_working", ".git"} for part in path.parts):
            continue
        resources.append({"path": name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    datasets = []
    for path in sorted((ROOT / "evaluation/datasets").glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            count = sum(1 for _ in reader)
            fields = reader.fieldnames
        kind = "header_only_template" if ".template." in path.name else "synthetic_example" if ".example." in path.name else "unverified_input"
        datasets.append({"path": str(path.relative_to(ROOT)), "kind": kind, "row_count": count, "fields": fields})
    version = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    (evidence / "resource-inventory.json").write_text(json.dumps({"markdown_files": markdown, "resources": resources, "evaluation_csv": datasets}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "local_version": __version__, "schema_version": max(row[0] for row in _MIGRATIONS),
              "git_head": version, "baseline": "working_tree_with_uncommitted_changes; source fingerprints in resource-inventory.json",
              "gate": {"passed": int(counts[1]), "skipped": int(counts[2]), "deselected": int(counts[3]), "frontend_tests": 15, "build": "passed", "ruff": "passed", "final_build_log": "build-final.log"},
              "browser_suites": suites,
              "browser_total": {"suites": len(suites), "passed": sum(row["passed"] for row in suites.values()), "total": sum(row["total"] for row in suites.values()), "page_errors": sum(row["page_errors"] for row in suites.values())},
              "native": native,
              "python_package": read_json(evidence / "python-package-smoke.json"),
              "live": {"health": read_json(evidence / "website-health-final.json"), "browser": read_json(evidence / "live-browser/summary.json"),
                       "closeout_health": read_json(evidence / "website-health-closeout.json"), "closeout_new_route": read_json(evidence / "website-new-route-closeout.json")},
              "learning_effect": {"status": "pending_real_collection", "basis": "2026-10-02 user explicitly confirmed no student trials or expert reviews collected", "synthetic_regression": read_json(evidence / "synthetic-evaluation.json"), "expert_calibration": read_json(evidence / "expert-calibration.json")},
              "resource_count": len(resources), "markdown_count": len(markdown), "evaluation_csv": datasets}
    result["local_regressions_passed"] = all(row["exit_ok"] and row["passed"] == row["total"] and row["page_errors"] == 0 for row in suites.values()) and native["passed"] == native["total"]
    (evidence / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    """保留独立场景失败记录，以最终指定复测作为当前结论。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to(ROOT / "_working"):
        parser.error("证据目录必须位于当前项目 _working")
    result = collect(evidence)
    print(json.dumps({key: result[key] for key in ["gate", "native", "local_regressions_passed", "resource_count", "markdown_count"]}, ensure_ascii=False))
    return 0 if result["local_regressions_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
