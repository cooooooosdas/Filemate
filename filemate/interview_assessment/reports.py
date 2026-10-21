"""Readable six-dimensional exports with original answers and missing-evidence explanations."""

import re
from html import escape


def _text(value: object) -> str:
    return re.sub(
        r"[\\`*_{}\[\]()#+.!|~>=-]", lambda match: f"&#{ord(match[0])};", escape(str(value))
    )


def markdown(report: dict) -> str:
    result, rubric, snap = report["result"], report["rubric"], report["input"]
    lines = [
        "# FileMate 六维面试训练报告",
        "",
        _text(report["purpose"]),
        "",
        f"岗位：{_text(snap['target_role'])}；场景：{_text(snap['scenario'])}",
        f"标准：{_text(rubric['id'])} / {_text(rubric['version'])}；校准：{_text(rubric['calibration'])}",
        f"整体参考：{result['overall_score'] if result['overall_score'] is not None else '待评测'}",
        f"有效权重：{result['weighting']['applied_weight']} / 100；{_text(result['weighting']['rule'])}",
        f"缺失核心维度：{_text(', '.join(result['core_missing']) or '无')}",
        "",
    ]
    for dim in result["dimensions"]:
        lines.extend(
            [
                f"## {_text(dim['name'])}",
                "",
                f"参考分：{dim['score'] if dim['score'] is not None else '待评测'}；权重：{dim['weight']}",
                f"依据说明：{_text(dim['reason'])}",
                f"下一步：{_text(dim['suggestion'])}",
                _text(dim["scope"]),
            ]
        )
        for evidence in dim["evidence"]:
            lines.extend(
                [
                    f"证据类型：{_text(evidence['kind'])}；回答版本ID：{_text(evidence['attempt_id'])}",
                    "原句：" + _text(evidence["quote"]),
                ]
            )
        lines.extend(
            ["标准锚点：" + _text("；".join(k + "：" + v for k, v in dim["anchors"].items())), ""]
        )
    lines.extend(["## 任务与互动时间轴", "", "互动事件由规则生成，非真实观众评价。"])
    for event in snap["events"]:
        lines.append(
            f"{_text(event['created_at'])}：{_text(event['text'])}；回答依据：{_text(event.get('attempt_id') or '未回应')}"
        )
    for task in snap["tasks"]:
        lines.append(
            f"{_text(task['title'])}：{_text(task['status'])}；回答依据：{_text(task.get('attempt_id') or '未作答')}"
        )
    lines.extend(["", "## 当前版本原回答", ""])
    for turn in snap["turns"]:
        lines.extend(
            [
                f"第{turn['question_index'] + 1}题 · 回答版本{turn.get('version')}",
                _text(turn["question"]),
                _text(turn["answer"]),
                "",
            ]
        )
    lines.extend(
        [
            "## 计算来源",
            "",
            f"评估ID：{_text(report['assessment_id'])}",
            f"生成时间：{_text(report['generated_at'])}",
            _text("; ".join(f"{key}={value}" for key, value in report["provenance"].items())),
            "原音视频不上传、不进入本报告；文字模型建议仍需本人核对。",
        ]
    )
    return "\n".join(lines)
