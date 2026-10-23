"""Prepare original course documents and an isolated synthetic account offline."""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from filemate.accounts import AccountStore, validate_password
from filemate.execution.storage import SQLiteStorage

DOCUMENTS = {
    "数据结构-基础讲义-原创演示.txt": "栈：后进先出的线性表。队列：先进先出的线性表。树：分层的结点结构。栈是DFS的前置知识。",
    "数据结构-补充笔记-原创演示.txt": "栈：在表尾执行插入和删除的线性表。DFS：深度优先搜索。树包含二叉树。",
    "Python-调用栈-原创演示.txt": "栈：函数调用的后进先出结构。列表：Python可变序列。",
}


def prepare(data_root: Path, password: str) -> dict:
    """Refuse existing directories and never emit passwords, sessions or recovery codes."""
    if not data_root.is_absolute() or data_root.exists():
        raise ValueError("请指定尚不存在的绝对目录")
    validate_password(password)
    data_root.mkdir(parents=True, exist_ok=False)
    (data_root / ".synthetic-course-graph").touch()
    documents = data_root / "documents"
    documents.mkdir()
    for name, text in DOCUMENTS.items():
        (documents / name).write_text(text, encoding="utf-8")
    database = data_root / "data" / "accounts.db"
    store = SQLiteStorage(database)
    try:
        store.init_schema()
    finally:
        store.close()
    workspace = f"u_{uuid4().hex}"
    account = AccountStore(database)
    account.register("course-graph@example.invalid", password, "课程图谱合成验收", workspace, False)
    result = {"synthetic": True, "data_root": str(data_root), "database_path": str(database),
              "email": "course-graph@example.invalid", "documents": list(DOCUMENTS),
              "notice": "仅原创工程验收资料，不代表真实学生效果。密码由本次环境变量提供，未保存明文。"}
    (data_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    args = parser.parse_args()
    password = os.environ.get("FILEMATE_AUDIT_PASSWORD", "")
    if not password:
        parser.error("需通过FILEMATE_AUDIT_PASSWORD提供一次性合成账户密码；不输出凭据")
    print(json.dumps(prepare(args.data_root, password), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
