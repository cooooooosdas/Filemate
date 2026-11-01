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
from filemate.core.session import ProcessingSession, SessionStatus


@pytest.fixture(autouse=True)
def _fake_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")


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


def test_generate_name_passes_organizer_to_namer(tmp_path: Path) -> None:
    """竞赛通知没有课程名时，网站流水线应让主办方补位。"""
    captured: dict = {}

    class _Namer:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return "[iCAN大赛组委会]-[竞赛通知]-[AI-OPC超级个体挑战赛]-[0831]-[待处理]"

    class _Storage:
        def log_operation(self, *args, **kwargs):
            return None

    stages = main_mod._make_stages(
        parser=object(),
        classifier=object(),
        extractor=object(),
        detector=object(),
        namer=_Namer(),
        calendar=object(),
        archiver=object(),
        storage=_Storage(),
        llm_client=object(),
        skip_calendar=True,
    )
    generate_name = next(stage for stage in stages if stage.__name__ == "generate_name")
    session = ProcessingSession(
        session_id="naming-test",
        source_path=str(tmp_path / "通知.pdf"),
        category="竞赛通知",
        entities={
            "course_name": None,
            "task_description": "AI-OPC超级个体挑战赛",
            "deadline": "2026-08-31",
            "extra_entities": {"organizer": "iCAN大学生创新创业大赛组织委员会"},
        },
    )

    generate_name(session)

    assert captured["course"] == ""
    assert captured["extra_entities"]["organizer"].startswith("iCAN")
    assert session.suggested_name.startswith("[iCAN大赛组委会]")


def test_process_single_releases_its_storage_connection(monkeypatch, tmp_path: Path) -> None:
    """每次处理都新建 storage 实例，返回前必须关闭，否则句柄与 WAL 锁会累积。"""
    created: list = []
    real_storage = main_mod.SQLiteStorage

    class TrackingStorage(real_storage):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(main_mod, "SQLiteStorage", TrackingStorage)
    bad = tmp_path / "讲义.xyz"
    bad.write_bytes(b"garbage")

    asyncio.run(main_mod.process_single(str(bad), db_path=str(tmp_path / "db.db")))

    assert created, "process_single 应当创建独立 storage"
    assert all(not instance._connections for instance in created)
