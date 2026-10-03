"""生成独立合成教材并连接实际模型验证学习资产闭环。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
NOTICE = "【合成工程资料】由测试脚本原创构造，不是实际学生、教师或学校资料。\n"
LESSONS = [
    {"id": "stack", "name": "数据结构课件.txt", "category": "课件",
     "text": "课程：数据结构。教学课件、课堂讲义。\n栈是一种后进先出的线性结构，英文缩写为LIFO。栈只允许在栈顶插入和删除元素。入栈操作称为push，出栈操作称为pop。依次将1、2、3入栈，再连续出栈，顺序为3、2、1。\n队列是一种先进先出的线性结构，英文缩写为FIFO。队列在队尾插入，在队首删除。广度优先搜索使用队列按层访问节点；深度优先搜索可以使用栈。两者不能混淆。",
     "question": "栈遵循什么顺序？", "pattern": r"后进先出|LIFO"},
    {"id": "os", "name": "操作系统课件.txt", "category": "课件",
     "text": "课程：操作系统。教学课件、课堂讲义。\n进程是程序的一次执行过程，进程控制块PCB保存进程的管理信息。就绪状态表示已具备运行条件但尚未获得CPU；运行状态表示正在CPU上执行；阻塞状态表示等待某个事件。等待磁盘I/O完成时，进程从运行进入阻塞。\n死锁的四个必要条件是互斥、占有并等待、不可剥夺、循环等待。破坏其中任一必要条件可预防死锁。该资料不涉及调度算法的具体性能排名。",
     "question": "死锁的四个必要条件是什么？", "pattern": r"互斥"},
    {"id": "database", "name": "数据库课件.txt", "category": "课件",
     "text": "课程：数据库。教学课件、课堂讲义。\n事务是一组作为整体执行的数据库操作。ACID分别表示原子性、一致性、隔离性、持久性。原子性要求事务全部成功或全部回滚；持久性要求提交后的结果持久保存。\n脏读是读取了另一个事务尚未提交的数据。不可重复读是在同一事务内两次读取同一行得到不同结果。SQL参数化查询通过分离数据和语句结构来降低注入风险，不应把用户输入拼接为SQL。",
     "question": "事务的ACID特性分别是什么？", "pattern": r"原子性"},
    {"id": "homework", "name": "数据结构作业.txt", "category": "作业",
     "text": "课程：数据结构。课后作业、习题、提交任务。请完成第三章习题：说明栈的LIFO原则，推演1、2、3依次入栈后的出栈顺序。作业截止时间为{deadline}，当日18:00前提交。要求提交推理过程，不只列出结论。"},
    {"id": "exam", "name": "操作系统考试通知.txt", "category": "考试通知",
     "text": "课程：操作系统。期末考试通知、考试安排、考场说明。考试日期为{deadline}，时间09:00–11:00，地点为虚拟教学楼A101。考试范围为进程状态与死锁必要条件。请携带文具，本通知不包含实际学生名单。"},
    {"id": "reference", "name": "数据库参考资料.txt", "category": "参考资料",
     "text": "课程：数据库。参考资料、复习资料、参考文献学习摘记。事务原子性表示一个事务中的操作要么全部执行，要么全部不执行；事务持久性表示提交后的更改保存在持久存储中。这是测试脚本原创的概念复习摘记，不引用实际出版物。"},
    {"id": "contest", "name": "虚拟算法竞赛通知.txt", "category": "竞赛通知",
     "text": "虚拟大学测试组委会算法程序设计竞赛报名通知。主办方为虚拟大学测试组委会。赛事报名截止日期为{deadline}，初赛日期为{preliminary}，决赛日期为{final}。参赛任务为运用栈和队列完成算法题。此赛事完全虚构，仅用于验证多阶段时间节点，不是实际赛事公告。"},
]


def save_json(path: Path, value: Any) -> None:
    """写入不包含密钥的工程结果。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def configure(out: Path) -> None:
    """所有读写限定在新的独立测试库。"""
    for name, relative in {
        "FILEMATE_DB_PATH": "runtime/learning.db", "FILEMATE_DATA_DIR": "runtime",
        "FILEMATE_UPLOAD_DIR": "runtime/inbox", "FILEMATE_ARCHIVE_DIR": "runtime/archive",
    }.items():
        os.environ[name] = str(out / relative)
    os.environ["FILEMATE_IDENTITY_MODE"] = "local"


