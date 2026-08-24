"""main.process_single 编排层测试：解析失败必须标记 FAILED，不静默降级。

parse 失败发生在任何 LLM 调用之前，因此只需注入非空的假 LLM 配置让
LLMClient 能构造，验证点只落在「FileParser 的 error 被正确消费」上。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import main as main_mod
from filemate.core.session import SessionStatus


@pytest.fixture(autouse=True)
def _fake_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.stepfun.com/step_plan/v1")
    monkeypatch.setenv("LLM_MODEL", "step-3.7-flash")


def test_parse_failure_marks_session_failed(tmp_path: Path) -> None:
    """FileParser 报错（不支持格式）时，process_single 标记 FAILED 并携带 error。"""
    bad = tmp_path / "讲义.xyz"
    bad.write_bytes(b"garbage")
    db = tmp_path / "db.db"

    session = asyncio.run(main_mod.process_single(str(bad), db_path=str(db)))

    assert session.status == SessionStatus.FAILED
    assert session.error
    assert "不支持" in session.error or "解析" in session.error


def test_parse_failure_does_not_call_llm(tmp_path: Path) -> None:
    """parse 失败后阶段链中断，不进 classify，category 保持为空。"""
    bad = tmp_path / "课件.unknownext"
    bad.write_bytes(b"garbage")
    db = tmp_path / "db.db"

    session = asyncio.run(main_mod.process_single(str(bad), db_path=str(db)))

    assert session.status == SessionStatus.FAILED
    assert session.category == ""
    assert session.confidence == 0.0
