"""里程碑识别端到端测试脚本。

用法:
    手动运行:  python filemate/tests/test_milestone_e2e.py
    pytest:    pytest -m e2e filemate/tests/test_milestone_e2e.py

功能:
    1. 扫描 datasets/raw/竞赛通知/ 下所有样本文件
    2. 用 FileParser 解析文件内容
    3. 用 MilestoneDetector 识别里程碑
    4. 校验输出结构（date 格式、order 连续）
    5. 将结果保存到 test_milestone_result.json 供人工标注评估

注意: 需要先配置好 .env 中的 API Key。CI 默认跳过（pytest -m "not e2e"）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# 加载 .env
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from filemate.perception.file_parser import FileParser
from filemate.understanding.milestone_detector import MilestoneDetector
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

COMPETITION_DIR = PROJECT_ROOT / "datasets" / "raw" / "竞赛通知"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


def scan_samples() -> list[Path]:
    samples = []
    if not COMPETITION_DIR.exists():
        logger.error("目录不存在: %s", COMPETITION_DIR)
        return samples
    for fp in sorted(COMPETITION_DIR.iterdir()):
        if fp.is_file():
            samples.append(fp)
    return samples


def run_milestone_e2e(
    output_dir: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """跑里程碑识别测试，返回统计结果。

    Parameters
    ----------
    output_dir : Path | None
        JSON 输出目录。None 时写项目根；pytest 里传 tmp_path。
    verbose : bool
        True 时打印逐份明细。

    Returns
    -------
    dict — {total, valid, errors, with_milestones, total_milestones,
            hit_rate, details, output_path}
    """
    _setup_logging(verbose)

    samples = scan_samples()
    if not samples:
        raise FileNotFoundError(f"未找到竞赛通知样本文件: {COMPETITION_DIR}")

    logger.info("共 %d 份竞赛通知样本", len(samples))

    llm_client = LLMClient()
    parser = FileParser()
    detector = MilestoneDetector(llm_client)

    results: list[dict[str, Any]] = []
    errors = 0

    for idx, fp in enumerate(samples, 1):
        logger.info("[%d/%d] %s", idx, len(samples), fp.name)

        try:
            parsed = parser.parse(fp)
            raw_text = parsed.get("raw_text", "")
            if parsed.get("error") or not raw_text.strip():
                errors += 1
                results.append({
                    "file": fp.name,
                    "error": parsed.get("error", "空内容"),
                    "milestones": [],
                })
                logger.warning("  解析失败/空: %s", parsed.get("error", "空"))
                continue
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "error": str(exc), "milestones": []})
            continue

        try:
            milestones = detector.detect(raw_text)
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "error": f"识别失败: {exc}", "milestones": []})
            continue

        results.append({"file": fp.name, "error": None, "milestones": milestones})

        if milestones:
            for m in milestones:
                logger.info("  [%s] %s %s", m["order"], m["date"], m["event"])
        else:
            logger.info("  无里程碑")

    total = len(samples)
    valid = total - errors
    with_milestones = sum(1 for r in results if r.get("milestones"))
    total_milestones = sum(len(r.get("milestones") or []) for r in results)
    hit_rate = round(with_milestones / valid * 100, 2) if valid > 0 else 0.0

    summary = {
        "total": total,
        "valid": valid,
        "errors": errors,
        "with_milestones": with_milestones,
        "total_milestones": total_milestones,
        "hit_rate": hit_rate,
    }

    if verbose:
        print("\n" + "=" * 60)
        print("里程碑识别测试结果")
        print("=" * 60)
        print(f"样本总数:      {total}")
        print(f"有效识别:      {valid}")
        print(f"解析失败:      {errors}")
        print(f"识别到里程碑:  {with_milestones}/{valid} ({hit_rate:.1f}%)")
        print(f"里程碑总条数:  {total_milestones}")
        print("=" * 60)

    output_dir = Path(output_dir) if output_dir is not None else PROJECT_ROOT
    output_path = output_dir / "test_milestone_result.json"
    output_path.write_text(
        json.dumps({"summary": summary, "details": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"\n结果已保存到: {output_path}")
        print("请人工标注 ground truth 后重新运行评估。")

    return {**summary, "details": results, "output_path": output_path}


# ----------------------------------------------------------------------
# pytest 入口（CI 默认跳过：pytest -m "not e2e"）
# ----------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="需要 LLM_API_KEY，见 .env")
def test_milestone_e2e(tmp_path: Path) -> None:
    """竞赛通知里程碑识别：至少有样本识别出结果，且输出结构合法。

    注：命中率不设硬阈值 —— 部分竞赛通知本身没有明确时间节点，
    且有 PDF 解析乱码问题（感知层已知问题）。这里只守结构契约。
    """
    if not scan_samples():
        pytest.skip(f"竞赛通知样本目录为空: {COMPETITION_DIR}")

    result = run_milestone_e2e(output_dir=tmp_path)

    assert result["valid"] > 0, "没有任何样本被有效识别"
    assert result["with_milestones"] > 0, "所有样本都没识别出里程碑，疑似 Prompt 或 LLM 故障"

    # 结构契约：date 必须是 YYYY-MM-DD，order 从 1 连续递增
    for item in result["details"]:
        milestones = item.get("milestones") or []
        for m in milestones:
            assert set(m) == {"event", "date", "order"}, f"{item['file']} 字段不符: {m}"
            assert _DATE_RE.match(m["date"]), f"{item['file']} date 格式非法: {m['date']}"
            assert m["event"], f"{item['file']} event 为空"
        orders = [m["order"] for m in milestones]
        assert orders == list(range(1, len(orders) + 1)), (
            f"{item['file']} order 非连续: {orders}"
        )
    assert result["output_path"].exists()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="里程碑识别端到端测试")
    ap.add_argument("--verbose", "-v", action="store_true", default=True,
                    help="打印逐份明细（手动运行默认开启）")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出错误，不打明细")
    ap.add_argument("--output-dir", type=Path, default=None, help="JSON 输出目录，默认项目根")
    args = ap.parse_args()
    try:
        run_milestone_e2e(output_dir=args.output_dir, verbose=not args.quiet)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