def readback(out: Path) -> None:
    """在新Python进程通过实际API读取已保存资料、产物和复练结果。"""
    configure(out)
    from fastapi.testclient import TestClient

    import server

    state = json.loads((out / "readback-input.json").read_text(encoding="utf-8"))
    with TestClient(server.app) as client:
        for source_id in state["sources"]:
            assert client.get(f"/knowledge/sources/{source_id}").status_code == 200
        for artifact_id in state["artifacts"]:
            artifact = client.get(f"/knowledge/artifacts/{artifact_id}").json()["data"]
            assert artifact["content"]
        assert server._storage.get_wrong_question(state["wrong_id"])["mastered"] == 1
        context = server._storage.get_document_context(state["ctx_id"])
        assert len(context["chat_history"]) >= 4
    save_json(out / "readback-result.json", {"passed": True, "process": "new_python_process",
              "sources": len(state["sources"]), "artifacts": len(state["artifacts"])})


def run(out: Path) -> dict[str, Any]:
    """验证实际模型及SQLite，不生成参与者、SUS或导师评分。"""
    from dotenv import load_dotenv
    from fastapi.testclient import TestClient

    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.perception import FileParser
    from filemate.understanding.classifier import Classifier
    from filemate.understanding.entity_extractor import EntityExtractor
    from filemate.understanding.milestone_detector import MilestoneDetector
    from filemate.understanding.namer import Namer

    load_dotenv(ROOT / ".env", override=False)
    configure(out)
    logging.disable(logging.CRITICAL)
    config = LLMConfig.from_env()
    if not config.api_key:
        raise RuntimeError("实际模型凭据不可用")
    report: dict[str, Any] = {"sample_kind": "synthetic", "provider": config.provider,
        "model": config.model, "started_at": datetime.now().astimezone().isoformat(),
        "checks": [], "model_calls": 0, "materials": [], "status": "running",
        "boundary": "原创合成教材与实际模型工程验收，不代表学生学习提升或真实导师研究"}
    original_call = LLMClient.call

    def counted_call(self: Any, *args: Any, **kwargs: Any) -> str:
        report["model_calls"] += 1
        if report["model_calls"] > 64:
            raise RuntimeError("超出本轮64次模型调用上限")
        kwargs["retry"], kwargs["timeout"] = 1, 30.0
        answer = original_call(self, *args, **kwargs)
        with (out / "model-trace.jsonl").open("a", encoding="utf-8") as trace:
            trace.write(json.dumps({"call": report["model_calls"], "sample_kind": "synthetic",
                                   "response": answer}, ensure_ascii=False) + "\n")
        return answer

    LLMClient.call = counted_call

    def check(label: str, condition: Any) -> None:
        report["checks"].append({"name": label, "passed": bool(condition)})
        save_json(out / "results.json", report)
        if not condition:
            raise AssertionError(label)
        print(f"PASS {label}", flush=True)

    def data(response: Any, label: str) -> Any:
        check(label, response.status_code == 200 and response.json().get("success") is True)
        return response.json()["data"]

    try:
        materials = out / "materials"
        materials.mkdir()
        today = datetime.now().astimezone().date()
        dates = {name: (today + timedelta(days=offset)).isoformat()
                 for name, offset in [("deadline", 7), ("preliminary", 9), ("final", 11)]}
        deadline = dates["deadline"]
        for item in LESSONS:
            path = materials / item["name"]
            text = NOTICE + item["text"].format(**dates)
            path.write_text(text, encoding="utf-8")
            report["materials"].append({"id": item["id"], "file": path.name,
                "category": item["category"], "sample_kind": "synthetic",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        save_json(out / "manifest.json", {"sample_kind": "synthetic", "materials": report["materials"]})
        model = LLMClient(config)
        for item in LESSONS:
            path = materials / item["name"]
            parsed = FileParser().parse(str(path))
            text = parsed.get("raw_text", "")
            check(f"parse_{item['id']}", NOTICE.strip() in text and len(text) > 100)
            classified = Classifier(model).classify(text, path.name)
            check(f"classify_{item['id']}", classified["category"] == item["category"])
            entities = EntityExtractor(model).extract(text)
            check(f"entities_{item['id']}", bool(entities.get("course_name"))
                  or (item["id"] == "contest" and bool(entities.get("extra_entities"))))
            if item["id"] in {"homework", "exam"}:
                check(f"deadline_{item['id']}", entities.get("deadline") == deadline)
                events = MilestoneDetector(model).detect(text)
                check(f"milestone_not_applicable_{item['id']}", events == [])
            if item["id"] == "contest":
                events = MilestoneDetector(model).detect(text)
                check("contest_three_milestones", [event["date"] for event in events]
                      == list(dates.values()))
            name = Namer(model).generate(category=classified["category"],
                course=entities.get("course_name") or "", task=entities.get("task_description") or path.stem,
                deadline=entities.get("deadline") or "", extra_entities=entities.get("extra_entities"))
            check(f"naming_{item['id']}", re.fullmatch(r"(?:\[[^\[\]]+\]-){4}\[[^\[\]]+\]", name))

        import server
        source_ids: list[str] = []
        artifacts: list[str] = []
        contexts: list[str] = []
        questions = None
        with TestClient(server.app) as client:
            for index, item in enumerate(LESSONS):
                path = materials / item["name"]
                source = data(client.post("/knowledge/import", files={"file": (
                    path.name, path.read_bytes(), "text/plain")}), f"import_{item['id']}")
                source_id = source["source_id"]
                source_ids.append(source_id)
                check(f"chunks_{item['id']}", server._storage.list_source_chunks(source_id))
                if index > 2:
                    continue
                context = data(client.post(f"/knowledge/sources/{source_id}/contexts"), f"context_{item['id']}")
                contexts.append(context["ctx_id"])
                kinds = ["summary", "notes", "knowledge_cards", "questions"] if index == 0 else ["summary"]
                for kind in kinds:
                    artifact = data(client.post(f"/knowledge/sources/{source_id}/artifacts",
                        json={"artifact_type": kind, "count": 2, "allow_external_model": True}), f"generate_{item['id']}_{kind}")
                    check(f"saved_{item['id']}_{kind}", artifact["content"])
                    artifacts.append(artifact["artifact_id"])
                    if kind == "questions":
                        questions = artifact
                answer = data(client.post("/ai/chat", json={"ctx_id": context["ctx_id"],
                    "question": item["question"]}), f"chat_{item['id']}")
                check(f"grounded_answer_{item['id']}", answer["answerable"] and re.search(item["pattern"], answer["answer"], re.IGNORECASE))
                check(f"citations_{item['id']}", answer["citations"] and all(
                    citation["source_id"] == source_id and citation["excerpt"] in source["raw_text"]
                    for citation in answer["citations"]))
            before = report["model_calls"]
            refusal = data(client.post("/ai/chat", json={"ctx_id": contexts[0],
                "question": "仙女座星系的恒星数量是多少？"}), "out_of_scope_question")
            check("refusal_without_model", refusal["answerable"] is False and not refusal["citations"] and report["model_calls"] == before)
            before = report["model_calls"]
            empty = client.post("/knowledge/import", files={"file": ("合成空资料.txt", b"", "text/plain")})
            check("empty_rejected_without_model", empty.status_code == 400 and report["model_calls"] == before)
            whitespace = client.post("/knowledge/import", files={"file": ("合成空白资料.txt", b" \n", "text/plain")})
            check("blank_text_rejected_without_model", whitespace.status_code == 422 and report["model_calls"] == before)
            question = questions["content"][0]
            payload = {"artifact_id": questions["artifact_id"], "question_index": 0, "expected_question": question}
            wrong = data(client.post("/quiz/attempts", json={**payload, "user_answer": "此项工程输入明确答错"}), "wrong_answer")
            check("wrong_answer_not_mastered", wrong["is_correct"] is False)
            pending = client.get("/wrongbook?mastered=false").json()["data"]
            wrong_id = next(row["wrong_id"] for row in pending if row["artifact_id"] == questions["artifact_id"])
            for repetition in [1, 2]:
                correct = data(client.post("/quiz/attempts", json={**payload, "user_answer": question["answer"]}), f"correct_repeat_{repetition}")
                check(f"correct_result_{repetition}", correct["is_correct"] is True)
            check("two_correct_mastered", server._storage.get_wrong_question(wrong_id)["mastered"] == 1)
            duplicate = data(client.post("/knowledge/import", files={"file": (
                LESSONS[0]["name"], (materials / LESSONS[0]["name"]).read_bytes(), "text/plain")}), "repeat_import")
            check("same_file_same_source", duplicate["source_id"] == source_ids[0])
            save_json(out / "readback-input.json", {"sources": source_ids, "artifacts": artifacts,
                      "wrong_id": wrong_id, "ctx_id": contexts[0]})
        restarted = subprocess.run([sys.executable, __file__, "--readback", "--out", str(out)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        (out / "readback.log").write_text(restarted.stdout + restarted.stderr, encoding="utf-8")
        check("new_process_readback", restarted.returncode == 0)
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        if isinstance(exc, AssertionError):
            report["failed_check"] = str(exc)
        raise
    finally:
        LLMClient.call = original_call
        report["finished_at"] = datetime.now().astimezone().isoformat()
        save_json(out / "results.json", report)
    return report


def main() -> int:
    """目录边界与重复运行保护先于导入服务。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / "_working"):
        parser.error("测试目录必须位于本项目 _working")
    if args.readback:
        readback(out)
        return 0
    out.mkdir(parents=True, exist_ok=False)
    try:
        report = run(out)
    except Exception as exc:  # noqa: BLE001 - 不在CLI泄露上游错误正文。
        print(f"FAILED {type(exc).__name__}; see {out / 'results.json'}", flush=True)
        return 1
    print(json.dumps({"status": report["status"], "sample_kind": report["sample_kind"],
          "materials": len(report["materials"]), "checks": len(report["checks"]),
          "model_calls": report["model_calls"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
