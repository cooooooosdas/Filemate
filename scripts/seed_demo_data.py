"""为竞赛演示生成独立的 FileMate 数据库。"""

from __future__ import annotations

import argparse
from pathlib import Path

from filemate.execution.storage import SQLiteStorage
from filemate.understanding.retrieval import split_document


def seed(database: Path) -> None:
    """创建可展示学习闭环与面试画像的样例数据。"""
    if database.exists():
        raise FileExistsError(f"目标数据库已存在，请换一个路径: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    storage = SQLiteStorage(database)
    storage.init_schema()
    try:
        sources = [
            (
                "demo-os",
                "操作系统复习讲义.pdf",
                "--- 第 1 页 ---\n进程是资源分配的基本单位。\n--- 第 2 页 ---\n线程是处理器调度的基本单位。",
            ),
            (
                "demo-network",
                "计算机网络重点.pdf",
                "--- 第 1 页 ---\nUDP 是无连接协议。\n--- 第 2 页 ---\nTCP 通过三次握手建立可靠连接。",
            ),
        ]
        for source_id, name, text in sources:
            storage.save_source(
                source_id=source_id,
                original_name=name,
                source_path=f"demo/{name}",
                raw_text=text,
                file_hash=f"demo-{source_id}",
                metadata={"demo": True},
            )
            storage.replace_source_chunks(source_id, split_document(text, chunk_size=200))
            storage.save_artifact(
                artifact_id=f"{source_id}-summary",
                source_id=source_id,
                artifact_type="summary",
                title=f"{name} · 摘要",
                content="演示摘要：提取课程核心概念并保留引用位置。",
                metadata={"demo": True},
            )

        questions = [
            {
                "type": "填空题",
                "question": "TCP 使用几次握手建立连接？",
                "answer": "三次握手",
                "explanation": "三次握手用于确认双方的收发能力。",
            },
            {
                "type": "简答题",
                "question": "线程与进程的核心区别是什么？",
                "answer": "进程是资源分配单位，线程是处理器调度单位",
                "explanation": "两者分别对应资源拥有与执行调度。",
            },
        ]
        storage.save_artifact(
            artifact_id="demo-questions",
            source_id="demo-network",
            artifact_type="questions",
            title="课程联合练习",
            content=questions,
            metadata={"demo": True},
        )
        storage.record_quiz_attempt(
            artifact_id="demo-questions",
            question_index=0,
            user_answer="两次",
            is_correct=False,
            score=0.2,
            feedback="已加入错题本",
        )
        storage.record_quiz_attempt(
            artifact_id="demo-questions",
            question_index=1,
            user_answer="进程管理资源",
            is_correct=False,
            score=0.45,
            feedback="需要补充线程的调度属性",
        )

        interview = storage.create_interview(
            target_role="中国软件杯项目答辩",
            scenario="竞赛答辩",
            difficulty="标准",
            questions=["项目解决什么痛点？", "核心创新点是什么？", "如何证明系统有效？"],
        )
        sample_turns = [
            ("项目解决大学生资料分散、复习缺少闭环的问题。", 78, {"内容": 80, "结构": 74, "表达": 82, "岗位匹配": 76}),
            ("创新点是把可信文件治理、可引用学习问答和成长评测连接起来。", 84, {"内容": 88, "结构": 82, "表达": 83, "岗位匹配": 84}),
            ("我们使用离线评测、自动化测试和用户前后测提供分层证据。", 88, {"内容": 90, "结构": 86, "表达": 87, "岗位匹配": 89}),
        ]
        for index, (answer, score, dimensions) in enumerate(sample_turns):
            storage.save_interview_turn(
                interview_id=interview["interview_id"],
                question_index=index,
                question=interview["questions"][index],
                answer=answer,
                score=score,
                dimensions=dimensions,
                feedback="回答结构完整，可继续补充量化数据。",
            )
    finally:
        storage.close()


def main() -> None:
    """解析命令行并生成演示数据库。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("_working/demo/filemate-demo.db"))
    args = parser.parse_args()
    seed(args.db.resolve())
    print(f"Demo database created: {args.db.resolve()}")


if __name__ == "__main__":
    main()
