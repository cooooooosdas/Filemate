"""FileMate 命令行入口（W4 里程碑：单文件端到端）。

用法::

    python main.py <file_path> [--watch-dir <dir>]

选项:
    --watch-dir    watchdog 监控目录（会持续运行直到 Ctrl+C）
    --no-calendar  跳过 .ics 生成

TODO(架构):
    1. 当前阶段链在 main.py 中硬编码，后续应迁移到 PipelineWorker 类
    2. 各模块初始化在 process_single 中，未来可抽象为工厂模式
    3. watch 模式使用 asyncio，但 UI 层采用同步接口，需统一架构
    4. 后续确认层需在此处添加用户确认后的归档逻辑
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

# Windows GBK 控制台 + 中文输出兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass

from filemate.core.session import ProcessingSession, SessionStatus
from filemate.execution.archiver import Archiver
from filemate.execution.file_ops import FileOps
from filemate.execution.scheduler import CalendarBuilder, CalendarEvent
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient, LLMConfig
from filemate.perception import FileParser
from filemate.perception.chart_parser import ChartParser
from filemate.perception.ocr import OCRBackend
from filemate.perception.table_reader import TableReader
from filemate.understanding import Classifier, EntityExtractor, MilestoneDetector, Namer

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

    # 阶段 1：解析文件（图片型 PDF 自动 OCR 回退）
    _ocr = OCRBackend()  # 全局单例，懒加载
    _table_reader = TableReader()
    _chart_parser = ChartParser()

    def parse(session: ProcessingSession) -> ProcessingSession:
        source = session.source_path
        parsed = parser.parse(source)
        raw_text = parsed.get("raw_text", "")
        meta = parsed.get("metadata", {})

        # 空文本 + 图片型 PDF → 尝试 OCR
        if not raw_text.strip() and meta.get("suffix") == "pdf" and meta.get("text_pages", 1) == 0:
            if _ocr.available:
                logger.info("[%s] 图片型 PDF，启动 OCR: %s", session.session_id, Path(source).name)
                raw_text = _ocr.recognize(source)
                if raw_text.strip():
                    logger.info("[%s] OCR 成功，识别 %d 字", session.session_id, len(raw_text))
                else:
                    logger.warning("[%s] OCR 未识别到文字", session.session_id)
            else:
                logger.info("[%s] 图片型 PDF，OCR 不可用（PaddleOCR 未安装），跳过", session.session_id)

        # 提取表格 → Markdown 追加到 raw_text
        try:
            tables = _table_reader.extract_tables(source)
            if tables:
                table_md = "\n\n".join(
                    t.to_markdown() for t in tables if t.to_markdown()
                )
                if table_md:
                    raw_text += f"\n\n--- 表格数据 ---\n{table_md}"
                    meta["tables"] = len(tables)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] 表格提取失败: %s", session.session_id, exc)

        # 提取图表 → 文本追加到 raw_text
        try:
            charts = _chart_parser.extract_charts(source)
            if charts:
                chart_lines = []
                for ch in charts:
                    if ch.title:
                        chart_lines.append(f"图表: {ch.title}")
                    if ch.description:
                        chart_lines.append(f"说明: {ch.description}")
                    for el in ch.to_task_elements():
                        if el.get("text"):
                            chart_lines.append(f"  - {el['text']}")
                if chart_lines:
                    raw_text += "\n\n--- 图表数据 ---\n" + "\n".join(chart_lines)
                    meta["charts"] = len(charts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] 图表提取失败: %s", session.session_id, exc)

        session.entities["raw_text"] = raw_text
        session.entities["metadata"] = meta
        storage.log_operation(session.session_id, "parse", source)
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

    # 阶段 6：只生成日历预览；真正写盘与归档由确认执行器原子完成
    if not skip_calendar:
        def calendar_(session: ProcessingSession) -> ProcessingSession:
            events: list[dict[str, str]] = []
            for m in session.milestones:
                events.append(
                    {
                        "summary": f"[{session.category}] {m.get('event', '')}",
                        "start": m.get("date", ""),
                        "description": f"来源: {Path(session.source_path).name}",
                    }
                )
            session.entities["calendar_enabled"] = True
            session.entities["calendar_preview"] = events
            storage.log_operation(
                session.session_id,
                "calendar_preview",
                f"{len(events)} events",
            )
            return session
        calendar_.__name__ = "calendar"  # type: ignore[attr-defined]
        stages.append(calendar_)
    else:
        def disable_calendar(session: ProcessingSession) -> ProcessingSession:
            session.entities["calendar_enabled"] = False
            session.entities["calendar_preview"] = []
            return session
        disable_calendar.__name__ = "calendar_disabled"  # type: ignore[attr-defined]
        stages.append(disable_calendar)

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
    p.add_argument("--check", action="store_true",
                   help="环境检查模式：验证各模块可导入、Schema 可初始化、.ics 可生成（不处理真实文件）")
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
    storage.init_schema()  # 初始化数据库表
    archiver = Archiver(Path.cwd() / "archive", file_ops)

    # 构造 session
    session_id = uuid.uuid4().hex[:12]
    session = ProcessingSession(session_id=session_id, source_path=path)
    storage.create_session(session_id, path)

    # 运行阶段链
    session.transition(SessionStatus.PROCESSING)
    stages = _make_stages(
        parser, classifier, extractor, detector, namer,
        calendar, archiver, storage, llm,
        skip_calendar=skip_calendar,
    )
    for stage in stages:
        try:
            session = stage(session)
        except Exception as exc:  # noqa: BLE001 - 阶段边界必须收敛第三方异常
            session.error = f"{getattr(stage, '__name__', 'unknown')} 失败: {exc}"
            session.transition(SessionStatus.FAILED)
            logger.error("[%s] 阶段失败: %s", session.session_id, session.error)
            break

    # 终态
    if session.status == SessionStatus.PROCESSING:
        session.transition(SessionStatus.DONE)

    session_dict = session.to_dict()
    # update_session 只接受部分字段，过滤 + 序列化复杂类型
    _allowed = {"status", "category", "confidence", "suggested_name",
                "entities", "milestones", "error", "user_modified"}
    filtered = {}
    for k, v in session_dict.items():
        if k not in _allowed:
            continue
        if isinstance(v, (dict, list)):
            filtered[k] = json.dumps(v, ensure_ascii=False)
        else:
            filtered[k] = v
    storage.update_session(session_id, **filtered)
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
        storage.init_schema()  # 初始化数据库表

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

    # check 模式 — 仅验证执行层模块
    if args.check:
        ok = _run_check(args.db)
        sys.exit(0 if ok else 1)

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
    except Exception as exc:
        print(f"\n❌ 处理失败：{exc}")
        logger.exception("处理失败: %s", path)
        sys.exit(1)

    print("\n=== 处理结果 ===")
    print(f"  文件:      {session.source_path}")
    print(f"  分类:      {session.category}（置信度 {session.confidence:.0%}）")
    if session.entities.get("course_name"):
        print(f"  课程:      {session.entities['course_name']}")
    if session.entities.get("task_description"):
        print(f"  任务:      {session.entities['task_description']}")
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
    print(f"  状态:      {'[OK] 处理完成' if not session.error else '[FAIL] 处理失败'}")


def _run_check(db_path: str) -> bool:
    """环境检查模式：验证执行层各模块可正常初始化和运行。"""
    import tempfile

    print("FileMate 环境检查")
    print("=" * 40)

    all_ok = True

    # 1. SQLiteStorage 初始化 + Schema
    print("\n[1/5] SQLiteStorage ...", end=" ")
    try:
        storage = SQLiteStorage(db_path)
        storage.init_schema()
        sid = "check-test"
        storage.create_session(sid, "/check/test.docx")
        storage.update_session(sid, status="done", category="课件", confidence=0.9)
        row = storage.get_session(sid)
        assert row is not None and row["category"] == "课件"
        print("OK")
    except Exception as exc:  # noqa: BLE001 - 自检需汇总所有模块错误
        print(f"FAIL: {exc}")
        all_ok = False

    # 2. FileOps 基本操作
    print("[2/5] FileOps ...", end=" ")
    try:
        ops = FileOps()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.txt"
            p.write_text("hello")
            h = ops.compute_hash(p)
            assert len(h) == 64
            res = ops.copy(p, Path(td) / "copy.txt")
            assert res.success
            res = ops.rename(Path(td) / "copy.txt", "renamed.txt")
            assert res.success
            res = ops.delete(Path(td) / "renamed.txt")
            assert res.success
        print("OK")
    except Exception as exc:  # noqa: BLE001 - 自检需汇总所有模块错误
        print(f"FAIL: {exc}")
        all_ok = False

    # 3. CalendarBuilder .ics 生成
    print("[3/5] CalendarBuilder ...", end=" ")
    try:
        cal = CalendarBuilder()
        events = [
            CalendarEvent(summary="大创申报截止", start="2026-09-15", location="线上"),
            CalendarEvent(summary="中期检查", start="2026-12-01T14:00"),
        ]
        data = cal.build(events)
        assert b"BEGIN:VCALENDAR" in data
        assert b"SUMMARY:" in data
        print("OK")
    except Exception as exc:  # noqa: BLE001 - 自检需汇总所有模块错误
        print(f"FAIL: {exc}")
        all_ok = False

    # 4. Archiver
    print("[4/5] Archiver ...", end=" ")
    try:
        ops2 = FileOps()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "archive"
            archiver = Archiver(base, ops2)
            src = Path(td) / "hw.docx"
            src.write_text("第三章习题")
            result = archiver.archive("chk-1", "作业", "操作系统", "[操作系统]-[作业]-[习题].docx", src)
            assert result.success
            dest = base / "操作系统" / "作业" / "[操作系统]-[作业]-[习题].docx"
            assert dest.exists()
        print("OK")
    except Exception as exc:  # noqa: BLE001 - 自检需汇总所有模块错误
        print(f"FAIL: {exc}")
        all_ok = False

    # 5. operation_log 写入（新签名兼容）
    print("[5/5] operation_log ...", end=" ")
    try:
        storage.log_operation(sid, "classify", "课件 0.9",
                              input_snapshot='{"category":"课件","confidence":0.9}',
                              model_used="step-3.7-speed",
                              latency_ms=1200)
        ops_log = storage.get_operations(sid)
        assert len(ops_log) >= 1
        # 验证新字段存在
        latest = ops_log[-1]
        assert latest.get("input_snapshot") is not None or "input_snapshot" in str(ops_log)
        print("OK")
    except Exception as exc:  # noqa: BLE001 - 自检需汇总所有模块错误
        print(f"FAIL: {exc}")
        all_ok = False

    # clean
    storage.close()
    Path(db_path).unlink(missing_ok=True)

    print()
    print("=" * 40)
    if all_ok:
        print("[PASS] 环境检查全部通过 — 执行层对接正常")
    else:
        print("[FAIL] 存在未通过项，见上方详情")
    return all_ok


if __name__ == "__main__":
    main()
