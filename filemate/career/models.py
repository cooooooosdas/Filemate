"""岗位导入与训练的有限合同。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=60)
    category: Literal["programming", "knowledge", "project", "communication"] = "knowledge"
    evidence: str = Field(min_length=1, max_length=400)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company: str = Field(min_length=1, max_length=80)
    industry: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=100)
    employment: Literal["校招", "实习", "社招参考", "用户自定义"] = "用户自定义"
    description: str = Field(min_length=10, max_length=12000)
    requirements: list[Requirement] = Field(min_length=1, max_length=30)
    source: str = Field(min_length=1, max_length=120)
    source_url: str = Field(default="", max_length=1000)
    source_kind: Literal["official_snapshot", "user_import"] = "user_import"
    collected_at: datetime
    published_at: str = Field(default="", max_length=40)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        """链接只供用户打开，不在服务端抓取。"""
        if value:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or any(c in value for c in "\r\n\t")
            ):
                raise ValueError("来源地址需为不含凭据的HTTPS链接")
        return value

    @model_validator(mode="after")
    def check_evidence(self):
        """保留明确的采集时间和岗位原句，拒绝无来源技能。"""
        if self.collected_at.tzinfo is None:
            raise ValueError("采集时间需包含时区")
        if self.collected_at > datetime.now(timezone.utc):
            raise ValueError("采集时间不能位于未来")
        labels = [item.label.casefold() for item in self.requirements]
        if len(set(labels)) != len(labels):
            raise ValueError("岗位要求重复")
        if any(item.evidence not in self.description for item in self.requirements):
            raise ValueError("每项要求须引用岗位描述原句")
        if self.source_kind == "official_snapshot" and not self.source_url:
            raise ValueError("官方快照缺少来源链接")
        return self


class PositionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: Position
    confirmed: bool = False
    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class PositionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: Position
    confirmed: bool = False
    expected_revision: int = Field(ge=1)


class TrainingStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["written", "interview", "review"]
    confirmed: bool = False
    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=1)


class WrittenAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, StrictInt] = Field(min_length=1, max_length=10)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False
    confirmation_token: str = Field(default="", max_length=64)
