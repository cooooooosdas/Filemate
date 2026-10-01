"""为已导入的公开资料添加自编练习，不预填作答或模型结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from filemate.execution.storage import SQLiteStorage


def main() -> None:
    """仅向项目临时数据库添加来源明确的自编练习。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    target = args.db.resolve()
    if not target.is_relative_to(PROJECT_ROOT / "_working"):
        parser.error("验收数据库必须位于项目 _working 目录内")
    storage = SQLiteStorage(target)
    try:
        storage.init_schema()
        source = storage.get_source(args.source)
        if source is None or "堆作为完全二叉树的一个特例" not in source["raw_text"]:
            parser.error("必须先导入附带来源与许可的真实教材节选")
        artifact = storage.save_artifact(
            source_id=args.source, artifact_type="questions", title="堆 · 自编验收练习",
            content=[{"type": "填空题", "question": "堆是哪种二叉树的一个特例？",
                      "knowledge_point": "堆", "answer": "完全二叉树",
                      "explanation": "资料明确说明：堆作为完全二叉树的一个特例。"}],
            metadata={"origin": "acceptance_self_authored", "is_model_generated": False,
                      "material_url": "https://www.hello-algo.com/chapter_heap/heap/"},
        )
        print(json.dumps({"artifact_id": artifact, "source_id": args.source}))
    finally:
        storage.close()


if __name__ == "__main__":
    main()
