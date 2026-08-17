"""分类器端到端测试脚本。

用法:
    手动运行:  python filemate/tests/test_classifier_e2e.py --verbose
    pytest:    pytest -m e2e filemate/tests/test_classifier_e2e.py

功能:
    1. 扫描 datasets/raw/ 下所有样本文件
    2. 用 FileParser 解析文件内容
    3. 用 Classifier 做分类
    4. 对比分类结果与真实类别（文件夹名）
    5. 输出准确率统计

注意: 需要先配置好 .env 中的 API Key。CI 默认跳过（pytest -m "not e2e"）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# 加载 .env（项目根目录下的 .env）
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()

# 项目根目录（本脚本放在 filemate/tests/ 下，上溯两级到项目根）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from filemate.perception.file_parser import FileParser
from filemate.understanding.classifier import Classifier
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

# 样本目录
DATASETS_DIR = PROJECT_ROOT / "datasets" / "raw"

# W3 验收标准：分类准确率 ≥ 85%
ACCURACY_THRESHOLD = 85.0


def _setup_logging(verbose: bool) -> None:
    """verbose 模式打 INFO，否则只打 WARNING 以上。"""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


def scan_samples() -> list[tuple[Path, str]]:
    """扫描 datasets/raw/ 下所有样本文件，返回 (文件路径, 真实类别) 列表。"""
    samples = []
    if not DATASETS_DIR.exists():
        logger.error("样本目录不存在: %s", DATASETS_DIR)
        return samples

    for category_dir in sorted(DATASETS_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        if category_dir.name in (".gitkeep",):
            continue
        category = category_dir.name
        for file_path in sorted(category_dir.iterdir()):
            if file_path.is_file():
                samples.append((file_path, category))

    return samples


def run_classifier_e2e(
    output_dir: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """跑分类测试，返回统计结果。

    Parameters
    ----------
    output_dir : Path | None
        JSON 结果输出目录。None 时写到项目根（手动运行的习惯位置）；
        pytest 里传 tmp_path，避免污染项目根目录。
    verbose : bool
        True 时打印逐份明细与统计表格，供手动运行时人工检查。

    Returns
    -------
    dict — {total, valid, correct, accuracy, rule_hits, llm_calls, errors,
            by_category, details, output_path}
    """
    _setup_logging(verbose)

    samples = scan_samples()
    if not samples:
        raise FileNotFoundError(
            f"没有找到任何样本文件，请先把文件放到 {DATASETS_DIR} 对应类别文件夹下"
        )

    logger.info("共找到 %d 份样本文件", len(samples))

    # 初始化模块
    try:
        llm_client = LLMClient()
        logger.info("LLM 客户端初始化成功")
    except Exception as exc:
        logger.warning("LLM 客户端初始化失败: %s", exc)
        logger.warning("将仅使用关键词规则分类，无法测试 LLM 效果。")
        llm_client = None

    parser = FileParser()
    classifier = Classifier(llm_client)

    # 逐份测试
    results: list[dict[str, Any]] = []
    correct = 0
    rule_hits = 0
    llm_calls = 0
    errors = 0

    for idx, (file_path, actual_category) in enumerate(samples, 1):
        logger.info("[%d/%d] 测试: %s (真实: %s)", idx, len(samples), file_path.name, actual_category)

        # 解析文件
        try:
            parsed = parser.parse(file_path)
            raw_text = parsed.get("raw_text", "")
            if parsed.get("error"):
                logger.warning("  解析失败: %s", parsed["error"])
                errors += 1
                results.append({
                    "file": file_path.name,
                    "actual": actual_category,
                    "predicted": "解析失败",
                    "confidence": 0.0,
                    "correct": False,
                    "method": "error",
                })
                continue
        except Exception as exc:
            logger.error("  解析异常: %s", exc)
            errors += 1
            results.append({
                "file": file_path.name,
                "actual": actual_category,
                "predicted": "解析异常",
                "confidence": 0.0,
                "correct": False,
                "method": "error",
            })
            continue

        if not raw_text.strip():
            logger.warning("  文件内容为空，跳过")
            errors += 1
            results.append({
                "file": file_path.name,
                "actual": actual_category,
                "predicted": "空内容",
                "confidence": 0.0,
                "correct": False,
                "method": "skip",
            })
            continue

        # 分类
        try:
            result = classifier.classify(raw_text, file_path.name)
            predicted = result.get("category", "待确认")
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "")
            is_correct = (predicted == actual_category)

            if is_correct:
                correct += 1
                logger.info("  ✓ 预测: %s (%.0f%%) %s", predicted, confidence * 100, reason)
            else:
                logger.info("  ✗ 预测: %s (%.0f%%), 实际: %s %s", predicted, confidence * 100, actual_category, reason)

            results.append({
                "file": file_path.name,
                "actual": actual_category,
                "predicted": predicted,
                "confidence": confidence,
                "correct": is_correct,
                "method": result.get("method", "llm"),
            })

            if result.get("method") == "rule":
                rule_hits += 1
            else:
                llm_calls += 1

        except Exception as exc:
            logger.error("  分类异常: %s", exc)
            errors += 1
            results.append({
                "file": file_path.name,
                "actual": actual_category,
                "predicted": "分类异常",
                "confidence": 0.0,
                "correct": False,
                "method": "error",
            })

    # 统计
    total = len(samples)
    valid = total - errors
    accuracy = correct / valid * 100 if valid > 0 else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r["actual"]
        by_category.setdefault(cat, {"total": 0, "correct": 0})
        by_category[cat]["total"] += 1
        if r["correct"]:
            by_category[cat]["correct"] += 1

    summary = {
        "total": total,
        "valid": valid,
        "correct": correct,
        "accuracy": round(accuracy, 2),
        "rule_hits": rule_hits,
        "llm_calls": llm_calls,
        "errors": errors,
    }

    if verbose:
        _print_report(summary, by_category, results)

    # 保存详细结果到 JSON
    output_dir = Path(output_dir) if output_dir is not None else PROJECT_ROOT
    output_path = output_dir / "test_result.json"
    output_path.write_text(
        json.dumps({
            "summary": summary,
            "by_category": by_category,
            "details": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"\n详细结果已保存到: {output_path}")

    return {**summary, "by_category": by_category, "details": results, "output_path": output_path}


def _print_report(
    summary: dict[str, Any],
    by_category: dict[str, dict[str, int]],
    results: list[dict[str, Any]],
) -> None:
    """手动运行时的人工检查报告。"""
    print("\n" + "=" * 60)
    print("分类测试结果")
    print("=" * 60)
    print(f"样本总数:  {summary['total']}")
    print(f"有效测试:  {summary['valid']}")
    print(f"分类正确:  {summary['correct']}")
    print(f"分类错误:  {summary['valid'] - summary['correct']}")
    print(f"解析错误:  {summary['errors']}")
    print(f"准确率:    {summary['accuracy']:.1f}% ({summary['correct']}/{summary['valid']})")
    print(f"规则命中:  {summary['rule_hits']} 次")
    print(f"LLM 调用:  {summary['llm_calls']} 次")
    print("=" * 60)

    print("\n按类别统计:")
    for cat, stats in sorted(by_category.items()):
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['correct']}/{stats['total']} ({acc:.0f}%)")

    wrong = [r for r in results if not r["correct"] and r["method"] != "error"]
    if wrong:
        print("\n分类错误的样本:")
        for r in wrong:
            print(f"  {r['file']}")
            print(f"    实际: {r['actual']} → 预测: {r['predicted']} ({r['confidence']:.0%})")


# ----------------------------------------------------------------------
# pytest 入口（CI 默认跳过：pytest -m "not e2e"）
# ----------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="需要 LLM_API_KEY，见 .env")
def test_classifier_e2e(tmp_path: Path) -> None:
    """W3 验收：57 份样本分类准确率 ≥ 85%。"""
    if not scan_samples():
        pytest.skip(f"样本目录为空: {DATASETS_DIR}")

    result = run_classifier_e2e(output_dir=tmp_path)

    assert result["valid"] > 0, "没有任何样本被有效解析"
    assert result["accuracy"] >= ACCURACY_THRESHOLD, (
        f"分类准确率 {result['accuracy']}% 低于验收标准 {ACCURACY_THRESHOLD}%"
    )
    # 结果文件应落在 tmp_path 里，不污染项目根
    assert result["output_path"].exists()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="分类器端到端测试")
    ap.add_argument("--verbose", "-v", action="store_true", default=True,
                    help="打印逐份明细与统计表格（手动运行默认开启）")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出错误，不打明细")
    ap.add_argument("--output-dir", type=Path, default=None, help="JSON 输出目录，默认项目根")
    args = ap.parse_args()
    try:
        run_classifier_e2e(output_dir=args.output_dir, verbose=not args.quiet)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
