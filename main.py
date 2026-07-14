"""FileMate 命令行入口。用法: python main.py <file_path>"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from filemate.perception.file_parser import FileParser
from filemate.understanding import (
    Classifier,
    EntityExtractor,
    MilestoneDetector,
    Namer,
)
from filemate.execution.scheduler import CalendarBuilder, CalendarEvent
from filemate.core.session import ProcessingSession, SessionStatus


async def process(path: str) -> ProcessingSession:
    """TODO(胡希): W4 前组装成可运行的端到端流程。"""
    raise NotImplementedError("TODO(胡希): main.py 端到端组装")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <file_path>")
        sys.exit(1)
    path = sys.argv[1]
    if not Path(path).exists():
        print(f"文件不存在: {path}")
        sys.exit(1)
    session = asyncio.run(process(path))
    print(session.to_dict())


if __name__ == "__main__":
    main()
