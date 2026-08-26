"""流程 2 端到端验收：导入资料 → 生成摘要/知识卡/笔记 → 产物进入知识库 → 重启后可查看。"""

import json
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="fm_flow2_"))
os.environ["FILEMATE_DB_PATH"] = str(tmp / "flow2.db")
os.environ["FILEMATE_DATA_DIR"] = str(tmp / "data")
os.environ["FILEMATE_UPLOAD_DIR"] = str(tmp / "inbox")
os.environ["FILEMATE_ARCHIVE_DIR"] = str(tmp / "archive")

from fastapi.testclient import TestClient

import server

# 构造一份有内容的测试文件
sample_file = tmp / "sample.txt"
sample_file.write_text(
    "人工智能是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。"
    "机器学习是人工智能的子领域，专注于通过经验自动改进的算法。"
    "深度学习使用多层神经网络来处理复杂模式识别任务。"
    "自然语言处理使计算机能够理解和生成人类语言。"
    "计算机视觉让机器能够从图像和视频中提取信息。",
    encoding="utf-8",
)

client = TestClient(server.app)
report = {"steps": []}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


# ---------- 步骤 1：上传文件生成 AI 摘要 ----------
with open(sample_file, "rb") as f:
    summary_resp = client.post(
        "/ai/summarize",
        files={"file": (sample_file.name, f, "text/plain")},
        data={"max_length": "200"},
    )
require(summary_resp.status_code == 200, f"摘要生成失败：{summary_resp.status_code} {summary_resp.text}")
summary_data = summary_resp.json()["data"]
summary_source_id = summary_data["source_id"]
summary_artifact_id = summary_data["artifact_id"]
report["steps"].append({
    "step": "summarize",
    "status": summary_resp.status_code,
    "source_id": summary_source_id,
    "artifact_id": summary_artifact_id,
    "has_summary": bool(summary_data.get("summary")),
})

# ---------- 步骤 2：上传文件生成知识卡 ----------
with open(sample_file, "rb") as f:
    cards_resp = client.post(
        "/ai/knowledge-cards",
        files={"file": (sample_file.name, f, "text/plain")},
        data={"num_cards": "5", "card_format": "front_back"},
    )
require(cards_resp.status_code == 200, f"知识卡生成失败：{cards_resp.status_code} {cards_resp.text}")
cards_data = cards_resp.json()["data"]
cards_source_id = cards_data["source_id"]
cards_artifact_id = cards_data["artifact_id"]
report["steps"].append({
    "step": "knowledge_cards",
    "status": cards_resp.status_code,
    "source_id": cards_source_id,
    "artifact_id": cards_artifact_id,
    "cards_count": cards_data.get("cards_count", 0),
})

# ---------- 步骤 3：上传文件生成结构化笔记 ----------
with open(sample_file, "rb") as f:
    notes_resp = client.post(
        "/ai/notes",
        files={"file": (sample_file.name, f, "text/plain")},
        data={"format": "outline"},
    )
require(notes_resp.status_code == 200, f"笔记生成失败：{notes_resp.status_code} {notes_resp.text}")
notes_data = notes_resp.json()["data"]
notes_source_id = notes_data["source_id"]
notes_artifact_id = notes_data["artifact_id"]
report["steps"].append({
    "step": "notes",
    "status": notes_resp.status_code,
    "source_id": notes_source_id,
    "artifact_id": notes_artifact_id,
    "has_notes": bool(notes_data.get("notes")),
})

# ---------- 步骤 4：验证产物在知识库中可查 ----------
artifacts_resp = client.get(f"/knowledge/sources/{summary_source_id}/artifacts")
require(artifacts_resp.status_code == 200, "知识库查询资料源产物失败")
artifact_list = artifacts_resp.json()["data"]
types = {a["artifact_type"] for a in artifact_list}
require("summary" in types, f"知识库缺少 summary 产物，实际类型：{types}")
require("knowledge_cards" in types, f"知识库缺少 knowledge_cards 产物，实际类型：{types}")
require("notes" in types, f"知识库缺少 notes 产物，实际类型：{types}")
report["steps"].append({
    "step": "list_artifacts",
    "status": artifacts_resp.status_code,
    "count": len(artifact_list),
    "types": sorted(types),
})

# ---------- 步骤 5：验证单条 artifact 可读 ----------
single = client.get(f"/knowledge/artifacts/{summary_artifact_id}")
require(single.status_code == 200, f"读取摘要 artifact 失败：{single.status_code}")
require(single.json()["data"]["artifact_id"] == summary_artifact_id, "artifact_id 不匹配")
report["steps"].append({
    "step": "get_artifact",
    "status": single.status_code,
    "artifact_type": single.json()["data"].get("artifact_type"),
})

# ---------- 步骤 6：验证分块已持久化（通过存储层直接查询） ----------
chunks = server._storage.list_source_chunks(summary_source_id)
require(len(chunks) > 0, "资料分块为空，重启后无法检索")
report["steps"].append({
    "step": "list_chunks",
    "chunk_count": len(chunks),
})

# ---------- 步骤 7：重启后（新建存储实例）数据仍可读 ----------
from filemate.execution.storage import SQLiteStorage

restarted = SQLiteStorage(str(tmp / "flow2.db"))
restarted.init_schema()

source_after = restarted.get_source(summary_source_id)
require(source_after is not None, "重启后资料源不可读")
require(source_after["original_name"] == sample_file.name, "重启后文件名不匹配")

artifact_after = restarted.get_artifact(summary_artifact_id)
require(artifact_after is not None, "重启后摘要 artifact 不可读")
require(artifact_after["artifact_type"] == "summary", "重启后 artifact 类型不匹配")

cards_after = restarted.get_artifact(cards_artifact_id)
require(cards_after is not None, "重启后知识卡 artifact 不可读")
require(cards_after["artifact_type"] == "knowledge_cards", "重启后知识卡类型不匹配")

notes_after = restarted.get_artifact(notes_artifact_id)
require(notes_after is not None, "重启后笔记 artifact 不可读")
require(notes_after["artifact_type"] == "notes", "重启后笔记类型不匹配")

chunks_after = restarted.list_source_chunks(summary_source_id)
require(len(chunks_after) > 0, "重启后资料分块为空")

report["steps"].append({
    "step": "restart_readable",
    "source_exists": source_after is not None,
    "summary_exists": artifact_after is not None,
    "cards_exists": cards_after is not None,
    "notes_exists": notes_after is not None,
    "chunk_count": len(chunks_after),
})

# ---------- 输出报告 ----------
out = Path(os.getcwd()) / "_working" / "flow2-acceptance.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
