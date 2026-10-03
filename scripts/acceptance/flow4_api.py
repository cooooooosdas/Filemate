"""流程 4 API 闭环验收：出题 → 作答 → 错题 → 今日复习 → 掌握。"""

import json
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="fm_flow4_"))
os.environ["FILEMATE_DB_PATH"] = str(tmp / "flow4.db")
os.environ["FILEMATE_DATA_DIR"] = str(tmp / "data")
os.environ["FILEMATE_UPLOAD_DIR"] = str(tmp / "inbox")
os.environ["FILEMATE_ARCHIVE_DIR"] = str(tmp / "archive")

from fastapi.testclient import TestClient

import server

artifact_id = server._storage.save_artifact(
    artifact_type="questions",
    title="Flow4 Acceptance",
    content=[
        {
            "question": "1+1=?",
            "answer": "2",
            "explanation": "基础加法",
        }
    ],
)

client = TestClient(server.app)
report = {"artifact_id": artifact_id, "steps": []}


def require(condition: bool, message: str) -> None:
    """验收条件不满足时立即以非零状态失败。"""
    if not condition:
        raise RuntimeError(message)


def submit(answer: str):
    return client.post(
        "/quiz/attempts",
        json={
            "artifact_id": artifact_id,
            "question_index": 0,
            "user_answer": answer,
        },
    )


def wrongbook(mastered: bool):
    return client.get(f"/wrongbook?mastered={str(mastered).lower()}")


wrong = submit("wrong")
require(wrong.status_code == 200, f"答错提交失败：{wrong.status_code} {wrong.text}")
require(wrong.json()["data"]["is_correct"] is False, "答错结果被错误判为正确")
report["steps"].append(
    {"step": "submit_wrong", "status": wrong.status_code, "data": wrong.json()["data"]}
)

book_false_1 = wrongbook(False)
require(book_false_1.status_code == 200, "答错后错题本查询失败")
pending_after_wrong = any(
    item.get("artifact_id") == artifact_id for item in book_false_1.json()["data"]
)
require(pending_after_wrong, "答错后题目未进入待掌握错题本")
report["steps"].append(
    {
        "step": "wrongbook_after_wrong",
        "status": book_false_1.status_code,
        "count": len(book_false_1.json()["data"]),
        "has_question": pending_after_wrong,
    }
)

today = client.get("/review/today")
require(today.status_code == 200, "今日复习查询失败")
today_has_wrong_item = any(
    item.get("artifact_id") == artifact_id for item in today.json()["data"].get("items", [])
)
require(today_has_wrong_item, "答错后题目未进入今日复习")
report["steps"].append(
    {
        "step": "today_review_after_wrong",
        "status": today.status_code,
        "has_wrong_item": today_has_wrong_item,
    }
)

correct_1 = submit("2")
require(correct_1.status_code == 200, "第一次答对提交失败")
require(correct_1.json()["data"]["is_correct"] is True, "正确答案被错误判定")
report["steps"].append(
    {
        "step": "submit_correct_1",
        "status": correct_1.status_code,
        "is_correct": correct_1.json()["data"]["is_correct"],
    }
)
book_false_2 = wrongbook(False)
require(book_false_2.status_code == 200, "第一次答对后错题本查询失败")
still_pending = any(item.get("artifact_id") == artifact_id for item in book_false_2.json()["data"])
require(still_pending, "仅答对一次就被错误标记为已掌握")
report["steps"].append(
    {
        "step": "wrongbook_after_correct_1",
        "count": len(book_false_2.json()["data"]),
        "still_pending": still_pending,
    }
)

correct_2 = submit("2")
require(correct_2.status_code == 200, "第二次答对提交失败")
require(correct_2.json()["data"]["is_correct"] is True, "第二次正确答案被错误判定")
report["steps"].append(
    {
        "step": "submit_correct_2",
        "status": correct_2.status_code,
        "is_correct": correct_2.json()["data"]["is_correct"],
    }
)
book_true = wrongbook(True)
require(book_true.status_code == 200, "已掌握错题本查询失败")
mastered = any(item.get("artifact_id") == artifact_id for item in book_true.json()["data"])
require(mastered, "连续答对两次后题目未标记为已掌握")
report["steps"].append(
    {
        "step": "wrongbook_mastered",
        "count": len(book_true.json()["data"]),
        "has_question": mastered,
    }
)
book_false_3 = wrongbook(False)
require(book_false_3.status_code == 200, "最终待掌握错题本查询失败")
still_in_pending = any(
    item.get("artifact_id") == artifact_id for item in book_false_3.json()["data"]
)
require(not still_in_pending, "已掌握题目仍残留在待掌握错题本")
report["steps"].append(
    {
        "step": "wrongbook_pending_after_mastered",
        "count": len(book_false_3.json()["data"]),
        "has_question": still_in_pending,
    }
)

out = Path(os.getenv("FILEMATE_EVIDENCE_DIR", str(Path.cwd() / "_working"))) / "flow4-acceptance.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
