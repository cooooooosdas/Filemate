"""W4 联调测试：五模块串联跑通并生成 Markdown 报告（任务 7）。

用法:
    手动运行:  python filemate/tests/test_pipeline_e2e.py
    pytest:    pytest -m e2e filemate/tests/test_pipeline_e2e.py

Pipeline:
    parse (FileParser) → classify (Classifier) → extract (EntityExtractor)
    → detect (MilestoneDetector) → name (Namer)

与单模块 e2e 的区别：单模块测试各自独立跑，本脚本检验**模块之间的接缝** ——
例如分类给不出 course_name 时命名模块是否只能填「未分类」这类断裂点。

样本集: filemate/tests/fixtures/pipeline_w4_samples.json（20 份，含筛选标准）
输出:   docs/联调测试报告_W4.md + pipeline_w4_result.json

注意: 需要配置 .env 中的 API Key。CI 默认跳过（pytest -m "not e2e"）。
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
from filemate.understanding.milestone_detector import MilestoneDetector
from filemate.understanding.namer import Namer
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

DATASETS_DIR = PROJECT_ROOT / "datasets" / "raw"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "pipeline_w4_samples.json"

# 命名规范：五段方括号
NAME_PATTERN = re.compile(
    r"^\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]-\[[^\[\]]+\]$"
)

# Namer 在字段缺失时填入的占位值 —— 命名"格式正确但内容无意义"的信号
PLACEHOLDERS = {"未分类", "未命名", "待定"}

# 各类别真正必需的命名字段。课件/参考资料本身没有截止日期，填「待定」是正确
# 行为而非缺陷；竞赛/大创/行政通知本身没有课程名，第一段由主办方补位。
# 只有「该有却没有」才计为命名不通过。
REQUIRED_SLOTS: dict[str, set[str]] = {
    "课件":     {"course"},
    "参考资料": {"course"},
    "作业":     {"course"},
    "考试通知": {"course", "deadline"},
    "竞赛通知": {"course", "deadline"},
    "大创通知": {"course"},
    "待确认":   {"course"},
}
# 占位值 → 它占的是哪个字段
_PLACEHOLDER_SLOT = {"未分类": "course", "待定": "deadline", "未命名": "task"}

# 失败原因分类（review 要求：规则未命中 / LLM 误判 / 实体缺失 / 其他）
REASON_PARSE = "解析失败"
REASON_RULE_WRONG = "规则误判"
REASON_LLM_WRONG = "LLM 误判"
REASON_ENTITY_MISSING = "实体缺失"
REASON_NAME_BAD = "命名不合规"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


def load_manifest() -> list[dict[str, str]]:
    """读取样本清单，返回 [{category, file, note?}, ...]。"""
    if not MANIFEST.exists():
        raise FileNotFoundError(f"样本清单不存在: {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data["samples"]


def resolve_samples() -> tuple[list[tuple[Path, str, str]], list[str]]:
    """把清单解析成 (路径, 真实类别, 备注) 列表。返回 (已找到, 缺失文件名)。"""
    found: list[tuple[Path, str, str]] = []
    missing: list[str] = []
    for item in load_manifest():
        path = DATASETS_DIR / item["category"] / item["file"]
        if path.is_file():
            found.append((path, item["category"], item.get("note", "")))
        else:
            missing.append(f"{item['category']}/{item['file']}")
    return found, missing


def run_pipeline_e2e(
    output_dir: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """逐份跑完整 pipeline，生成统计与 Markdown 报告。

    Parameters
    ----------
    output_dir : Path | None
        报告与 JSON 输出目录。None 时报告写 `docs/`、JSON 写项目根；
        pytest 里传 tmp_path，两者都落在临时目录，不污染仓库。
    verbose : bool
        True 时打印逐份明细。

    Returns
    -------
    dict — 含 summary / details / report_path / json_path
    """
    _setup_logging(verbose)

    samples, missing = resolve_samples()
    if missing:
        logger.warning("清单中 %d 份样本在 datasets/raw/ 下找不到:", len(missing))
        for m in missing:
            logger.warning("  缺失: %s", m)
    if not samples:
        raise FileNotFoundError(
            f"清单里没有任何样本能在 {DATASETS_DIR} 下找到，请确认样本已放到对应类别文件夹"
        )

    logger.info("共 %d 份样本参与联调", len(samples))

    llm_client = LLMClient()
    parser = FileParser()
    classifier = Classifier(llm_client)
    extractor = EntityExtractor(llm_client)
    detector = MilestoneDetector(llm_client)
    namer = Namer(llm_client)

    details: list[dict[str, Any]] = []

    for idx, (path, actual_cat, note) in enumerate(samples, 1):
        logger.info("[%d/%d] %s", idx, len(samples), path.name)
        row: dict[str, Any] = {
            "file": path.name,
            "actual_category": actual_cat,
            "manifest_note": note,
            "reasons": [],
        }

        # ---------- 1. parse ----------
        try:
            parsed = parser.parse(path)
            raw_text = parsed.get("raw_text", "") or ""
            if parsed.get("error") or not raw_text.strip():
                row["error"] = parsed.get("error") or "正文为空"
                row["reasons"].append(REASON_PARSE)
                details.append(row)
                logger.warning("  解析失败: %s", row["error"])
                continue
        except Exception as exc:
            row["error"] = f"解析异常: {exc}"
            row["reasons"].append(REASON_PARSE)
            details.append(row)
            continue

        row["text_len"] = len(raw_text)
        # PDF 提取乱码的特征（感知层已知问题）
        row["cid_garbled"] = "(cid:" in raw_text

        # ---------- 2. classify ----------
        try:
            cls = classifier.classify(raw_text, path.name)
        except Exception as exc:
            cls = {}
            row["classify_error"] = str(exc)
        predicted = cls.get("category", "待确认")
        confidence = float(cls.get("confidence", 0.0))
        method = cls.get("method", "none")
        correct = predicted == actual_cat

        row.update({
            "predicted_category": predicted,
            "confidence": round(confidence, 3),
            "method": method,
            "correct": correct,
        })
        if not correct:
            row["reasons"].append(REASON_RULE_WRONG if method == "rule" else REASON_LLM_WRONG)

        # ---------- 3. extract ----------
        try:
            entities = extractor.extract(raw_text)
        except Exception as exc:
            entities = {}
            row["extract_error"] = str(exc)
        row["entities"] = entities
        if not entities.get("task_description"):
            row["reasons"].append(REASON_ENTITY_MISSING)

        # ---------- 4. detect ----------
        try:
            milestones = detector.detect(raw_text)
        except Exception as exc:
            milestones = []
            row["detect_error"] = str(exc)
        row["milestones"] = milestones

        # ---------- 5. name ----------
        course = cls.get("course_name") or entities.get("course_name") or ""
        task = entities.get("task_description") or path.stem
        deadline = entities.get("deadline") or ""
        try:
            suggested = namer.generate(
                category=predicted,
                course=course,
                task=task,
                deadline=deadline,
                status="待处理",
                extra_entities=entities.get("extra_entities"),
            )
        except Exception as exc:
            suggested = None
            row["name_error"] = str(exc)
            row["reasons"].append(REASON_NAME_BAD)

        row["suggested_name"] = suggested
        if suggested:
            fmt_ok = bool(NAME_PATTERN.match(suggested)) and len(suggested) <= 80
            used_ph = sorted(p for p in PLACEHOLDERS if f"[{p}]" in suggested)
            # 只有「该类别本应有、却填了占位值」的字段才算缺陷
            required = REQUIRED_SLOTS.get(actual_cat, {"course"})
            blocking = sorted(
                p for p in used_ph if _PLACEHOLDER_SLOT.get(p) in required
            )
            row["name_format_ok"] = fmt_ok
            row["name_placeholders"] = used_ph
            row["name_blocking_placeholders"] = blocking
            row["name_pass"] = fmt_ok and not blocking
            if not fmt_ok:
                row["reasons"].append(REASON_NAME_BAD)
            logger.info("  [%s %.0f%%] %s", predicted, confidence * 100, suggested)

        details.append(row)

    summary = _summarize(details, len(samples), missing)
    if verbose:
        _print_summary(summary)

    # ---------- 输出 ----------
    if output_dir is not None:
        out = Path(output_dir)
        report_path = out / "联调测试报告_W4.md"
        json_path = out / "pipeline_w4_result.json"
    else:
        docs = PROJECT_ROOT / "docs"
        docs.mkdir(exist_ok=True)
        report_path = docs / "联调测试报告_W4.md"
        json_path = PROJECT_ROOT / "pipeline_w4_result.json"

    report_path.write_text(_render_report(summary, details, missing), encoding="utf-8")
    json_path.write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"\n报告已生成: {report_path}")
        print(f"原始数据: {json_path}")

    return {
        **summary,
        "details": details,
        "report_path": report_path,
        "json_path": json_path,
    }


# ----------------------------------------------------------------------
# 统计与报告
# ----------------------------------------------------------------------

def _summarize(
    details: list[dict[str, Any]],
    total: int,
    missing: list[str],
) -> dict[str, Any]:
    parsed = [r for r in details if REASON_PARSE not in r["reasons"]]
    n_parsed = len(parsed)
    correct = sum(1 for r in parsed if r.get("correct"))

    fields = ("course_name", "task_description", "deadline", "location")
    recall = {
        f: round(sum(1 for r in parsed if (r.get("entities") or {}).get(f)) / n_parsed * 100, 2)
        if n_parsed else 0.0
        for f in fields
    }

    named = [r for r in parsed if r.get("suggested_name")]
    fmt_ok = sum(1 for r in named if r.get("name_format_ok"))
    # 通过 = 格式合规 且 无「该有却缺」的占位值（按类别区分，见 REQUIRED_SLOTS）
    clean = sum(1 for r in named if r.get("name_pass"))
    # 参考口径：完全无任何占位值（旧的严格算法，供对比）
    strict = sum(1 for r in named if r.get("name_format_ok") and not r.get("name_placeholders"))

    with_ms = sum(1 for r in parsed if r.get("milestones"))
    n_ms = sum(len(r.get("milestones") or []) for r in parsed)

    by_cat: dict[str, dict[str, int]] = {}
    for r in details:
        c = r["actual_category"]
        by_cat.setdefault(c, {"total": 0, "correct": 0, "parse_failed": 0})
        by_cat[c]["total"] += 1
        if REASON_PARSE in r["reasons"]:
            by_cat[c]["parse_failed"] += 1
        elif r.get("correct"):
            by_cat[c]["correct"] += 1

    reason_counts: dict[str, int] = {}
    for r in details:
        for reason in r["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "total": total,
        "missing_from_disk": len(missing),
        "parsed": n_parsed,
        "parse_failed": total - n_parsed,
        "cid_garbled": sum(1 for r in parsed if r.get("cid_garbled")),
        "correct": correct,
        "accuracy": round(correct / n_parsed * 100, 2) if n_parsed else 0.0,
        "rule_hits": sum(1 for r in parsed if r.get("method") == "rule"),
        "llm_calls": sum(1 for r in parsed if r.get("method") == "llm"),
        "field_recall": recall,
        "named": len(named),
        "name_format_ok": fmt_ok,
        "name_format_rate": round(fmt_ok / len(named) * 100, 2) if named else 0.0,
        "name_no_placeholder": clean,
        "name_pass_rate": round(clean / len(named) * 100, 2) if named else 0.0,
        "name_strict_no_placeholder": strict,
        "name_strict_rate": round(strict / len(named) * 100, 2) if named else 0.0,
        "with_milestones": with_ms,
        "total_milestones": n_ms,
        "by_category": by_cat,
        "failure_reasons": reason_counts,
    }


def _print_summary(s: dict[str, Any]) -> None:
    print("\n" + "=" * 64)
    print("W4 联调测试结果")
    print("=" * 64)
    print(f"样本总数:      {s['total']}（清单缺失 {s['missing_from_disk']}）")
    print(f"解析成功:      {s['parsed']}    解析失败: {s['parse_failed']}    PDF 乱码: {s['cid_garbled']}")
    print(f"分类准确率:    {s['accuracy']}%  ({s['correct']}/{s['parsed']})")
    print(f"规则/LLM:      {s['rule_hits']} / {s['llm_calls']}")
    print("字段召回:")
    for k, v in s["field_recall"].items():
        print(f"  {k:<18} {v}%")
    print(f"命名格式合规:  {s['name_format_rate']}%  ({s['name_format_ok']}/{s['named']})")
    print(f"命名通过率:    {s['name_pass_rate']}%  ({s['name_no_placeholder']}/{s['named']})  ← 按类别区分必需字段")
    print(f"命名零占位率:  {s['name_strict_rate']}%  ({s['name_strict_no_placeholder']}/{s['named']})  ← 严格参考值")
    print(f"里程碑:        {s['with_milestones']} 份有结果，共 {s['total_milestones']} 条")
    if s["failure_reasons"]:
        print("失败原因分布:")
        for k, v in sorted(s["failure_reasons"].items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
    print("=" * 64)


def _cell(value: Any) -> str:
    """Markdown 表格单元格：空值转 —，转义竖线。"""
    if value in (None, "", [], {}):
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_report(
    s: dict[str, Any],
    details: list[dict[str, Any]],
    missing: list[str],
) -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    L: list[str] = []
    add = L.append

    add("# FileMate 理解层 W4 联调测试报告")
    add("")
    add("| 项 | 值 |")
    add("|---|---|")
    add(f"| 负责人 | 张金宝（理解层） |")
    add(f"| Pipeline | `parse → classify → extract → detect → name` |")
    add(f"| 样本数 | {s['total']} 份（见 `filemate/tests/fixtures/pipeline_w4_samples.json`） |")
    add(f"| 复现命令 | `pytest -m e2e filemate/tests/test_pipeline_e2e.py` |")
    add("")

    add("## 一、结论摘要")
    add("")
    add("| 指标 | 结果 | 说明 |")
    add("|---|---|---|")
    add(f"| 解析成功率 | {s['parsed']}/{s['total']} | 失败 {s['parse_failed']} 份，PDF 乱码 {s['cid_garbled']} 份 |")
    add(f"| **分类准确率** | **{s['accuracy']}%** | {s['correct']}/{s['parsed']}，规则命中 {s['rule_hits']} / LLM {s['llm_calls']} |")
    add(f"| task_description 召回 | {s['field_recall']['task_description']}% | 关键字段 |")
    add(f"| deadline 召回 | {s['field_recall']['deadline']}% | 部分文件本身无截止时间 |")
    add(f"| course_name 召回 | {s['field_recall']['course_name']}% | 竞赛/行政通知本身无课程名 |")
    add(f"| location 召回 | {s['field_recall']['location']}% | |")
    add(f"| 里程碑识别 | {s['with_milestones']} 份有结果 | 共 {s['total_milestones']} 条 |")
    add(f"| 命名格式合规率 | {s['name_format_rate']}% | {s['name_format_ok']}/{s['named']} 符合五段格式 |")
    add(f"| **命名通过率** | **{s['name_pass_rate']}%** | {s['name_no_placeholder']}/{s['named']} 格式合规且必需字段无占位值 |")
    add(f"| 命名零占位率 | {s['name_strict_rate']}% | {s['name_strict_no_placeholder']}/{s['named']} 完全不含任何占位值（严格参考值） |")
    add("")
    add("> **「命名通过率」的判定口径**：格式合规，**且**该类别本应有的字段没有填占位值。")
    add("> 课件、参考资料本身没有截止日期，填「待定」是正确行为而非缺陷；竞赛、大创、")
    add("> 行政通知本身没有课程名，第一段由主办方补位。只有「该有却没有」才算不通过。")
    add("> 「命名零占位率」是不区分类别的严格值，仅供对比参考。")
    add("")

    add("## 二、逐份结果")
    add("")
    add("| 文件 | 真实类别 | 分类(置信度) | 课程名 | 任务描述 | 截止时间 | 命名合理性 | 备注 |")
    add("|---|---|---|---|---|---|---|---|")
    for r in details:
        ent = r.get("entities") or {}
        name = r.get("suggested_name")
        if REASON_PARSE in r["reasons"]:
            verdict = "❌ 未产出"
        elif not r.get("name_format_ok"):
            verdict = "❌ 格式错误"
        elif r.get("name_blocking_placeholders"):
            verdict = "❌ 缺必需字段 " + "/".join(r["name_blocking_placeholders"])
        elif r.get("name_placeholders"):
            verdict = "✅（含 " + "/".join(r["name_placeholders"]) + "，该类别不要求）"
        else:
            verdict = "✅"

        remarks = []
        if r.get("error"):
            remarks.append(r["error"])
        if r.get("cid_garbled"):
            remarks.append("PDF 提取乱码")
        if r.get("milestones"):
            remarks.append(f"里程碑 {len(r['milestones'])} 条")
        if not r.get("correct") and REASON_PARSE not in r["reasons"]:
            remarks.append(f"误判（{r.get('method')}）")
        if r.get("manifest_note"):
            remarks.append(r["manifest_note"])

        cls_cell = "—"
        if r.get("predicted_category"):
            mark = "✓" if r.get("correct") else "✗"
            cls_cell = f"{mark} {r['predicted_category']} ({r.get('confidence', 0):.2f})"

        add("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            _cell(r["file"][:40]),
            _cell(r["actual_category"]),
            _cell(cls_cell),
            _cell(ent.get("course_name")),
            _cell((ent.get("task_description") or "")[:24] or None),
            _cell(ent.get("deadline")),
            verdict,
            _cell("；".join(remarks)),
        ))
    add("")
    add("### 生成的文件名")
    add("")
    add("| 文件 | 建议命名 |")
    add("|---|---|")
    for r in details:
        if r.get("suggested_name"):
            add(f"| {_cell(r['file'][:36])} | `{r['suggested_name']}` |")
    add("")

    add("## 三、按类别统计")
    add("")
    add("| 类别 | 样本 | 分类正确 | 解析失败 | 准确率 |")
    add("|---|---|---|---|---|")
    for cat, st in sorted(s["by_category"].items()):
        valid = st["total"] - st["parse_failed"]
        acc = f"{st['correct'] / valid * 100:.0f}%" if valid else "—"
        add(f"| {cat} | {st['total']} | {st['correct']} | {st['parse_failed']} | {acc} |")
    add("")

    add("## 四、失败案例与原因分析")
    add("")
    if s["failure_reasons"]:
        add("| 原因 | 次数 |")
        add("|---|---|")
        for k, v in sorted(s["failure_reasons"].items(), key=lambda x: -x[1]):
            add(f"| {k} | {v} |")
        add("")
        add("### 逐条明细")
        add("")
        for r in details:
            if not r["reasons"]:
                continue
            add(f"**{r['file']}**（真实：{r['actual_category']}）")
            add("")
            for reason in r["reasons"]:
                if reason == REASON_PARSE:
                    add(f"- `{reason}` — {r.get('error')}")
                elif reason in (REASON_RULE_WRONG, REASON_LLM_WRONG):
                    add(f"- `{reason}` — 预测「{r.get('predicted_category')}」"
                        f"置信度 {r.get('confidence')}，方式 {r.get('method')}")
                elif reason == REASON_ENTITY_MISSING:
                    add(f"- `{reason}` — task_description 为空，命名回退到文件名")
                elif reason == REASON_NAME_BAD:
                    add(f"- `{reason}` — {r.get('suggested_name') or r.get('name_error')}")
            add("")
    else:
        add("无失败案例。")
        add("")

    add("## 五、模块接缝观察")
    add("")
    add("联调的核心目的不是单模块指标，而是模块之间的传递是否有断裂。以下为本次观测：")
    add("")
    ph_rows = [r for r in details if r.get("name_blocking_placeholders")]
    add(f"1. **命名依赖上游字段** — {len(ph_rows)}/{s['named']} 份生成的文件名缺必需字段。"
        "`Classifier` 不返回 `course_name`（规则命中与 LLM 兜底两条路均硬编码 None），"
        "`Namer` 只能取 `EntityExtractor` 的 `course_name`。"
        "对竞赛/大创/行政通知，两者都缺 —— 因为这类文件本就没有课程名。"
        "本次已让 `Namer` 回退取 `extra_entities` 里的主办方补位。"
        "**但 `Classifier.course_name` 恒为 None 这一点仍待确认是否要真正实现。**")
    add(f"2. **task_description 是命名的关键输入** — 缺失时 `Namer` 回退用文件名（`path.stem`），"
        "生成的名字虽格式合规但等于没有重命名。")
    add(f"3. **解析质量决定上限** — PDF 乱码 {s['cid_garbled']} 份。"
        "感知层提取出 `(cid:XXXX)` 时，后续分类/抽取/里程碑全部拿不到可用文本，"
        "属于感知层问题（非理解层可修）。")
    add("4. **LLM 空响应会让整条链失效** — 分类返回置信度 0.00 即走到「重试后仍失败」"
        "兜底分支，直接返回「待确认」。此时若真实类别恰为「待确认」会被误记为正确，"
        "使准确率虚高。实体抽取重试已从 2 次加固到 3 次、`max_tokens` 提至 4000，"
        "并要求 `extra_entities` 保持扁平以免 JSON 被截断。")
    add("")

    add("## 六、样本集与已知局限")
    add("")
    for line in manifest.get("_selection_criteria", []):
        add(f"- {line}")
    add("")
    add(f"> ⚠️ **{manifest.get('_known_limitation', '')}**")
    add("")
    if missing:
        add(f"本次运行有 {len(missing)} 份清单样本在磁盘上未找到：")
        add("")
        for m in missing:
            add(f"- `{m}`")
        add("")

    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------
# pytest 入口（CI 默认跳过：pytest -m "not e2e"）
# ----------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="需要 LLM_API_KEY，见 .env")
def test_pipeline_e2e(tmp_path: Path) -> None:
    """W4 联调：五模块串联跑通，且每份样本都产出合法命名。"""
    samples, _ = resolve_samples()
    if not samples:
        pytest.skip(f"清单样本在 {DATASETS_DIR} 下均未找到")

    result = run_pipeline_e2e(output_dir=tmp_path)

    assert result["parsed"] > 0, "没有任何样本解析成功"
    # 解析成功的样本必须都能走完 pipeline 并产出格式合法的命名
    assert result["name_format_rate"] == 100.0, (
        f"命名格式合规率 {result['name_format_rate']}%，存在不合规命名"
    )
    assert result["report_path"].exists()
    assert result["json_path"].exists()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="W4 联调测试并生成报告")
    ap.add_argument("--verbose", "-v", action="store_true", default=True,
                    help="打印逐份明细（手动运行默认开启）")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出错误")
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="输出目录，默认报告写 docs/、JSON 写项目根")
    args = ap.parse_args()
    try:
        run_pipeline_e2e(output_dir=args.output_dir, verbose=not args.quiet)
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
