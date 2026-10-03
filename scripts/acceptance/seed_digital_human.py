"""为数字人浏览器验收创建隔离的合成回答。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from filemate.execution.storage import SQLiteStorage


def main() -> None:
    """只向项目 _working 内的临时库写入合成会话。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    target = parser.parse_args().db.resolve()
    if not target.is_relative_to(PROJECT_ROOT / "_working"):
        parser.error("验收数据库必须位于项目 _working 目录内")
    target.parent.mkdir(parents=True, exist_ok=True)
    storage = SQLiteStorage(target)
    try:
        storage.init_schema()
        storage.save_document_context(
            ctx_id="v2-1-acceptance",
            context_text="合成工程回归资料，不是真实用户数据。",
            chat_history=[
                {"role": "assistant", "content": "合成测试回答一：前序遍历先访问根节点，再遍历左右子树。"},
                {"role": "assistant", "content": "合成测试回答二：中序遍历先遍历左子树，再访问根节点。"},
            ],
        )
    finally:
        storage.close()
    print("已准备隔离的合成测试回答。")


if __name__ == "__main__":
    main()
