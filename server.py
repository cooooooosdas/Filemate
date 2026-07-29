"""FileMate FastAPI 服务器。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

# 加载 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# 初始化数据库
from filemate.execution.storage import SQLiteStorage
_storage = SQLiteStorage("filemate.db")
_storage.init_schema()

# =============== Models ===============

class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


class ConfirmRequest(BaseModel):
    accepted: bool
    edits: dict | None = None


# =============== App ===============

app = FastAPI(title="FileMate API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存存储 session（简化版，后续可以连数据库）
_sessions: dict[str, dict] = {}

# =============== Routes ===============

@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE"])
def root():
    return {"message": "FileMate API", "version": "1.0.0"}


@app.post("/process", response_model=ApiResponse)
async def process_file(
    file: UploadFile = File(...),
):
    """上传文件并立即处理。"""
    # 保存上传文件到临时目录
    import tempfile
    temp_dir = Path(tempfile.gettempdir()) / "filemate_uploads"
    temp_dir.mkdir(exist_ok=True)

    file_path = temp_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    logger.info("Received file: %s (%d bytes)", file.filename, len(content))

    # 调用 main.py 的 process_single
    try:
        from main import process_single
        session = await process_single(
            str(file_path),
            skip_calendar=False,
            db_path="filemate.db",
        )

        result = session.to_dict()
        result["_local_file_path"] = str(file_path)
        _sessions[session.session_id] = result

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        logger.exception("处理失败: %s", file.filename)
        return ApiResponse(success=False, error=str(exc))


@app.get("/sessions/{session_id}", response_model=ApiResponse)
def get_session(session_id: str):
    """获取 session 详情。"""
    session = _sessions.get(session_id)
    if not session:
        # 尝试从数据库读取
        from filemate.execution.storage import SQLiteStorage
        store = SQLiteStorage("filemate.db")
        session = store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return ApiResponse(success=True, data=session)
    return ApiResponse(success=True, data=session)


@app.post("/sessions/{session_id}/confirm", response_model=ApiResponse)
def confirm_session(
    session_id: str,
    data: ConfirmRequest,
):
    """确认/拒绝处理结果。"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["status"] = "confirmed" if data.accepted else "rejected"
    if data.edits:
        session["user_modified"] = data.edits

    # 写入数据库
    from filemate.execution.storage import SQLiteStorage
    store = SQLiteStorage("filemate.db")
    store.update_session(
        session_id,
        status=session["status"],
        user_modified=json.dumps(data.edits, ensure_ascii=False) if data.edits else None,
    )
    store.log_operation(
        session_id,
        "confirm" if data.accepted else "reject",
        detail=str(data.edits or {}),
    )

    return ApiResponse(
        success=True,
        data={"ok": True, "session_id": session_id, "accepted": data.accepted}
    )


@app.get("/sessions", response_model=ApiResponse)
def list_sessions(
    status: str | None = Query(None),
    limit: int = Query(20),
):
    """获取所有 session 历史。"""
    from filemate.execution.storage import SQLiteStorage
    store = SQLiteStorage("filemate.db")
    sessions = store.list_sessions(status=status, limit=limit)
    return ApiResponse(success=True, data=sessions)


@app.get("/sessions/{session_id}/ics", response_model=ApiResponse)
def get_ics(session_id: str):
    """获取 .ics 日历文件内容。"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    ics_path = session.get("ics_path")
    if not ics_path or not Path(ics_path).exists():
        raise HTTPException(status_code=404, detail="ICS file not found")

    content = Path(ics_path).read_text(encoding="utf-8")
    return ApiResponse(success=True, data=content)


# =============== Main ===============

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)