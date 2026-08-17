"""命名生成端到端测试脚本。

用法:
    手动运行:  python filemate/tests/test_namer_e2e.py
    pytest:    pytest -m e2e filemate/tests/test_namer_e2e.py

功能:
    1. 扫描 datasets/raw/ 下所有样本文件
    2. 用 FileParser 解析文件内容
    3. 用 Classifier 分类 + EntityExtractor 抽取实体
    4. 用 Namer 生成文件名
    5. 校验命名格式合规率，结果保存到 test_namer_result.json 供人工评估

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
from filemate.understanding.classifier import Classifier
from filemate.understanding.entity_extractor import EntityExtractor
from filemate.understanding.namer import Namer
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

DATASETS_DIR = PROJECT_ROOT / "datasets" / "raw"

# 命名规范：[课程]-[类型]-[任务]-[截止]-[状态]，五段方括号，段内不得再有方括号
NAME_PATTERN = re.compile(
    r"^\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]$"
)

# 命名格式合规率验收线
FORMAT_THRESHOLD = 100.0

# 与 namer._MAX_LEN 对齐
MAX_NAME_LEN = 80


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


def run_namer_e2e(
    output_dir: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """跑命名生成测试，返回统计结果。

    Parameters
    ----------
    output_dir : Path | None
        JSON 输出目录。None 时写项目根；pytest 里传 tmp_path。
    verbose : bool
        True 时打印逐份明细。

    Returns
    -------
    dict — {total, valid, errors, format_ok, format_rate, details, output_path}
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
    namer = Namer(llm_client)

    results: list[dict[str, Any]] = []
    errors = 0
    format_ok = 0

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
                    "suggested_name": None,
                })
                logger.warning("  解析失败/空: %s", parsed.get("error", "空"))
                continue
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "actual_category": actual_cat, "error": str(exc), "suggested_name": None})
            continue

        # 分类
        try:
            cat_result = classifier.classify(raw_text, fp.name)
            category = cat_result.get("category", "待确认")
            course_name = cat_result.get("course_name")
        except Exception:
            category = "待确认"
            course_name = None

        # 实体抽取
        try:
            entities = extractor.extract(raw_text)
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "actual_category": actual_cat, "error": f"抽取失败: {exc}", "suggested_name": None})
            continue

        # 生成文件名
        try:
            suggested = namer.generate(
                category=category,
                course=course_name or entities.get("course_name") or "未分类",
                task=entities.get("task_description") or fp.stem,
                deadline=entities.get("deadline") or "",
                status="待处理",
            )
        except Exception as exc:
            errors += 1
            results.append({"file": fp.name, "actual_category": actual_cat, "error": f"命名失败: {exc}", "suggested_name": None})
            continue

        is_valid_format = bool(NAME_PATTERN.match(suggested)) and len(suggested) <= MAX_NAME_LEN
        if is_valid_format:
            format_ok += 1
        else:
            logger.warning("  命名格式不合规: %s", suggested)

        results.append({
            "file": fp.name,
            "actual_category": actual_cat,
            "predicted_category": category,
            "entities": entities,
            "suggested_name": suggested,
            "format_ok": is_valid_format,
        })
        logger.info("  [%s] %s", category, suggested)

    total = len(samples)
    valid = total - errors
    format_rate = round(format_ok / valid * 100, 2) if valid > 0 else 0.0

    summary = {
        "total": total,
        "valid": valid,
        "errors": errors,
        "format_ok": format_ok,
        "format_rate": format_rate,
    }

    if verbose:
        print("\n" + "=" * 60)
        print("命名生成测试结果")
        print("=" * 60)
        print(f"样本总数:    {total}")
        print(f"成功命名:    {valid}")
        print(f"失败/跳过:   {errors}")
        print(f"格式合规:    {format_ok}/{valid} ({format_rate:.1f}%)")
        print("=" * 60)
        bad = [r for r in results if r.get("suggested_name") and not r.get("format_ok")]
        if bad:
            print("\n格式不合规的命名:")
            for r in bad:
                print(f"  {r['file']} → {r['suggested_name']}")

    output_dir = Path(output_dir) if output_dir is not None else PROJECT_ROOT
    output_path = output_dir / "test_namer_result.json"
    output_path.write_text(
        json.dumps({"summary": summary, "details": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"\n结果已保存到: {output_path}")
        print(f"共 {len(results)} 条，请人工评估命名质量。")

    return {**summary, "details": results, "output_path": output_path}


# ----------------------------------------------------------------------
# pytest 入口（CI 默认跳过：pytest -m "not e2e"）
# ----------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="需要 LLM_API_KEY，见 .env")
def test_namer_e2e(tmp_path: Path) -> None:
    """W3 验收：命名格式 100% 符合 [课程]-[类型]-[任务]-[截止]-[状态]。"""
    if not scan_samples():
        pytest.skip(f"样本目录为空: {DATASETS_DIR}")

    result = run_namer_e2e(output_dir=tmp_path)

    assert result["valid"] > 0, "没有任何样本成功生成命名"
    assert result["format_rate"] >= FORMAT_THRESHOLD, (
        f"命名格式合规率 {result['format_rate']}% 低于验收标准 {FORMAT_THRESHOLD}%"
    )
    assert result["output_path"].exists()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="命名生成端到端测试")
    ap.add_argument("--verbose", "-v", action="store_true", default=True,
                    help="打印逐份明细（手动运行默认开启）")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出错误，不打明细")
    ap.add_argument("--output-dir", type=Path, default=None, help="JSON 输出目录，默认项目根")
    args = ap.parse_args()
    try:
        run_namer_e2e(output_dir=args.output_dir, verbose=not args.quiet)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
