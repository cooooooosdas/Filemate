"""分类器端到端测试脚本。

用法:
    python filemate/tests/test_classifier_e2e.py

功能:
    1. 扫描 datasets/raw/ 下所有样本文件
    2. 用 FileParser 解析文件内容
    3. 用 Classifier 做分类
    4. 对比分类结果与真实类别（文件夹名）
    5. 输出准确率统计

注意: 需要先配置好 .env 中的 API Key。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# 加载 .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            import os
            os.environ[key.strip()] = value.strip()

# 项目根目录（本脚本放在项目根目录下）
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from filemate.perception.file_parser import FileParser
from filemate.understanding.classifier import Classifier
from filemate.llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 样本目录
DATASETS_DIR = PROJECT_ROOT / "datasets" / "raw"

# 结果存储
results: list[dict[str, Any]] = []


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


def test_classifier():
    """跑分类测试。"""
    samples = scan_samples()
    if not samples:
        logger.error("没有找到任何样本文件！请先把文件放到 datasets/raw/ 对应类别文件夹下。")
        sys.exit(1)

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
    classifier = Classifier(llm_client) if llm_client else Classifier(None)

    # 逐份测试
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
                "method": "rule" if "关键词" in reason else "llm",
            })

            if "关键词" in reason:
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

    # 输出统计
    total = len(samples)
    valid = total - errors
    accuracy = correct / valid * 100 if valid > 0 else 0

    print("\n" + "=" * 60)
    print("分类测试结果")
    print("=" * 60)
    print(f"样本总数:  {total}")
    print(f"有效测试:  {valid}")
    print(f"分类正确:  {correct}")
    print(f"分类错误:  {valid - correct}")
    print(f"解析错误:  {errors}")
    print(f"准确率:    {accuracy:.1f}% ({correct}/{valid})")
    print(f"规则命中:  {rule_hits} 次")
    print(f"LLM 调用:  {llm_calls} 次")
    print("=" * 60)

    # 按类别统计
    print("\n按类别统计:")
    categories = {}
    for r in results:
        cat = r["actual"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        if r["correct"]:
            categories[cat]["correct"] += 1

    for cat, stats in sorted(categories.items()):
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['correct']}/{stats['total']} ({acc:.0f}%)")

    # 错误分析
    wrong = [r for r in results if not r["correct"] and r["method"] != "error"]
    if wrong:
        print("\n分类错误的样本:")
        for r in wrong:
            print(f"  {r['file']}")
            print(f"    实际: {r['actual']} → 预测: {r['predicted']} ({r['confidence']:.0%})")

    # 保存详细结果到 JSON
    output_path = PROJECT_ROOT / "test_result.json"
    output_path.write_text(
        json.dumps({
            "summary": {
                "total": total,
                "valid": valid,
                "correct": correct,
                "accuracy": round(accuracy, 2),
                "rule_hits": rule_hits,
                "llm_calls": llm_calls,
                "errors": errors,
            },
            "by_category": categories,
            "details": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    test_classifier()
