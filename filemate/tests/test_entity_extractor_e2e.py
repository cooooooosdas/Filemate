"""实体抽取端到端测试脚本。

用法:
    手动运行:  python filemate/tests/test_entity_extractor_e2e.py
    pytest:    pytest -m e2e filemate/tests/test_entity_extractor_e2e.py

功能:
    1. 扫描 datasets/raw/ 下所有样本文件
    2. 用 FileParser 解析文件内容
    3. 用 EntityExtractor 抽取实体
    4. 统计各字段非空率（近似召回，ground truth 需人工标注）
    5. 将结果保存到 test_entity_result.json 供人工标注评估

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
from filemate.understanding.classifier import Classifier
from filemate.understanding.entity_extractor import EntityExtractor
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

DATASETS_DIR = PROJECT_ROOT / "datasets" / "raw"

# W3 验收标准：关键字段（task_description）召回 ≥ 80%
TASK_FILL_THRESHOLD = 80.0

# 统计哪些字段的非空率
TRACKED_FIELDS = ("course_name", "task_description", "deadline", "location")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


def scan_samples() -> list[tuple[Path, str]]:
    samples = []
    if not DATASETS_DIR.exists():
        return samples
    for category_dir in sorted(DATASETS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name == ".gitkeep":
            continue
        for fp in sorted(category_dir.iterdir()):
            if fp.is_file():
                samples.append((fp, category_dir.name))
    return samples


def run_entity_extractor_e2e(
    output_dir: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """跑实体抽取测试，返回统计结果。

    Parameters
    ----------
    output_dir : Path | None
        JSON 输出目录。None 时写项目根；pytest 里传 tmp_path。
    verbose : bool
        True 时打印逐份明细。

    Returns
    -------
    dict — {total, valid, errors, fill_rates, details, output_path}
        fill_rates 是各字段非空率（百分比）。注意这是"抽出了东西"的比例，
        不等于真召回率 —— 真召回需要人工标注 ground truth 后另算。
    """
    _setup_logging(verbose)

    samples = scan_samples()
    if not samples:
        raise FileNotFoundError(f"未找到样本文件: {DATASETS_DIR}")

    logger.info("共 %d 份样本", len(samples))

    llm_client = LLMClient()
    parser = FileParser()
    classifier = Classifier(llm_client)
    extractor = EntityExtractor(llm_client)

    results: list[dict[str, Any]] = []
    errors = 0
    filled = {field: 0 for field in TRACKED_FIELDS}

    for idx, (fp, actual_cat) in enumerate(samples, 1):
        logger.info("[%d/%d] %s (真实: %s)", idx, len(samples), fp.name, actual_cat)

        try:
            parsed = parser.parse(fp)
            raw_text = parsed.get("raw_text", "")
            if parsed.get("error") or not raw_text.strip():
                errors += 1
                results.append({
                    "file": fp.name,
                    "actual_category": actual_cat,
                    "error": parsed.get("error", "空内容"),
                    "entities": None,
                })
                logger.warning("  解析失败/空: %s", parsed.get("error", "空"))
                continue
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "actual_category": actual_cat, "error": str(exc), "entities": None})
            continue

        try:
            cat_result = classifier.classify(raw_text, fp.name)
            category = cat_result.get("category", "待确认")
        except Exception:
            category = "待确认"

        try:
            entities = extractor.extract(raw_text)
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "actual_category": actual_cat, "error": f"抽取失败: {exc}", "entities": None})
            continue

        for field in TRACKED_FIELDS:
            if entities.get(field):
                filled[field] += 1

        results.append({
            "file": fp.name,
            "actual_category": actual_cat,
            "predicted_category": category,
            "entities": entities,
        })

        logger.info(
            "  [分类] %s | 课程=%s 任务=%s 截止=%s 地点=%s",
            category,
            entities.get("course_name") or "—",
            entities.get("task_description") or "—",
            entities.get("deadline") or "—",
            entities.get("location") or "—",
        )

    total = len(samples)
    valid = total - errors
    fill_rates = {
        field: round(filled[field] / valid * 100, 2) if valid > 0 else 0.0
        for field in TRACKED_FIELDS
    }

    summary = {"total": total, "valid": valid, "errors": errors, "fill_rates": fill_rates}

    if verbose:
        print("\n" + "=" * 60)
        print("实体抽取测试结果")
        print("=" * 60)
        print(f"样本总数:  {total}")
        print(f"有效抽取:  {valid}")
        print(f"解析失败:  {errors}")
        print("\n各字段非空率（近似召回）:")
        for field in TRACKED_FIELDS:
            print(f"  {field}: {filled[field]}/{valid} ({fill_rates[field]:.1f}%)")
        print("=" * 60)

    output_dir = Path(output_dir) if output_dir is not None else PROJECT_ROOT
    output_path = output_dir / "test_entity_result.json"
    output_path.write_text(
        json.dumps({"summary": summary, "details": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"\n结果已保存到: {output_path}")
        print(f"共 {len(results)} 条，请人工标注 recall 后重新运行评估。")

    return {**summary, "details": results, "output_path": output_path}


# ----------------------------------------------------------------------
# pytest 入口（CI 默认跳过：pytest -m "not e2e"）
# ----------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="需要 LLM_API_KEY，见 .env")
def test_entity_extractor_e2e(tmp_path: Path) -> None:
    """W3 验收：task_description 非空率 ≥ 80%。"""
    if not scan_samples():
        pytest.skip(f"样本目录为空: {DATASETS_DIR}")

    result = run_entity_extractor_e2e(output_dir=tmp_path)

    assert result["valid"] > 0, "没有任何样本被有效抽取"
    task_rate = result["fill_rates"]["task_description"]
    assert task_rate >= TASK_FILL_THRESHOLD, (
        f"task_description 非空率 {task_rate}% 低于验收标准 {TASK_FILL_THRESHOLD}%"
    )
    # 契约检查：每条成功记录的 5 个字段都必须在
    for item in result["details"]:
        entities = item.get("entities")
        if entities is None:
            continue
        for field in (*TRACKED_FIELDS, "extra_entities"):
            assert field in entities, f"{item['file']} 缺字段 {field}"
        assert isinstance(entities["extra_entities"], dict)
    assert result["output_path"].exists()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="实体抽取端到端测试")
    ap.add_argument("--verbose", "-v", action="store_true", default=True,
                    help="打印逐份明细（手动运行默认开启）")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出错误，不打明细")
    ap.add_argument("--output-dir", type=Path, default=None, help="JSON 输出目录，默认项目根")
    args = ap.parse_args()
    try:
        run_entity_extractor_e2e(output_dir=args.output_dir, verbose=not args.quiet)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
