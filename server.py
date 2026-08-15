"""FileMate FastAPI 服务器。"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from filemate.core.categories import CATEGORIES
from filemate.execution.confirmation_executor import (
    ConfirmationExecutor,
    ExecutionError,
)
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient

# 加载 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=False)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"}
DATA_DIR = Path(
    os.getenv(
        "FILEMATE_DATA_DIR",
        str(Path(__file__).resolve().parent / ".filemate-data"),
    )
).expanduser().resolve()
UPLOAD_ROOT = Path(
    os.getenv(
        "FILEMATE_UPLOAD_DIR",
        str(DATA_DIR / "inbox"),
    )
).expanduser().resolve()
DATABASE_PATH = Path(
    os.getenv("FILEMATE_DB_PATH", str(DATA_DIR / "filemate.db"))
).expanduser().resolve()
SHUTDOWN_TOKEN = os.getenv("FILEMATE_SHUTDOWN_TOKEN", "")
_uvicorn_server: Any = None
ARCHIVE_DIR = Path(
    os.getenv(
        "FILEMATE_ARCHIVE_DIR",
        str(Path(__file__).resolve().parent / "archive"),
    )
).expanduser().resolve()


async def _save_upload(file: UploadFile) -> tuple[Path, int]:
    """校验并保存上传文件，隔离同名文件与路径穿越。"""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if Path(filename).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 25 MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    upload_dir = UPLOAD_ROOT / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_bytes(content)
    return file_path, len(content)

# 初始化数据库
_storage = SQLiteStorage(DATABASE_PATH)
_storage.init_schema()

# =============== Models ===============

class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


class ConfirmRequest(BaseModel):
    accepted: bool
    edits: dict | None = None


class SessionDraftRequest(BaseModel):
    edits: dict


class ArtifactUpdateRequest(BaseModel):
    title: str
    content: Any


class ProductFeedbackRequest(BaseModel):
    area: Literal["retrieval", "tutor", "interview", "study_plan"]
    target_id: str
    rating: Literal[-1, 1]
    context: dict[str, Any] | None = None


# =============== App ===============

app = FastAPI(title="FileMate API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """把 FastAPI HTTP 错误收敛为统一响应。"""
    del request
    message = exc.detail if isinstance(exc.detail, str) else json.dumps(
        exc.detail,
        ensure_ascii=False,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": message},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """返回稳定、可直接展示的请求校验错误。"""
    del request
    errors = exc.errors()
    message = errors[0].get("msg", "请求参数无效") if errors else "请求参数无效"
    return JSONResponse(
        status_code=422,
        content={"success": False, "data": None, "error": message},
    )

# 内存存储 session（简化版，后续可以连数据库）
_sessions: dict[str, dict] = {}


def _deserialize_session(session: dict[str, Any]) -> dict[str, Any]:
    """还原数据库 Session 中的 JSON 字段。"""
    result = dict(session)
    for field, fallback in (("entities", {}), ("milestones", [])):
        raw = result.get(field)
        if isinstance(raw, str):
            try:
                result[field] = json.loads(raw)
            except json.JSONDecodeError:
                result[field] = fallback
        elif raw is None:
            result[field] = fallback
    return result


def _public_execution(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """筛选前端需要的执行记录字段。"""
    if record is None:
        return None
    return {
        key: record.get(key)
        for key in (
            "execution_id",
            "status",
            "source_path",
            "dest_path",
            "ics_path",
            "error",
            "created_at",
            "applied_at",
            "undone_at",
        )
    }


def _enrich_session(session: dict[str, Any]) -> dict[str, Any]:
    """补充反序列化字段与可撤销执行状态。"""
    result = _deserialize_session(session)
    active = _storage.get_active_execution(result["session_id"])
    latest = active or _storage.get_latest_execution(result["session_id"])
    result["execution"] = _public_execution(latest)
    result["can_undo"] = active is not None
    return result


def _apply_session_edits(
    session_id: str,
    edits: dict[str, Any] | None,
    *,
    action: str,
) -> dict[str, Any]:
    """验证并持久化用户草稿修改。"""
    session = _storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not edits:
        return _enrich_session(session)

    updates: dict[str, Any] = {"user_modified": 1}
    if "category" in edits:
        category = str(edits["category"]).strip()
        if category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="无效的文件分类")
        updates["category"] = category
    if "confidence" in edits:
        confidence = float(edits["confidence"])
        if not 0 <= confidence <= 1:
            raise HTTPException(status_code=422, detail="置信度必须在 0 到 1 之间")
        updates["confidence"] = confidence
    if "suggested_name" in edits:
        suggested_name = str(edits["suggested_name"]).strip()
        if not suggested_name:
            raise HTTPException(status_code=422, detail="文件名不能为空")
        updates["suggested_name"] = suggested_name

    session_data = _deserialize_session(session)
    entities = dict(session_data.get("entities") or {})
    entity_edits = edits.get("entities")
    if entity_edits is not None:
        if not isinstance(entity_edits, dict):
            raise HTTPException(status_code=422, detail="entities 必须是对象")
        entities.update(entity_edits)
        updates["entities"] = json.dumps(entities, ensure_ascii=False)

    _storage.update_session(session_id, **updates)
    serialized_edits = json.dumps(edits, ensure_ascii=False)
    _storage.log_operation(
        session_id,
        action,
        detail=serialized_edits,
        user_override=serialized_edits,
    )
    updated = _storage.get_session(session_id)
    if updated is None:
        raise RuntimeError("Session 更新后不可读")
    _sessions[session_id] = _deserialize_session(updated)
    return _enrich_session(updated)


def _confirmation_executor() -> ConfirmationExecutor:
    """使用当前服务存储与归档目录构造执行器。"""
    return ConfirmationExecutor(storage=_storage, archive_dir=ARCHIVE_DIR)

# =============== Routes ===============

@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE"])
def root():
    """API 根路径：有前端构建产物时返回页面，否则返回 API 信息。"""
    if _frontend_dist.is_dir():
        index = _frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
    return {"message": "FileMate API", "version": "1.2.0"}


@app.get("/api/health", response_model=ApiResponse)
def health_check():
    """供 Web 与桌面壳检测本地服务状态。"""
    return ApiResponse(success=True, data={"version": "1.2.0"})


@app.post("/internal/shutdown", response_model=ApiResponse, include_in_schema=False)
def shutdown_backend(request: Request):
    """仅允许桌面宿主从本机优雅关闭 Sidecar。"""
    client_host = request.client.host if request.client else ""
    if not SHUTDOWN_TOKEN:
        raise HTTPException(status_code=404, detail="Not found")
    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="仅允许本机关闭服务")
    provided = request.headers.get("x-filemate-shutdown-token", "")
    if not hmac.compare_digest(provided, SHUTDOWN_TOKEN):
        raise HTTPException(status_code=403, detail="关闭令牌无效")
    if _uvicorn_server is None:
        raise HTTPException(status_code=503, detail="服务尚未进入可关闭状态")
    _uvicorn_server.should_exit = True
    return ApiResponse(success=True, data={"shutting_down": True})


@app.post("/process", response_model=ApiResponse)
async def process_file(
    file: Annotated[UploadFile, File()],
):
    """上传文件并立即处理。"""
    file_path, size = await _save_upload(file)
    logger.info("Received file: %s (%d bytes)", file_path.name, size)

    # 调用 main.py 的 process_single
    try:
        from main import process_single
        session = await process_single(
            str(file_path),
            skip_calendar=False,
            db_path=str(_storage.db_path),
        )

        result = session.to_dict()
        result["_local_file_path"] = str(file_path)
        _sessions[session.session_id] = result

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        logger.exception("处理失败: %s", file.filename)
        raise HTTPException(status_code=500, detail="文件处理失败") from exc


@app.get("/sessions/{session_id}", response_model=ApiResponse)
def get_session(session_id: str):
    """获取 session 详情。"""
    session = _sessions.get(session_id)
    if not session:
        # 尝试从数据库读取
        session = _storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    return ApiResponse(success=True, data=_enrich_session(session))


@app.patch("/sessions/{session_id}", response_model=ApiResponse)
def update_session_draft(
    session_id: str,
    data: SessionDraftRequest,
):
    """保存分类、命名和实体草稿，不触发文件系统操作。"""
    if _storage.get_active_execution(session_id) is not None:
        raise HTTPException(status_code=409, detail="已执行的 Session 请先撤销")
    session = _apply_session_edits(
        session_id,
        data.edits,
        action="edit_draft",
    )
    return ApiResponse(success=True, data=session)


@app.post("/sessions/{session_id}/confirm", response_model=ApiResponse)
def confirm_session(
    session_id: str,
    data: ConfirmRequest,
):
    """最终确认并执行，或拒绝本次处理结果。"""
    session = _sessions.get(session_id) or _storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not data.accepted:
        _storage.update_session(session_id, status="skipped")
        _storage.log_operation(session_id, "reject", detail="用户跳过")
        updated = _storage.get_session(session_id)
        if updated is not None:
            _sessions[session_id] = _deserialize_session(updated)
        return ApiResponse(
            success=True,
            data={
                "ok": True,
                "session_id": session_id,
                "accepted": False,
                "execution": None,
            },
        )

    active = _storage.get_active_execution(session_id)
    if active is not None:
        execution = _confirmation_executor().execute(
            _deserialize_session(session)
        )
        return ApiResponse(
            success=True,
            data={
                "ok": True,
                "session_id": session_id,
                "accepted": True,
                "execution": execution,
            },
        )

    try:
        if data.edits:
            _apply_session_edits(
                session_id,
                data.edits,
                action="confirm_edit",
            )
        current = _storage.get_session(session_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Session not found")
        execution = _confirmation_executor().execute(
            _deserialize_session(current)
        )
    except ExecutionError as exc:
        logger.warning("Session %s 执行失败: %s", session_id, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    updated = _storage.get_session(session_id)
    if updated is not None:
        _sessions[session_id] = _deserialize_session(updated)
    return ApiResponse(
        success=True,
        data={
            "ok": True,
            "session_id": session_id,
            "accepted": True,
            "execution": execution,
        },
    )


@app.post("/sessions/{session_id}/undo", response_model=ApiResponse)
def undo_session_execution(session_id: str):
    """撤销 Session 最近一次仍生效的文件系统操作。"""
    if _storage.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        execution = _confirmation_executor().undo(session_id)
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated = _storage.get_session(session_id)
    if updated is not None:
        _sessions[session_id] = _deserialize_session(updated)
    return ApiResponse(
        success=True,
        data={
            "ok": True,
            "session_id": session_id,
            "execution": execution,
        },
    )


@app.get("/sessions/{session_id}/executions", response_model=ApiResponse)
def list_session_executions(session_id: str):
    """读取 Session 的执行、失败与撤销记录。"""
    if _storage.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    records = [
        _public_execution(record)
        for record in _storage.list_execution_records(session_id)
    ]
    return ApiResponse(success=True, data=records)


@app.get("/sessions", response_model=ApiResponse)
def list_sessions(
    status: str | None = Query(None),
    limit: int = Query(20),
):
    """获取所有 session 历史。"""
    sessions = [
        _enrich_session(session)
        for session in _storage.list_sessions(status=status, limit=limit)
    ]
    return ApiResponse(success=True, data=sessions)


@app.get("/sessions/{session_id}/ics", response_model=ApiResponse)
def get_ics(session_id: str):
    """获取 .ics 日历文件内容。"""
    session = _sessions.get(session_id) or _storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _deserialize_session(session)
    ics_path = session.get("ics_path") or session.get("entities", {}).get("ics_path")
    if not ics_path or not Path(ics_path).exists():
        raise HTTPException(status_code=404, detail="ICS file not found")

    content = Path(ics_path).read_text(encoding="utf-8")
    return ApiResponse(success=True, data=content)


@app.get("/knowledge/sources", response_model=ApiResponse)
def list_knowledge_sources(limit: int = Query(50, ge=1, le=200)):
    """列出本地工作区中的持久化资料源。"""
    sources = []
    for source in _storage.list_sources(limit=limit):
        item = {key: value for key, value in source.items() if key != "raw_text"}
        item["text_length"] = len(source.get("raw_text", ""))
        sources.append(item)
    return ApiResponse(success=True, data=sources)


@app.get("/knowledge/sources/{source_id}", response_model=ApiResponse)
def get_knowledge_source(source_id: str):
    """读取单个资料源及其文本。"""
    source = _storage.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return ApiResponse(success=True, data=source)


@app.get("/knowledge/sources/{source_id}/artifacts", response_model=ApiResponse)
def list_source_artifacts(
    source_id: str,
    artifact_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
):
    """列出资料源派生出的摘要、卡片、题目、笔记与计划。"""
    if _storage.get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Source not found")
    artifacts = _storage.list_artifacts(
        source_id=source_id,
        artifact_type=artifact_type,
        limit=limit,
    )
    return ApiResponse(success=True, data=artifacts)


@app.get("/knowledge/artifacts/{artifact_id}", response_model=ApiResponse)
def get_knowledge_artifact(artifact_id: str):
    """读取可编辑的学习产物详情。"""
    artifact = _storage.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="学习产物不存在")
    return ApiResponse(success=True, data=artifact)


@app.patch("/knowledge/artifacts/{artifact_id}", response_model=ApiResponse)
def update_knowledge_artifact(
    artifact_id: str,
    request: ArtifactUpdateRequest,
):
    """保存用户对摘要、笔记、卡片或题目的修订。"""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="标题不能为空")
    artifact = _storage.update_artifact(
        artifact_id,
        title=title[:200],
        content=request.content,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="学习产物不存在")
    return ApiResponse(success=True, data=artifact)


@app.get("/knowledge/search", response_model=ApiResponse)
def search_knowledge(
    q: str = Query(..., min_length=1, max_length=200),
    source_id: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    """检索本地资料并返回可定位引用。"""
    from filemate.understanding.retrieval import rank_chunks

    sources = [_storage.get_source(source_id)] if source_id else _storage.list_sources(limit=100)
    chunks = []
    source_names = {}
    for source in sources:
        if source is None:
            continue
        source_names[source["source_id"]] = source["original_name"]
        chunks.extend(_storage.list_source_chunks(source["source_id"]))
    results = rank_chunks(q, chunks, limit=limit)
    for item in results:
        item["source_name"] = source_names.get(item["source_id"], "未知资料")
        item["excerpt"] = item.pop("content")[:280]
    return ApiResponse(success=True, data=results)


# =============== AI 工具箱 API ===============

def _persist_ai_context(
    *,
    file_path: Path,
    text: str,
    artifact_type: str,
    content: Any,
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """持久化资料源、AI 产物与可恢复问答上下文。"""
    file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    source_id = _storage.save_source(
        original_name=file_path.name,
        source_path=str(file_path),
        raw_text=text,
        media_type=mimetypes.guess_type(file_path.name)[0] or "",
        file_hash=file_hash,
        metadata={"size_bytes": file_path.stat().st_size},
    )
    from filemate.understanding.retrieval import split_document

    _storage.replace_source_chunks(source_id, split_document(text))
    artifact_id = _storage.save_artifact(
        source_id=source_id,
        artifact_type=artifact_type,
        title=title,
        content=content,
        metadata=metadata,
    )
    ctx_id = uuid.uuid4().hex[:12]
    _storage.save_document_context(
        ctx_id=ctx_id,
        source_id=source_id,
        artifact_id=artifact_id,
        context_text=text,
        metadata={
            "filename": file_path.name,
            "artifact_type": artifact_type,
        },
    )
    return ctx_id, source_id, artifact_id


@app.post("/ai/summarize", response_model=ApiResponse)
async def ai_summarize(
    file: Annotated[UploadFile, File()],
    max_length: Annotated[int, Form()] = 500,
):
    """AI摘要生成：上传PDF/文档，生成AI摘要笔记。"""
    file_path, _ = await _save_upload(file)
    logger.info("[AI Summarize] Received file: %s", file_path.name)

    try:
        # 解析文件获取文本
        from filemate.perception import FileParser
        parser = FileParser()
        parsed = parser.parse(str(file_path))
        text = parsed.get("raw_text", "")

        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

        # 生成摘要
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.understanding import AISummarizer
        summarizer = AISummarizer(llm)
        summary = summarizer.summarize(text, max_length=max_length)

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="summary",
            content=summary,
            title=f"{file_path.stem} · 摘要",
            metadata={"max_length": max_length},
        )

        result = {
            "ctx_id": ctx_id,
            "filename": file.filename,
            "summary": summary,
            "text_length": len(text),
            "source_id": source_id,
            "artifact_id": artifact_id,
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("AI摘要生成失败: %s", file.filename)
        raise HTTPException(status_code=502, detail="AI 摘要生成失败") from exc


@app.post("/ai/knowledge-cards", response_model=ApiResponse)
async def ai_knowledge_cards(
    file: Annotated[UploadFile, File()],
    num_cards: Annotated[int, Form()] = 10,
    card_format: Annotated[str, Form()] = "front_back",
):
    """AI知识卡生成：上传PDF/文档，生成AI知识卡片。"""
    file_path, _ = await _save_upload(file)
    logger.info("[AI Knowledge Cards] Received file: %s", file_path.name)

    try:
        # 解析文件获取文本
        from filemate.perception import FileParser
        parser = FileParser()
        parsed = parser.parse(str(file_path))
        text = parsed.get("raw_text", "")

        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

        # 生成知识卡
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.understanding import KnowledgeCardGenerator
        generator = KnowledgeCardGenerator(llm)
        cards = generator.generate_cards(text, num_cards=num_cards, card_format=card_format)

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="knowledge_cards",
            content=cards,
            title=f"{file_path.stem} · 知识卡",
            metadata={"count": len(cards), "card_format": card_format},
        )

        result = {
            "ctx_id": ctx_id,
            "filename": file.filename,
            "cards": cards,
            "cards_count": len(cards),
            "source_id": source_id,
            "artifact_id": artifact_id,
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("AI知识卡生成失败: %s", file.filename)
        raise HTTPException(status_code=502, detail="AI 知识卡生成失败") from exc


@app.post("/ai/questions", response_model=ApiResponse)
async def ai_questions(
    file: Annotated[UploadFile, File()],
    question_types: Annotated[str | None, Form()] = None,
    num_questions: Annotated[int, Form()] = 10,
):
    """AI题目提取：上传PDF/文档，提取练习题目。"""
    file_path, _ = await _save_upload(file)
    logger.info("[AI Questions] Received file: %s", file_path.name)

    try:
        # 解析文件获取文本
        from filemate.perception import FileParser
        parser = FileParser()
        parsed = parser.parse(str(file_path))
        text = parsed.get("raw_text", "")

        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

        # 解析题目类型
        types_list = None
        if question_types:
            types_list = [t.strip() for t in question_types.split(",") if t.strip()]

        # 提取题目（接入统一出题主链 generate_questions_with_llm）
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.study import chunk_text, generate_questions_with_llm

        # 旧格式 type → 新 question_type 映射
        _TYPE_MAP = {
            "选择题": "choice",
            "单选题": "choice",
            "多选题": "choice",
            "填空题": "fill",
            "判断题": "short_answer",
            "简答题": "short_answer",
            "计算题": "short_answer",
            "论述题": "short_answer",
            "choice": "choice",
            "fill": "fill",
            "short_answer": "short_answer",
        }

        def _map_type(raw: str) -> str:
            return _TYPE_MAP.get(raw.strip(), "short_answer")

        # 从文件名和文本前段推测学科和知识点
        subject = file_path.stem[:20] or "综合"
        knowledge_point = text[:60].replace("\n", " ") if text else "核心内容"
        chunks = chunk_text(text, chunk_size=800, overlap=100)

        all_questions: list[dict[str, Any]] = []
        types_to_generate = [_map_type(t) for t in types_list] if types_list else ["choice"]
        per_type = max(1, min(num_questions // max(len(types_to_generate), 1), 10))
        for qtype in types_to_generate:
            try:
                batch = generate_questions_with_llm(
                    llm=llm,
                    subject=subject,
                    knowledge_point=knowledge_point,
                    count=per_type,
                    question_type=qtype,
                    context=chunks,
                )
                all_questions.extend(batch)
            except RuntimeError:
                continue

        questions = all_questions[:num_questions] if all_questions else []

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="questions",
            content=questions,
            title=f"{file_path.stem} · 练习题",
            metadata={"count": len(questions), "types": types_list or []},
        )

        result = {
            "ctx_id": ctx_id,
            "filename": file.filename,
            "questions": questions,
            "questions_count": len(questions),
            "source_id": source_id,
            "artifact_id": artifact_id,
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("AI题目提取失败: %s", file.filename)
        raise HTTPException(status_code=502, detail="AI 题目生成失败") from exc


@app.post("/ai/notes", response_model=ApiResponse)
async def ai_notes(
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()] = "outline",
):
    """AI笔记提取：上传PDF/文档，提取结构化笔记。"""
    file_path, _ = await _save_upload(file)
    logger.info("[AI Notes] Received file: %s", file_path.name)

    try:
        # 解析文件获取文本
        from filemate.perception import FileParser
        parser = FileParser()
        parsed = parser.parse(str(file_path))
        text = parsed.get("raw_text", "")

        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

        # 提取笔记
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.understanding import NoteExtractor
        extractor = NoteExtractor(llm)
        notes = extractor.extract_notes(text, format=format)

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="notes",
            content=notes,
            title=f"{file_path.stem} · 结构化笔记",
            metadata={"format": format},
        )

        result = {
            "ctx_id": ctx_id,
            "filename": file.filename,
            "notes": notes,
            "source_id": source_id,
            "artifact_id": artifact_id,
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("AI笔记提取失败: %s", file.filename)
        raise HTTPException(status_code=502, detail="AI 笔记生成失败") from exc


@app.post("/ai/study-plan", response_model=ApiResponse)
async def ai_study_plan(
    file: Annotated[UploadFile, File()],
    exam_date: Annotated[str, Form()],
    daily_minutes: Annotated[int, Form()] = 60,
    goal: Annotated[str, Form()] = "掌握核心知识并通过考试",
    weak_topics: Annotated[str | None, Form()] = None,
):
    """根据课程资料和考试日期生成个性化复习计划。"""
    file_path, _ = await _save_upload(file)
    logger.info("[AI Study Plan] Received file: %s", file_path.name)

    try:
        from filemate.perception import FileParser

        parsed = FileParser().parse(str(file_path))
        text = parsed.get("raw_text", "")
        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

        from filemate.llm_client import LLMClient, LLMConfig
        from filemate.understanding import StudyPlanGenerator

        topics = None
        if weak_topics:
            topics = [item.strip() for item in weak_topics.split(",") if item.strip()]
        plan = StudyPlanGenerator(LLMClient(LLMConfig.from_env())).generate(
            text=text,
            exam_date=exam_date,
            daily_minutes=daily_minutes,
            goal=goal.strip(),
            weak_topics=topics,
        )

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="study_plan",
            content=plan,
            title=plan.get("title", f"{file_path.stem} · 学习计划"),
            metadata={"exam_date": exam_date, "daily_minutes": daily_minutes},
        )
        saved_plan = _storage.create_study_plan(
            artifact_id=artifact_id,
            source_id=source_id,
            plan=plan,
        )
        return ApiResponse(
            success=True,
            data={
                "ctx_id": ctx_id,
                "filename": file_path.name,
                "plan": plan,
                "source_id": source_id,
                "artifact_id": artifact_id,
                "plan_id": saved_plan["plan_id"],
                "completed_days": saved_plan["completed_days"],
            },
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("AI学习计划生成失败: %s", file_path.name)
        raise HTTPException(status_code=502, detail="AI 学习计划生成失败") from exc


class ChatRequest(BaseModel):
    ctx_id: str
    question: str
    chat_history: list[dict] | None = None
    mode: Literal["answer", "socratic", "feynman"] = "answer"


class QuizAttemptRequest(BaseModel):
    artifact_id: str
    question_index: int
    user_answer: str


class InterviewStartRequest(BaseModel):
    target_role: str
    scenario: str = "求职面试"
    difficulty: str = "标准"


class InterviewAnswerRequest(BaseModel):
    answer: str


class StudyPlanDayRequest(BaseModel):
    completed: bool


# ── AI 学习 ──────────────────────────────────

class AILearningSessionCreate(BaseModel):
    mode: Literal["explore", "reinforce"] = "explore"
    user_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


class AILearningMessage(BaseModel):
    content: str
    file_text: str | None = None


class AILearningSummary(BaseModel):
    format: Literal["markdown"] = "markdown"


def _answer_score(user_answer: str, reference_answer: str) -> float:
    """计算适用于客观题与短答案的稳定相似度。"""
    normalize = lambda value: re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())
    user = normalize(user_answer)
    reference = normalize(reference_answer)
    if not user or not reference:
        return 0.0
    if user == reference or user in reference or reference in user:
        return 1.0
    user_tokens = set(user) | {user[index:index + 2] for index in range(len(user) - 1)}
    reference_tokens = set(reference) | {
        reference[index:index + 2] for index in range(len(reference) - 1)
    }
    return round(len(user_tokens & reference_tokens) / max(1, len(reference_tokens)), 4)


@app.get("/study-plans", response_model=ApiResponse)
def list_study_plans(
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    """读取可跨重启继续执行的学习计划。"""
    try:
        plans = _storage.list_study_plans(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponse(success=True, data=plans)


@app.get("/study-plans/{plan_id}", response_model=ApiResponse)
def get_study_plan(plan_id: str):
    """读取单份学习计划。"""
    plan = _storage.get_study_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="学习计划不存在")
    return ApiResponse(success=True, data=plan)


@app.patch("/study-plans/{plan_id}/days/{day_index}", response_model=ApiResponse)
def update_study_plan_day(
    plan_id: str,
    day_index: int,
    request: StudyPlanDayRequest,
):
    """持久化某个学习日的完成状态。"""
    try:
        plan = _storage.set_study_plan_day(
            plan_id,
            day_index,
            request.completed,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "学习计划不存在" else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return ApiResponse(success=True, data=plan)


@app.post("/quiz/attempts", response_model=ApiResponse)
def submit_quiz_attempt(request: QuizAttemptRequest):
    """批改练习并自动写入错题本（接入统一判题 check_answer）。"""
    artifact = _storage.get_artifact(request.artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="题目集不存在")
    questions = artifact.get("content")
    if not isinstance(questions, list) or not 0 <= request.question_index < len(questions):
        raise HTTPException(status_code=422, detail="题目序号无效")

    # 旧 Artifact 格式兼容：{type, question, options, answer, explanation}
    # → 映射为 {question_type, stem, options, answer}
    _OLD_TYPE_MAP = {
        "选择题": "choice", "单选题": "choice", "多选题": "choice",
        "填空题": "fill", "判断题": "short_answer",
        "简答题": "short_answer", "计算题": "short_answer", "论述题": "short_answer",
    }

    def _normalize_question(q: dict[str, Any]) -> dict[str, Any]:
        if "question_type" in q:
            return q
        mapped = dict(q)
        raw_type = str(q.get("type", ""))
        mapped["question_type"] = _OLD_TYPE_MAP.get(raw_type, "short_answer")
        if "stem" not in mapped and "question" in q:
            mapped["stem"] = q["question"]
        return mapped

    question = _normalize_question(questions[request.question_index])
    user_answer = (request.user_answer or "").strip()

    from filemate.study import check_answer
    is_correct = check_answer(question, user_answer)
    score = 1.0 if is_correct else 0.0

    result = _storage.record_quiz_attempt(
        artifact_id=request.artifact_id,
        question_index=request.question_index,
        user_answer=user_answer,
        is_correct=is_correct,
        score=score,
        feedback="回答正确" if is_correct else "已加入错题本，请结合解析复习",
    )
    return ApiResponse(success=True, data=result)


@app.get("/wrongbook", response_model=ApiResponse)
def list_wrongbook(
    mastered: bool | None = Query(False),
    limit: int = Query(100, ge=1, le=200),
):
    """读取错题本。"""
    return ApiResponse(
        success=True,
        data=_storage.list_wrong_questions(mastered=mastered, limit=limit),
    )


@app.get("/analytics/overview", response_model=ApiResponse)
def learning_analytics():
    """返回学习闭环与模拟面试的本地统计。"""
    return ApiResponse(success=True, data=_storage.get_learning_analytics())


def _anonymous_feedback_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """仅保留评测需要的非文本、非身份指标。"""
    if not context:
        return {}
    numeric_keys = {
        "rank",
        "score",
        "query_length",
        "query_token_count",
        "duration_seconds",
    }
    enum_keys = {"result_type", "mode"}
    sanitized: dict[str, Any] = {}
    for key in numeric_keys:
        value = context.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            sanitized[key] = value
    for key in enum_keys:
        value = context.get(key)
        if isinstance(value, str):
            sanitized[key] = value[:40]
    return sanitized


@app.post("/evaluation/feedback", response_model=ApiResponse)
def record_evaluation_feedback(request: ProductFeedbackRequest):
    """记录匿名产品反馈，不保存原问题、文件名或用户身份。"""
    target_id = request.target_id.strip()
    if not target_id or len(target_id) > 500:
        raise HTTPException(status_code=422, detail="反馈目标无效")
    feedback = _storage.record_product_feedback(
        area=request.area,
        target_id=target_id,
        rating=request.rating,
        context=_anonymous_feedback_context(request.context),
    )
    return ApiResponse(
        success=True,
        data={
            "feedback_id": feedback["feedback_id"],
            "area": feedback["area"],
            "rating": feedback["rating"],
            "updated_at": feedback["updated_at"],
        },
    )


@app.get("/evaluation/feedback/summary", response_model=ApiResponse)
def evaluation_feedback_summary():
    """返回本机匿名反馈汇总。"""
    return ApiResponse(success=True, data=_storage.get_product_feedback_summary())


@app.get("/evaluation/feedback/export.csv")
def export_evaluation_feedback():
    """导出不含原文、文件名和身份字段的匿名评测 CSV。"""
    output = io.StringIO()
    fields = [
        "feedback_id",
        "area",
        "target_hash",
        "rating",
        "context_json",
        "created_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in _storage.list_product_feedback(limit=5000):
        writer.writerow(
            {
                "feedback_id": item["feedback_id"],
                "area": item["area"],
                "target_hash": item["target_hash"],
                "rating": item["rating"],
                "context_json": json.dumps(
                    item["context"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="filemate-anonymous-feedback.csv"'
            )
        },
    )


def _parse_iso_date(value: str) -> date | None:
    """安全解析学习计划中的 ISO 日期。"""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@app.get("/review/today", response_model=ApiResponse)
def today_review():
    """聚合下一学习日与高优先级错题，形成今日执行队列。"""
    today = datetime.now().astimezone().date()
    items: list[dict[str, Any]] = []
    active_plans = _storage.list_study_plans(status="active", limit=20)

    for saved in active_plans:
        plan = saved.get("plan_data") or {}
        days = plan.get("daily_plan") or []
        completed = {int(index) for index in saved.get("completed_days") or []}
        candidates = [
            (index, day, _parse_iso_date(str(day.get("date", ""))))
            for index, day in enumerate(days)
            if index not in completed and isinstance(day, dict)
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item[2] or date.max, item[0]))
        day_index, day, scheduled = candidates[0]
        exam = _parse_iso_date(str(plan.get("exam_date", "")))
        overdue = bool(scheduled and scheduled < today)
        due_today = scheduled == today
        urgency = "high" if overdue or (exam and (exam - today).days <= 3) else "normal"
        if overdue:
            reason = f"原定 {scheduled.isoformat()}，建议今天补上"
        elif due_today:
            reason = "这是计划中的今日任务"
        elif scheduled:
            reason = f"下一学习日为 {scheduled.isoformat()}"
        else:
            reason = "下一项未完成学习任务"
        items.append(
            {
                "item_id": f"plan:{saved['plan_id']}:{day_index}",
                "kind": "plan_day",
                "priority": urgency,
                "score": 90 if overdue else 70 if due_today else 45,
                "title": str(day.get("focus") or saved.get("title") or "学习计划"),
                "reason": reason,
                "duration_minutes": int(day.get("duration_minutes") or saved["daily_minutes"]),
                "tasks": day.get("tasks") or [],
                "plan_id": saved["plan_id"],
                "day_index": day_index,
                "route": "/study-plan",
            }
        )

    wrong_questions = _storage.list_wrong_questions(
        mastered=False,
        due_only=True,
        limit=50,
    )
    wrong_questions.sort(
        key=lambda item: (
            int(item.get("error_count", 0)) * 3 - int(item.get("correct_streak", 0)),
            str(item.get("updated_at", "")),
        ),
        reverse=True,
    )
    for wrong in wrong_questions[:5]:
        question = wrong.get("question") or {}
        items.append(
            {
                "item_id": f"wrong:{wrong['wrong_id']}",
                "kind": "wrong_question",
                "priority": "high" if int(wrong["error_count"]) >= 2 else "normal",
                "score": 80 + min(int(wrong["error_count"]), 5) * 3,
                "title": str(question.get("question") or "待复习错题"),
                "reason": (
                    f"答错 {wrong['error_count']} 次，"
                    f"已复习 {wrong['review_count']} 次"
                ),
                "duration_minutes": 10,
                "artifact_id": wrong["artifact_id"],
                "question_index": wrong["question_index"],
                "wrong_id": wrong["wrong_id"],
                "explanation": question.get("explanation", ""),
                "route": "/wrongbook",
            }
        )

    items.sort(key=lambda item: (-int(item["score"]), item["kind"]))
    recommended = items[:8]
    return ApiResponse(
        success=True,
        data={
            "date": today.isoformat(),
            "items": recommended,
            "active_plan_count": len(active_plans),
            "pending_wrong_count": len(wrong_questions),
            "recommended_minutes": sum(
                int(item["duration_minutes"]) for item in recommended
            ),
        },
    )


@app.post("/interviews", response_model=ApiResponse)
def start_interview(request: InterviewStartRequest):
    """创建一场可持续复盘的模拟面试。"""
    from filemate.understanding import build_questions

    interview = _storage.create_interview(
        target_role=request.target_role.strip() or "通用岗位",
        scenario=request.scenario,
        difficulty=request.difficulty,
        questions=build_questions(request.scenario, request.target_role),
    )
    interview["current_question"] = interview["questions"][0]
    return ApiResponse(success=True, data=interview)


@app.get("/interviews/{interview_id}", response_model=ApiResponse)
def get_interview(interview_id: str):
    """读取面试进度与评分。"""
    interview = _storage.get_interview(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    index = interview["current_index"]
    interview["current_question"] = (
        interview["questions"][index] if index < len(interview["questions"]) else None
    )
    return ApiResponse(success=True, data=interview)


@app.post("/interviews/{interview_id}/answers", response_model=ApiResponse)
def answer_interview(interview_id: str, request: InterviewAnswerRequest):
    """评估当前回答并推进到下一题。"""
    interview = _storage.get_interview(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview["status"] == "completed":
        raise HTTPException(status_code=409, detail="模拟面试已完成")
    if not request.answer.strip():
        raise HTTPException(status_code=422, detail="回答不能为空")

    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.understanding import InterviewEvaluator

    index = interview["current_index"]
    question = interview["questions"][index]
    try:
        if os.getenv("FILEMATE_INTERVIEW_LOCAL_ONLY") == "1":
            raise RuntimeError("本地评分模式")
        evaluator = InterviewEvaluator(LLMClient(LLMConfig.from_env()))
    except Exception:  # noqa: BLE001 - 未配置模型或隐私模式下使用本地评分
        evaluator = InterviewEvaluator(None)
    evaluation = evaluator.evaluate(
        question,
        request.answer,
        interview["target_role"],
    )
    updated = _storage.save_interview_turn(
        interview_id=interview_id,
        question_index=index,
        question=question,
        answer=request.answer.strip(),
        score=evaluation["score"],
        dimensions=evaluation["dimensions"],
        feedback=evaluation["feedback"],
    )
    next_index = updated["current_index"]
    updated["current_question"] = (
        updated["questions"][next_index]
        if next_index < len(updated["questions"])
        else None
    )
    updated["latest_evaluation"] = evaluation
    return ApiResponse(success=True, data=updated)


@app.post("/ai/chat", response_model=ApiResponse)
async def ai_chat(request: ChatRequest):
    """AI问答：基于文档内容进行问答对话。"""
    ctx_id = request.ctx_id
    question = request.question

    if not ctx_id:
        raise HTTPException(status_code=422, detail="文档上下文 ID 不能为空")

    ctx = _storage.get_document_context(ctx_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="文档上下文不存在，请先上传文档")

    context = ctx.get("context_text", "")
    if not context:
        raise HTTPException(status_code=422, detail="文档上下文为空")

    logger.info("[AI Chat] ctx_id: %s, question: %s", ctx_id, question[:50])

    try:
        from filemate.understanding.retrieval import rank_chunks

        citations = []
        source = _storage.get_source(ctx.get("source_id")) if ctx.get("source_id") else None
        chunks = _storage.list_source_chunks(ctx["source_id"]) if source else []
        matches = rank_chunks(question, chunks, limit=5)
        if matches:
            context_parts = []
            for index, match in enumerate(matches, start=1):
                location = f"第 {match['page_number']} 页" if match.get("page_number") else f"片段 {match['chunk_index'] + 1}"
                context_parts.append(f"[引用{index} | {location}]\n{match['content']}")
                citations.append(
                    {
                        "id": index,
                        "source_id": match["source_id"],
                        "source_name": source["original_name"],
                        "page_number": match.get("page_number"),
                        "chunk_index": match["chunk_index"],
                        "excerpt": match["content"][:220],
                        "score": match["score"],
                    }
                )
            context = "\n\n".join(context_parts)
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.understanding import AIChatbot
        chatbot = AIChatbot(llm)
        persisted_history = ctx.get("chat_history") or request.chat_history or []
        answer = chatbot.answer(
            question,
            context,
            chat_history=persisted_history,
            mode=request.mode,
        )
        chat_history = _storage.append_context_messages(
            ctx_id,
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
        )

        result = {
            "ctx_id": ctx_id,
                "question": question,
                "answer": answer,
                "mode": request.mode,
                "citations": citations,
            "chat_history": chat_history[-10:],
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        logger.exception("AI问答失败")
        raise HTTPException(status_code=502, detail="AI 问答失败") from exc


# =============== AI 辅助学习 ===============

def _make_llm_for_learning(api_key: str, base_url: str, model: str) -> LLMClient:
    """根据用户自带的 API 配置构建 LLMClient。"""
    from filemate.llm_client import LLMClient, LLMConfig
    # 如果用户没提供 key，回退到系统默认配置
    if not api_key:
        env = LLMConfig.from_env()
        api_key = env.api_key or api_key
        base_url = env.base_url or base_url
        model = env.model or model
    cfg = LLMConfig(
        provider="auto",
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=120.0,
        max_retries=2,
    )
    return LLMClient(cfg)


@app.post("/ai/learning/sessions", response_model=ApiResponse)
def create_ai_learning_session(req: AILearningSessionCreate):
    """创建 AI 学习会话（立即返回，不阻塞 LLM）。"""
    session_id = uuid.uuid4().hex[:12]
    _storage.create_ai_session(
        session_id=session_id,
        mode=req.mode,
        user_api_key=req.user_api_key,
        llm_base_url=req.llm_base_url,
        llm_model=req.llm_model,
    )
    return ApiResponse(success=True, data={"session_id": session_id, "mode": req.mode})


@app.get("/ai/learning/sessions", response_model=ApiResponse)
def list_ai_learning_sessions(limit: int = Query(50, ge=1, le=100)):
    """获取 AI 学习会话列表。"""
    sessions = _storage.list_ai_sessions(limit=limit)
    return ApiResponse(success=True, data=sessions)


@app.get("/ai/learning/sessions/{session_id}", response_model=ApiResponse)
def get_ai_learning_session(session_id: str):
    """获取 AI 学习会话详情（含消息历史）。"""
    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = _storage.get_ai_messages(session_id)
    session["messages"] = messages
    return ApiResponse(success=True, data=session)


@app.get("/ai/learning/sessions/{session_id}/download")
def download_ai_learning_session(session_id: str, mode: str = ""):
    """导出对话为 Markdown 文件（公式保留 LaTeX 源码）。"""
    import tempfile

    from fastapi.responses import FileResponse

    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 按模式过滤
    if mode:
        messages = _storage.get_ai_messages_by_mode(session_id, mode)
        mode_label = "探索" if mode == "explore" else "巩固"
        filename = f"{mode_label}学习笔记_{session_id[:8]}.md"
    else:
        messages = _storage.get_ai_messages(session_id)
        filename = f"AI学习对话_{session_id[:8]}.md"

    if not messages:
        raise HTTPException(status_code=400, detail="对话为空，无法导出")

    mode_title = {"explore": "探索全新领域", "reinforce": "加强已有知识"}.get(mode, "全部对话")

    lines = [
        f"# {mode_title} - 学习对话记录",
        "",
        f"> 会话 ID: {session_id}",
        f"> 导出时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 消息数: {len(messages)}",
        "",
        "---",
        "",
    ]

    for m in messages:
        role_label = "用户" if m["role"] == "user" else "AI 助手"
        lines.append(f"### {role_label}")
        lines.append("")
        lines.append(m["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    content = "\n".join(lines)

    # 写入临时文件（delete=False 保留文件供 FileResponse 读取）
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    return FileResponse(
        path=tmp_path,
        filename=filename,
        media_type="text/markdown; charset=utf-8",
    )


class AILearningSettingsUpdate(BaseModel):
    user_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


class AILearningModeUpdate(BaseModel):
    mode: str


class AILearningConfigValidate(BaseModel):
    user_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


@app.post("/ai/learning/sessions/{session_id}/validate-config", response_model=ApiResponse)
def validate_ai_learning_config(session_id: str, req: AILearningConfigValidate):
    """验证 LLM 配置是否可用（直接发 HTTP 请求，避免 LLMClient  overhead）。"""
    import requests as _requests

    api_key = req.user_api_key or os.environ.get("LLM_API_KEY", "")
    base_url = (req.llm_base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
    model = req.llm_model or os.environ.get("LLM_MODEL", "")

    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")

    # 根据 base_url 判断端点
    if "step_plan" in base_url:
        url = f"{base_url}/messages"
    elif "unisound" in base_url or "anthropic" in base_url:
        url = f"{base_url}/v1/messages"
    else:
        url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "OK"}],
        "max_tokens": 1,
        "temperature": 0,
    }

    try:
        resp = _requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return ApiResponse(success=True, data={"message": "API 可用"})
        if resp.status_code == 401:
            raise HTTPException(status_code=400, detail="API Key 无效，请检查")
        raise HTTPException(status_code=400, detail=f"API 返回异常 (HTTP {resp.status_code})")
    except _requests.Timeout:
        raise HTTPException(status_code=400, detail="API 连接超时，请检查 URL 和网络")
    except _requests.ConnectionError:
        raise HTTPException(status_code=400, detail="无法连接到 API 服务器，请检查 Base URL")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("LLM 配置验证失败: %s", exc)
        raise HTTPException(status_code=400, detail="API 信息异常，请检查配置") from exc


@app.put("/ai/learning/sessions/{session_id}/settings", response_model=ApiResponse)
def update_ai_learning_settings(session_id: str, req: AILearningSettingsUpdate):
    """更新 AI 学习会话的 LLM 配置（API Key / Base URL / 模型名）。"""
    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    _storage.update_ai_session(
        session_id=session_id,
        user_api_key=req.user_api_key,
        llm_base_url=req.llm_base_url,
        llm_model=req.llm_model,
    )
    return ApiResponse(success=True, data={"message": "配置已保存"})


@app.put("/ai/learning/sessions/{session_id}/mode", response_model=ApiResponse)
def update_ai_learning_mode(session_id: str, req: AILearningModeUpdate):
    """更新 AI 学习会话的模式（探索 / 巩固）。"""
    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if req.mode not in ("explore", "reinforce"):
        raise HTTPException(status_code=400, detail="模式无效，必须是 explore 或 reinforce")
    _storage.update_ai_session(session_id=session_id, mode=req.mode)
    return ApiResponse(success=True, data={"mode": req.mode})


@app.post("/ai/learning/sessions/{session_id}/messages", response_model=ApiResponse)
async def send_ai_learning_message(session_id: str, req: AILearningMessage):
    """发送消息到 AI 学习会话。"""
    from filemate.understanding.ai_learning import AILearningChat

    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 持久化用户消息（带上当前模式）
    current_mode = session.get("mode", "explore")
    _storage.add_ai_message(
        message_id=uuid.uuid4().hex[:12],
        session_id=session_id,
        role="user",
        content=req.content,
        mode=current_mode,
    )

    # 构建 LLM：优先用 session 里的配置，再回退到环境变量
    api_key = session.get("user_api_key", "") or os.environ.get("LLM_API_KEY", "")
    llm_base_url = session.get("llm_base_url", "") or os.environ.get("LLM_BASE_URL", "")
    llm_model = session.get("llm_model", "") or os.environ.get("LLM_MODEL", "")
    llm = _make_llm_for_learning(
        api_key=api_key,
        base_url=llm_base_url,
        model=llm_model,
    )
    chat = AILearningChat(_storage, llm)

    try:
        reply = chat.chat(
            session_id=session_id,
            user_message=req.content,
            mode=session["mode"],
            uploaded_file_text=req.file_text or "",
        )
        return ApiResponse(success=True, data=reply)
    except Exception as exc:
        logger.exception("AI学习对话失败")
        raise HTTPException(status_code=502, detail="AI 学习对话失败") from exc


@app.post("/ai/learning/sessions/{session_id}/summary", response_model=ApiResponse)
async def summarize_ai_learning_session(session_id: str):
    """总结对话并写入知识库。"""
    from filemate.understanding.ai_learning import AILearningChat

    session = _storage.get_ai_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    api_key = session.get("user_api_key", "") or os.environ.get("LLM_API_KEY", "")
    llm_base_url = session.get("llm_base_url", "") or os.environ.get("LLM_BASE_URL", "")
    llm_model = session.get("llm_model", "") or os.environ.get("LLM_MODEL", "")
    llm = _make_llm_for_learning(
        api_key=api_key,
        base_url=llm_base_url,
        model=llm_model,
    )
    chat = AILearningChat(_storage, llm)

    try:
        result = chat.generate_summary(session_id)
        return ApiResponse(success=True, data=result)
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("生成总结失败")
        raise HTTPException(status_code=502, detail="生成总结失败") from exc

def run_server() -> None:
    """启动本地 FastAPI 服务。"""
    import uvicorn

    global _uvicorn_server
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="info")
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


# ── 前端静态文件（构建后 serve） ──────────────────
_frontend_dist = Path(__file__).resolve().parent / "filemate" / "web" / "dist"

if _frontend_dist.is_dir():
    # 先挂载 assets 等静态资源
    app.mount(
        "/assets",
        StaticFiles(directory=str(_frontend_dist / "assets")),
        name="frontend-assets",
    )
    # favicon 等
    for static_file in _frontend_dist.glob("*.svg"):
        route = f"/{static_file.name}"
        app.get(route)(lambda r, sf=static_file: FileResponse(sf))

    # SPA 兜底：所有非 API 路由返回 index.html
    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        path = full_path or "index.html"
        file_path = _frontend_dist / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")


if __name__ == "__main__":
    run_server()
