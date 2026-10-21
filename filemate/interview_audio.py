"""Bounded device-reported audio evidence, independent of competence scoring."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AudioSummary(EvidenceModel):
    method: Literal["web_audio_energy_v1"]
    duration_seconds: float = Field(gt=0, le=600.1)
    sample_rate: int = Field(ge=8000, le=96000)
    sample_count: int = Field(ge=1, le=57609600)
    rms: float = Field(ge=0, le=1.01)
    low_energy_seconds: float = Field(ge=0, le=600.1)
    clipping_ratio: float = Field(ge=0, le=1)
    threshold: Literal[0.01]

    @model_validator(mode="after")
    def consistent_samples(self) -> Self:
        if abs(self.sample_count / self.sample_rate - self.duration_seconds) > 0.02:
            raise ValueError("音频采样数与时长不一致")
        if self.low_energy_seconds > self.duration_seconds + 0.02:
            raise ValueError("低能量时长不能超过音频时长")
        return self


class AudioEvidence(EvidenceModel):
    status: Literal["measured", "unavailable"]
    summary: AudioSummary | None

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if (self.status == "measured") != (self.summary is not None):
            raise ValueError("音频摘要状态不一致")
        return self


class TranscriptSegment(EvidenceModel):
    text: str = Field(min_length=1, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    callback_seconds: float = Field(ge=0, le=600)


class TranscriptionEvidence(EvidenceModel):
    provider: Literal["browser_web_speech"]
    status: Literal["completed", "interrupted", "denied", "no_speech", "unsupported"]
    language: Literal["zh-CN", "en-US"]
    segments: list[TranscriptSegment] = Field(max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def normalize_confidence(self) -> Self:
        if sum(len(segment.text) for segment in self.segments) > 12000:
            raise ValueError("转写原文超长")
        if self.status in {"denied", "no_speech", "unsupported"} and self.segments:
            raise ValueError("无转写结果的状态不能包含原文")
        values = [s.confidence for s in self.segments if s.confidence is not None]
        self.confidence = sum(values) / len(values) if values else None
        return self


class MediaEvidence(EvidenceModel):
    source: Literal["browser_media_v1"]
    duration_seconds: float = Field(ge=0, le=600)
    audio: AudioEvidence | None
    transcription: TranscriptionEvidence | None

    @model_validator(mode="after")
    def has_evidence(self) -> Self:
        if self.audio is None and self.transcription is None:
            raise ValueError("至少需要一项音频或转写记录")
        return self
