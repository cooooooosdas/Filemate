"""从持久化回答生成透明的复盘报告。"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
from html import escape
from pathlib import Path
from typing import Any

from filemate.interview_review.models import CONTENT_LABELS, VISUAL_LABELS
from filemate.study.explanation_cycle import describe_answer_structure

_PDF_FONT_LOCK = threading.Lock()


def evidence_digest(interview: dict[str, Any]) -> str:
    """计算影响报告的原始记录摘要。"""
    payload = {key: interview[key] for key in (
        "interview_id", "target_role", "scenario", "status", "questions", "turns",
    )}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_report(interview: dict[str, Any]) -> dict[str, Any]:
    """合并内容、节奏和视觉观察，不生成无样本的能力判断。"""
    turns, timeline, concerns = [], [], []
    durations, paces, fillers, pauses = [], [], 0, 0
    visual_samples, face_samples, dim_samples = 0, 0, 0
    for turn in interview["turns"]:
        fluency = turn.get("fluency_metrics") or {}
        visual = turn.get("visual_metrics") or {}
        analysis = turn.get("content_analysis") or {}
        metrics = fluency if fluency.get("source") == "speech_recognition" else {}
        if metrics.get("duration_seconds", 0) >= 2:
            durations.append(metrics["duration_seconds"])
            paces.append(metrics.get("chars_per_minute", 0))
            fillers += metrics.get("filler_count", 0)
            pauses += metrics.get("long_pause_count", 0)
        visual_valid = visual.get("source") == "mediapipe_local_v1"
        if visual_valid:
            visual_samples += visual.get("sample_count", 0)
            face_samples += visual.get("face_samples", 0)
            dim_samples += visual.get("low_light_samples", 0)
            for event in visual.get("events", []):
                timeline.append({
                    "question_index": turn["question_index"], "start": event["start"],
                    "end": event["end"], "kind": event["kind"],
                    "label": VISUAL_LABELS.get(event["kind"], "可观察动作"),
                    "timebase": visual.get("timeline_origin", "visual"),
                })
        for marker in metrics.get("markers", []):
            offset = metrics.get("recording_offset_seconds")
            aligned = offset is not None
            second = marker["second"] + (offset if aligned else 0)
            timeline.append({
                "question_index": turn["question_index"], "start": round(second, 2),
                "end": round(second, 2), "kind": marker["kind"], "label": marker["label"],
                "timebase": "recording" if aligned else "speech",
            })
        for key, item in analysis.get("areas", {}).items():
            if item.get("status") in {"missing", "partial"}:
                concerns.append({
                    "question_index": turn["question_index"], "area": CONTENT_LABELS[key],
                    "evidence": item.get("evidence", ""), "suggestion": item["suggestion"],
                    "source": "model_reference",
                })
        turns.append({
            "turn_id": turn["turn_id"], "question_index": turn["question_index"],
            "question": turn["question"], "answer": turn["answer"],
            "score": turn["score"], "scoring_mode": turn["scoring_mode"],
            "feedback": turn["feedback"], "content_analysis": analysis,
            "structure": describe_answer_structure(turn["answer"]),
            "fluency": metrics, "visual": visual if visual_valid else {},
            "data_error": bool(turn.get("analysis_data_error")),
        })
    timeline.sort(key=lambda e: (e["question_index"], e["timebase"], e["start"]))
    return {
        "version": "2.4", "interview_id": interview["interview_id"],
        "target_role": interview["target_role"], "scenario": interview["scenario"],
        "status": interview["status"], "answered": len(turns), "total": len(interview["questions"]),
        "assessed": interview["assessed_turn_count"], "overall_score": interview["overall_score"],
        "calibration": "待校准（没有真实专家评分样本）",
        "purpose": "用于训练和复盘，模型评分是参考，不用于录用决定或心理状态推断。",
        "expression": {
            "speech_turns": len(durations), "duration_seconds": round(sum(durations), 2),
            "chars_per_minute": round(sum(
                duration * pace for duration, pace in zip(durations, paces, strict=True)
            ) / sum(durations), 2) if durations else None,
            "filler_count": fillers if durations else None,
            "long_pause_count": pauses if durations else None,
            "method": "浏览器识别回调间隔和文本口头语计数；不是音频静音检测或医学卡顿诊断。",
        },
        "visual": {
            "sample_count": visual_samples,
            "face_observed_ratio": round(face_samples / visual_samples, 3) if visual_samples else None,
            "low_light_ratio": round(dim_samples / visual_samples, 3) if visual_samples else None,
            "method": "本机MediaPipe采样与亮度阈值；比例只描述采样结果，不代表准确率。",
        },
        "turns": turns, "timeline": timeline, "review_focus": concerns,
        "suggestions": [
            "选一题对照原资料核对定义、条件和例子；关键词出现不等于知识正确。",
            "回看有时间证据的位置，尝试按情境、任务、行动、结果重新组织经历。",
        ] + (["部分采样画面亮度较低，视觉观察可信度可能下降。"] if dim_samples else []),
        "privacy": {
            "video": "录像仅存当前浏览器页面内存；不上传，刷新或删除后清除。",
            "records": "回答、节奏、观察摘要和报告保存在本地SQLite，可单独清空分析或删除练习。",
            "external": "只有主动授权的回答内容分析会外发问题、回答和目标方向；不发送音视频和人脸点。供应商保存策略需另行核对。",
            "speech": "语音识别由浏览器提供，可能使用浏览器厂商在线服务；文本输入不需要语音外发。",
        },
    }


def report_markdown(report: dict[str, Any]) -> str:
    """导出保留原句、数据来源和缺失说明的Markdown。"""
    lines = ["# FileMate 面试复盘报告", "", f"方向：{report['target_role']}",
             f"场景：{report['scenario']}", f"已回答：{report['answered']} / {report['total']}",
             f"内容已评估：{report['assessed']}题", f"校准状态：{report['calibration']}",
             "", report["purpose"], "", "## 表达与停顿", "",
             f"有语音证据：{report['expression']['speech_turns']}题",
             f"语速：{report['expression']['chars_per_minute'] if report['expression']['chars_per_minute'] is not None else '待评测'} 字/分钟",
             f"口头语：{report['expression']['filler_count'] if report['expression']['filler_count'] is not None else '待评测'}",
             f"较长回调间隔：{report['expression']['long_pause_count'] if report['expression']['long_pause_count'] is not None else '待评测'}",
             report["expression"]["method"], "", "## 面部可观察行为", "",
             f"有效采样：{report['visual']['sample_count']}；检出比例：{report['visual']['face_observed_ratio'] if report['visual']['face_observed_ratio'] is not None else '待评测'}",
             report["visual"]["method"], "", "## 回答与专业内容", ""]
    for turn in report["turns"]:
        lines.extend([f"### 第{turn['question_index'] + 1}题", "", turn["question"], "",
                      "回答：", "", turn["answer"], "", f"来源：{turn['scoring_mode']}",
                      f"评分：{turn['score'] if turn['score'] is not None else '待评估'}", turn["feedback"],
                      "表达线索：" + ("、".join(turn["structure"]["cues"]) or "未观察到预设线索")])
        for key, item in turn["content_analysis"].get("areas", {}).items():
            lines.extend([f"{CONTENT_LABELS[key]}：{item['status']}（模型参考）",
                          f"原句证据：{item['evidence'] or '无，属于缺失项建议'}", item["suggestion"]])
        if turn["content_analysis"].get("keywords"):
            lines.append("原回答关键词：" + "、".join(turn["content_analysis"]["keywords"]))
        if turn["data_error"]:
            lines.append("部分分析数据损坏，已跳过；原回答保留。")
        lines.append("")
    lines.extend(["## 时间轴", ""])
    for event in report["timeline"]:
        lines.append(f"第{event['question_index'] + 1}题 / {event['timebase']} / "
                     f"{event['start']:.1f}-{event['end']:.1f}秒：{event['label']}")
    if not report["timeline"]:
        lines.append("没有采集时间证据，待评测。")
    lines.extend(["", "## 薄弱项与建议", ""])
    for focus in report["review_focus"]:
        lines.append(f"第{focus['question_index'] + 1}题 {focus['area']}（模型待核对）：{focus['suggestion']}")
    if not report["review_focus"]:
        lines.append("内容薄弱知识点待评估，不由回答长度或面部动作推断。")
    lines.extend(report["suggestions"] + ["", "## 隐私与保存", "", *report["privacy"].values()])
    return "\n".join(lines) + "\n"


def report_pdf(report: dict[str, Any]) -> bytes:
    """以嵌入中文字体生成可下载、可分页的本地PDF。"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_name = "FileMateNotoSC"
    with _PDF_FONT_LOCK:
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, str(
                Path(__file__).parent / "assets" / "NotoSansSC-Regular.ttf",
            )))
    stream = io.BytesIO()
    body = ParagraphStyle("body", fontName=font_name, fontSize=10, leading=16,
                          wordWrap="CJK", spaceAfter=6, textColor=colors.HexColor("#183229"))
    styles = {1: ParagraphStyle("h1", parent=body, fontSize=20, leading=28, spaceAfter=16, keepWithNext=True),
              2: ParagraphStyle("h2", parent=body, fontSize=14, leading=21, spaceBefore=12, keepWithNext=True),
              3: ParagraphStyle("h3", parent=body, fontSize=12, leading=18, spaceBefore=8, keepWithNext=True)}
    story = []
    after_heading = False
    for line in report_markdown(report).splitlines():
        if not line:
            if not after_heading:
                story.append(Spacer(1, 4))
            continue
        heading = re.match(r"^(#{1,3}) (.*)$", line)
        story.append(Paragraph(escape(heading[2] if heading else line),
                               styles[len(heading[1])] if heading else body))
        after_heading = bool(heading)

    def footer(canvas, document):
        canvas.setFont(font_name, 9)
        canvas.setFillColor(colors.HexColor("#4D655B"))
        canvas.drawString(42, 26, "FileMate / 本地面试训练复盘")
        canvas.drawRightString(A4[0] - 42, 26, str(document.page))

    SimpleDocTemplate(stream, pagesize=A4, leftMargin=42, rightMargin=42,
                      topMargin=42, bottomMargin=42, title="FileMate 面试复盘报告").build(
                          story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
