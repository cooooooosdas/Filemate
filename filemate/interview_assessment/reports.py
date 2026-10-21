"""Readable six-dimensional exports with original answers and missing-evidence explanations."""


def markdown(report: dict) -> str:
    result, rubric, snap = report["result"], report["rubric"], report["input"]
    lines = [
        "# FileMate 六维面试训练报告",
        "",
        report["purpose"],
        "",
        f"岗位：{snap['target_role']}；场景：{snap['scenario']}",
        f"标准：{rubric['id']} / {rubric['version']}；校准：{rubric['calibration']}",
        f"整体参考：{result['overall_score'] if result['overall_score'] is not None else '待评测'}",
        f"有效权重：{result['weighting']['applied_weight']} / 100；{result['weighting']['rule']}",
        f"缺失核心维度：{', '.join(result['core_missing']) or '无'}",
        "",
    ]
    for dim in result["dimensions"]:
        lines.extend(
            [
                f"## {dim['name']}",
                "",
                f"参考分：{dim['score'] if dim['score'] is not None else '待评测'}；权重：{dim['weight']}",
                f"依据说明：{dim['reason']}",
                f"下一步：{dim['suggestion']}",
                dim["scope"],
            ]
        )
        for evidence in dim["evidence"]:
            lines.extend(
                [
                    f"证据类型：{evidence['kind']}；回答版本ID：{evidence['attempt_id']}",
                    "原句：" + evidence["quote"],
                ]
            )
        lines.extend(
            ["标准锚点：" + "；".join(k + "：" + v for k, v in dim["anchors"].items()), ""]
        )
    lines.extend(["## 任务与互动时间轴", "", "互动事件由规则生成，非真实观众评价。"])
    for event in snap["events"]:
        lines.append(
            f"{event['created_at']}：{event['text']}；回答依据：{event.get('attempt_id') or '未回应'}"
        )
    for task in snap["tasks"]:
        lines.append(
            f"{task['title']}：{task['status']}；回答依据：{task.get('attempt_id') or '未作答'}"
        )
    lines.extend(["", "## 当前版本原回答", ""])
    for turn in snap["turns"]:
        lines.extend(
            [
                f"第{turn['question_index'] + 1}题 · 回答版本{turn.get('version')}",
                turn["question"],
                turn["answer"],
                "",
            ]
        )
    lines.extend(
        [
            "## 计算来源",
            "",
            f"评估ID：{report['assessment_id']}",
            f"生成时间：{report['generated_at']}",
            "; ".join(f"{key}={value}" for key, value in report["provenance"].items()),
            "原音视频不上传、不进入本报告；文字模型建议仍需本人核对。",
        ]
    )
    return "\n".join(lines)
