"""面试观察的有限数据合同。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VISUAL_LABELS = {
    "no_face": "未检测到稳定人脸",
    "low_light": "画面亮度偏低",
    "head_turn": "头部朝向偏离正面",
    "head_pose_change": "头部姿态变化",
    "smile_change": "嘴角动作变化",
    "look_direction_change": "眼部方向系数变化",
}


class VisualEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal[
        "no_face", "low_light", "head_turn", "head_pose_change",
        "smile_change", "look_direction_change",
    ]
    start: float = Field(ge=0, le=1800)
    end: float = Field(ge=0, le=1800)


class VisualMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: Literal["mediapipe_local_v1"]
    timeline_origin: Literal["recording", "visual"]
    duration_seconds: float = Field(ge=0, le=1800)
    sample_count: int = Field(ge=0, le=3604)
    face_samples: int = Field(ge=0, le=3604)
    low_light_samples: int = Field(ge=0, le=3604)
    dropped_samples: int = Field(default=0, ge=0, le=3604)
    events: list[VisualEvent] = Field(default_factory=list, max_length=200)
    events_truncated: bool = False

    @model_validator(mode="after")
    def validate_observations(self):
        """拒绝不可能的计数和超出采集区间的时间点。"""
        if max(self.face_samples, self.low_light_samples) > self.sample_count:
            raise ValueError("观察样本计数不一致")
        if self.sample_count > self.duration_seconds * 2 + 4:
            raise ValueError("观察采样频率超过约定")
        for event in self.events:
            if event.start > event.end or event.end > self.duration_seconds:
                raise ValueError("观察时间超出录像区间")
        return self


CONTENT_AREAS = ("completeness", "logic", "technical_coverage", "technical_expression", "relevance", "star")
CONTENT_LABELS = {
    "completeness": "回答完整度", "logic": "逻辑结构",
    "technical_coverage": "专业知识覆盖", "relevance": "问题相关性", "star": "STAR结构",
    "technical_expression": "技术表达",
}


def validate_content_analysis(data: dict, answer: str) -> dict:
    """核对模型引用确实来自原回答，不把参考建议当成客观结论。"""
    if not isinstance(data, dict) or set(data) != set(CONTENT_AREAS):
        raise ValueError("内容分析字段缺失")
    result = {}
    for key in CONTENT_AREAS:
        item = data[key]
        if not isinstance(item, dict):
            raise TypeError("内容分析格式错误")
        status = item.get("status")
        evidence, suggestion = item.get("evidence"), item.get("suggestion")
        if status not in {"covered", "partial", "missing", "not_applicable"}:
            raise ValueError("未知内容状态")
        if not isinstance(evidence, str) or len(evidence) > 500:
            raise ValueError("证据格式错误")
        if evidence and evidence not in answer:
            raise ValueError("模型引用不属于回答")
        if status in {"covered", "partial"} and not evidence.strip():
            raise ValueError("肯定性评价缺少原句")
        if not isinstance(suggestion, str) or not 1 <= len(suggestion) <= 1000:
            raise ValueError("改进建议缺失")
        result[key] = {"status": status, "evidence": evidence, "suggestion": suggestion}
    return result


def validate_saved_analysis(data: dict, answer: str) -> dict:
    """重新核对持久化引用，避免损坏记录被报告当成证据。"""
    if data.get("source") != "llm_reference":
        raise ValueError("unknown content analysis")
    areas = validate_content_analysis(data.get("areas"), answer)
    dimensions = data.get("dimension_evidence")
    if (not isinstance(dimensions, dict)
            or set(dimensions) != {"内容", "结构", "表达", "岗位匹配"}
            or not all(isinstance(v, str) and v.strip() and len(v) <= 500 and v in answer
                       for v in dimensions.values())):
        raise ValueError("维度引用不属于原回答")
    keywords = data.get("keywords")
    if (not isinstance(keywords, list) or len(keywords) > 20
            or not all(isinstance(k, str) and k.strip() and len(k) <= 40 and k in answer
                       for k in keywords)):
        raise ValueError("关键词不属于原回答")
    return {"source": "llm_reference", "areas": areas, "dimension_evidence": dimensions,
            "keywords": list(dict.fromkeys(keywords))}
