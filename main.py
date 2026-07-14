"""FileMate 命令行入口（W4 里程碑：单文件端到端）。

用法::

    python main.py <file_path> [--watch-dir <dir>]

选项:
    --watch-dir    watchdog 监控目录（会持续运行直到 Ctrl+C）
    --no-calendar  跳过 .ics 生成
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from filemate.llm_client import LLMClient, LLMConfig
from filemate.perception import FileParser
from filemate.understanding import (
    Classifier,
    EntityExtractor,
    MilestoneDetector,
    Namer,
)
from filemate.execution.scheduler import CalendarBuilder, CalendarEvent
from filemate.execution.file_ops import FileOps, OpResult
from filemate.execution.archiver import Archiver
from filemate.execution.storage import SQLiteStorage
from filemate.core.session import ProcessingSession, SessionStatus
from filemate.core.pipeline import PipelineWorker

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  阶段函数工厂（将各模块包装成 PipelineWorker 接受的 StageFn）
# ──────────────────────────────────────────────

def _make_stages(
    parser: FileParser,
    classifier: Classifier,
    extractor: EntityExtractor,
    detector: MilestoneDetector,
    namer: Namer,
    calendar: CalendarBuilder,
    archiver: Archiver,
    storage: SQLiteStorage,
    llm_client: LLMClient,
    *,
    skip_calendar: bool = False,
) -> list:
    """构造阶段链，每个阶段是 (ProcessingSession) -> ProcessingSession。"""
    stages: list = []

    # 阶段 1：解析文件
    def parse(session: ProcessingSession) -> ProcessingSession:
        parsed = parser.parse(session.source_path)
        session.entities["raw_text"] = parsed.get("raw_text", "")
        session.entities["metadata"] = parsed.get("metadata", {})
        storage.log_operation(session.session_id, "parse", session.source_path)
        return session
    parse.__name__ = "parse"  # type: ignore[attr-defined]
    stages.append(parse)

    # 阶段 2：分类
    def classify(session: ProcessingSession) -> ProcessingSession:
        raw_text = session.entities.get("raw_text", "")
        filename = Path(session.source_path).name
        result = classifier.classify(raw_text, filename=filename)
        session.category = result.get("category", "待确认")
        session.confidence = float(result.get("confidence", 0.0))
        if result.get("course_name"):
            session.entities["course_name"] = result["course_name"]
        storage.log_operation(session.session_id, "classify",
                             f"{session.category}({session.confidence:.0%})")
        return session
    classify.__name__ = "classify"  # type: ignore[attr-defined]
    stages.append(classify)

    # 阶段 3：实体抽取
    def extract(session: ProcessingSession) -> ProcessingSession:
        raw_text = session.entities.get("raw_text", "")
        entities = extractor.extract(raw_text)
        session.entities.update(entities)
        storage.log_operation(session.session_id, "extract")
        return session
    extract.__name__ = "extract"  # type: ignore[attr-defined]
    stages.append(extract)

    # 阶段 4：多里程碑识别
    def detect(session: ProcessingSession) -> ProcessingSession:
        raw_text = session.entities.get("raw_text", "")
        milestones = detector.detect(raw_text)
        session.milestones = milestones
        storage.log_operation(session.session_id, "detect_milestones",
                             f"{len(milestones)} events")
        return session
    detect.__name__ = "detect_milestones"  # type: ignore[attr-defined]
    stages.append(detect)

    # 阶段 5：生成文件名
    def generate_name(session: ProcessingSession) -> ProcessingSession:
        course = session.entities.get("course_name") or "未分类"
        task = session.entities.get("task_description") or Path(session.source_path).stem
        deadline = session.entities.get("deadline") or ""
        suggested = namer.generate(
            category=session.category,
            course=course,
            task=task,
            deadline=deadline,
            status="待处理",
        )
        session.suggested_name = suggested
        storage.log_operation(session.session_id, "name", suggested)
        return session
    generate_name.__name__ = "generate_name"  # type: ignore[attr-defined]
    stages.append(generate_name)

    # 阶段 6：日历
    if not skip_calendar:
        def calendar_(session: ProcessingSession) -> ProcessingSession:
            events = []
            for m in session.milestones:
                events.append(CalendarEvent(
                    summary=f"[{session.category}] {m.get('event', '')}",
                    start=m.get("date", ""),
                    description=f"来源: {Path(session.source_path).name}",
                ))
            if events:
                out = Path(session.source_path).with_suffix(".ics")
                calendar.save(events, out)
                session.entities["ics_path"] = str(out)
                storage.log_operation(session.session_id, "calendar", str(out))
            return session
        calendar_.__name__ = "calendar"  # type: ignore[attr-defined]
        stages.append(calendar_)

    # 阶段 7：归档（用户确认后才真正移动，此处只做预览）
    # 实际移动逻辑在确认层，此处留空占位

    return stages


# ──────────────────────────────────────────────
#  watch 模式
# ──────────────────────────────────────────────

async def _watch_loop(
    watch_dir: str | Path,
    processor,
    storage: SQLiteStorage,
    *,
    poll_interval: float = 2.0,
) -> None:
    """轮询监控目录，新文件入队。"""
    watched = Path(watch_dir)
    watched.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    logger.info("watch 模式启动，监控目录: %s（每 %.1fs 轮询）", watched, poll_interval)
    print(f"[watch] 监控目录: {watched}  （Ctrl+C 退出）")
    while True:
        for p in watched.iterdir():
            if p.is_file() and p.name not in seen and FileOps.is_supported(p):
                seen.add(p.name)
                session_id = uuid.uuid4().hex[:12]
                session = ProcessingSession(session_id=session_id, source_path=str(p))
                storage.create_session(session_id, str(p))
                logger.info("[watch] 新文件: %s (session=%s)", p.name, session_id)
                print(f"[watch] 新文件: {p.name}")
                await processor(session)
        await asyncio.sleep(poll_interval)


# ──────────────────────────────────────────────
#  main
# ──────────────────────────────────────────────

def _build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FileMate — 课程文件智能归档")
    p.add_argument("path", nargs="?", help="待处理文件路径")
    p.add_argument("--watch-dir", help="watchdog 监控目录（持续运行）")
    p.add_argument("--no-calendar", action="store_true", help="跳过 .ics 生成")
    p.add_argument("--db", default="filemate.db", help="SQLite 路径（默认 filemate.db）")
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG 日志")
    return p.parse_args()


async def process_single(
    path: str,
    *,
    skip_calendar: bool = False,
    db_path: str = "filemate.db",
) -> ProcessingSession:
    """处理单个文件的完整流程（供 CLI 和测试调用）。"""
    # 初始化各模块
    llm_config = LLMConfig.from_env()
    llm = LLMClient(llm_config)
    parser = FileParser()
    classifier = Classifier(llm)
    extractor = EntityExtractor(llm)
    detector = MilestoneDetector(llm)
    namer = Namer(llm)
    calendar = CalendarBuilder()
    file_ops = FileOps()
    storage = SQLiteStorage(db_path)
    archiver = Archiver(Path(".").resolve() / "archive", file_ops)

    # 构造 session
    session_id = uuid.uuid4().hex[:12]
    session = ProcessingSession(session_id=session_id, source_path=path)
    storage.create_session(session_id, path)

    # 运行阶段链
    stages = _make_stages(
        parser, classifier, extractor, detector, namer,
        calendar, archiver, storage, llm,
        skip_calendar=skip_calendar,
    )
    for stage in stages:
        session = stage(session)
        if session.status == SessionStatus.FAILED:
            break

    storage.update_session(session_id, **session.to_dict())
    return session


def main() -> None:
    args = _build_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # watch 模式
    if args.watch_dir:
        storage = SQLiteStorage(args.db)

        async def _processor(session: ProcessingSession) -> None:
            try:
                await process_single(
                    session.source_path,
                    skip_calendar=args.no_calendar,
                    db_path=args.db,
                )
            except Exception:
                logger.exception("处理失败: %s", session.source_path)

        try:
            asyncio.run(_watch_loop(args.watch_dir, _processor, storage))
        except KeyboardInterrupt:
            print("\n[watch] 已停止")
        return

    # 单文件模式
    if not args.path:
        print("Usage: python main.py <file_path> [--watch-dir <dir>]")
        sys.exit(1)
    path = Path(args.path)
    if not path.exists():
        print(f"文件不存在: {path}")
        sys.exit(1)

    try:
        session = asyncio.run(process_single(
            str(path),
            skip_calendar=args.no_calendar,
            db_path=args.db,
        ))
    except NotImplementedError as exc:
        print(f"\n⚠️  功能尚未实现：{exc}")
        print("请让对应成员按 TODO 标记完成：")
        print("  感知层 → 汤新阳 | 理解层 → 张金宝 | 执行层 → 徐书和")
        sys.exit(2)

    print("\n=== 处理结果 ===")
    print(f"  文件:      {session.source_path}")
    print(f"  分类:      {session.category}（置信度 {session.confidence:.0%}）")
    print(f"  建议名:    {session.suggested_name}")
    if session.entities.get("deadline"):
        print(f"  截止时间:  {session.entities['deadline']}")
    if session.milestones:
        print(f"  里程碑:    {len(session.milestones)} 个")
        for m in session.milestones:
            print(f"    - {m.get('date', '')} {m.get('event', '')}")
    ics = session.entities.get("ics_path")
    if ics:
        print(f"  日历文件:  {ics}")
    if session.error:
        print(f"  错误:      {session.error}")
    print(f"  session:   {session.session_id}")


if __name__ == "__main__":
    main()
