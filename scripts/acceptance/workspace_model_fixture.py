"""仅供回环工程验收的合成模型HTTP夹具，不用于真实模型质量评测。"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def content_for(messages: list[dict[str, Any]]) -> tuple[str, int, str]:
    """识别现役合同并返回明确标记的原创合成内容。"""
    system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
    user = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "user")
    kind, count = "chat", 1
    if "课程文件分类器" in system:
        kind = "classification"
        content: Any = {"category": "课件", "confidence": 0.5, "course_name": "操作系统", "reason": "合成合同夹具，非质量评分"}
    elif "信息提取助手" in system:
        kind = "entities"
        content = {"course_name": "操作系统", "task_description": "进程和线程", "deadline": "2026-12-31", "location": None, "extra_entities": {}}
    elif '"sections"' in system:
        kind = "notes"
        content = {"title": "合成资料：栈与队列", "sections": [
            {"title": "栈：后进先出", "content": "栈遵循后进先出（LIFO）。push 入栈，pop 出栈。此内容为原创工程夹具。"},
            {"title": "队列：先进先出", "content": "队列遵循先进先出（FIFO）。enqueue 入队，dequeue 出队。仅用于检查阅读、保存与恢复。"},
        ]}
    elif '"front"' in system:
        kind = "knowledge_cards"
        matched = re.search(r"最多(\d+)张", system)
        count = min(10, max(1, int(matched.group(1)) if matched else 5))
        content = [{"front": f"合成回忆卡 {index + 1}：栈遵循什么顺序？", "back": "后进先出（LIFO）。push 入栈，pop 出栈。"} for index in range(count)]
    elif "高校出题专家" in system:
        kind = "questions"
        matched = re.search(r"数量[：:]\s*(\d+)", user)
        count = min(10, max(1, int(matched.group(1)) if matched else 5))
        content = [{"subject": "数据结构", "knowledge_point": "栈与队列", "question_type": "choice",
                    "stem": f"工程合成练习 {index + 1}：栈遵循哪一种访问顺序？",
                    "options": ["A. 后进先出（LIFO）", "B. 先进先出（FIFO）", "C. 随机访问", "D. 按字母排序"],
                    "answer": "A", "analysis": "栈遵循后进先出（LIFO）；此题仅用于界面链路验收。"} for index in range(count)]
    elif '"summary"' in system:
        kind = "summary"
        content = {"summary": "合成资料摘要：栈遵循后进先出（LIFO），队列遵循先进先出（FIFO）。本资料仅用于工程验收，不代表真实学习效果。"}
    else:
        return kind, count, "依据这份合成资料，栈遵循后进先出（LIFO）。push 入栈，pop 出栈。[引用1]"
    return kind, count, json.dumps(content, ensure_ascii=False)


def main() -> None:
    """只监听回环地址并要求一次性合成凭据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    token = os.environ.get("FILEMATE_UI_FIXTURE_TOKEN", "")
    if not token or not 1 <= args.port <= 65535:
        raise ValueError("需要一次性夹具凭据及有效端口")
    lock = threading.Lock()
    state: dict[str, Any] = {"calls": [], "next_mode": "normal", "next_delay": 0.0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *arguments: Any) -> None:
            pass

        def respond(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == "Bearer " + token

        def do_GET(self) -> None:
            if self.path == "/health":
                self.respond(200, {"scope": "synthetic_engineering_fixture", "ready": True})
            elif self.path == "/stats" and self.authorized():
                with lock:
                    snapshot = list(state["calls"])
                self.respond(200, {"scope": "synthetic_engineering_fixture", "calls": snapshot})
            else:
                self.respond(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if not self.authorized():
                self.respond(401, {"error": "fixture_auth_required"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                self.respond(413, {"error": "fixture_request_size"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.respond(400, {"error": "invalid_json"})
                return
            if self.path == "/control":
                mode = body.get("mode", "normal")
                delay = body.get("delay", 0)
                if mode not in {"normal", "invalid", "unavailable"} or not isinstance(delay, (int, float)) or not 0 <= delay <= 5:
                    self.respond(422, {"error": "invalid_control"})
                    return
                with lock:
                    if body.get("reset_calls") is True:
                        state["calls"] = []
                    state["next_mode"], state["next_delay"] = mode, delay
                self.respond(200, {"armed": True})
                return
            if self.path != "/v1/chat/completions" or not isinstance(body.get("messages"), list):
                self.respond(404, {"error": "not_found"})
                return
            kind, count, content = content_for(body["messages"])
            with lock:
                mode, delay = state["next_mode"], state["next_delay"]
                state["next_mode"], state["next_delay"] = "normal", 0.0
                state["calls"].append({"kind": kind, "requested_count": count, "mode": mode})
            time.sleep(delay)
            if mode == "unavailable":
                self.respond(503, {"error": "synthetic_unavailable"})
                return
            self.respond(200, {"choices": [{"message": {"role": "assistant", "content": "invalid synthetic JSON" if mode == "invalid" else content}}]})

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
