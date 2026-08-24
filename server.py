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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from filemate.core.categories import CATEGORIES
from filemate.execution.confirmation_executor import (
    ConfirmationExecutor,
    ExecutionError,
)
from filemate.execution.storage import SQLiteStorage

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


def _managed_file_status(
    path_value: str | None,
    *,
    remove: bool = False,
) -> dict[str, Any]:
    """判断或清理托管上传副本是否位于 FILEMATE_UPLOAD_DIR 内。

    resolve 后再判断相对关系，防止符号链接与路径穿越逃逸到上传目录之外。
    remove=True 时仅删除目录内的真实文件，并尝试清理上传时生成的空 uuid 目录。
    外部原文件、归档文件一律不删。
    """
    result: dict[str, Any] = {
        "path": str(path_value) if path_value else None,
        "managed": False,
        "exists": False,
        "removed": False,
    }
    if not path_value:
        return result
    try:
        candidate = Path(path_value).expanduser().resolve(strict=False)
    except OSError:
        return result
    result["path"] = str(candidate)
    root = UPLOAD_ROOT.resolve(strict=False)
    if not candidate.is_relative_to(root):
        return result
    result["managed"] = True
    result["exists"] = candidate.exists()
    if remove and candidate.exists() and candidate.is_file():
        try:
            candidate.unlink()
            result["removed"] = True
            parent = candidate.parent
            if parent != root and parent.is_relative_to(root):
                parent.rmdir()
        except OSError as exc:
            logger.warning("删除托管副本失败: %s (%s)", candidate, exc)
    return result


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

        # 阶段级失败（损坏/加密文件）→ 返回 success=False，前端 ElMessage.error 已就绪
        if session.error:
            return ApiResponse(success=False, data=result, error=session.error)
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


@app.delete("/knowledge/sources/{source_id}", response_model=ApiResponse)
def delete_knowledge_source(source_id: str):
    """预览并删除一份知识资料及其派生数据。

    先返回（并执行）删除影响，再仅清理 FILEMATE_UPLOAD_DIR 内的托管副本；
    用户外部原文件、归档文件与其他 Source 引用文件不会被删除。幂等：重复删除
    返回 404（与“资源不存在”一致），不重复清理。
    """
    preview = _storage.preview_source_deletion(source_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Source not found")

    file_status = _managed_file_status(preview.get("source_path"), remove=False)

    deleted = _storage.delete_source(source_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if file_status["managed"] and file_status["exists"]:
        file_status = _managed_file_status(preview.get("source_path"), remove=True)
        logger.info(
            "清理托管副本 source_id=%s path=%s removed=%s",
            source_id,
            file_status["path"],
            file_status["removed"],
        )

    return ApiResponse(
        success=True,
        data={
            "source_id": source_id,
            "affected": deleted["affected"],
            "managed_file": file_status,
            "external_files_untouched": not file_status["managed"],
        },
    )


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

        # 提取题目
        from filemate.llm_client import LLMClient, LLMConfig
        llm_config = LLMConfig.from_env()
        llm = LLMClient(llm_config)
        from filemate.understanding import QuestionExtractor
        extractor = QuestionExtractor(llm)
        questions = extractor.extract_questions(text, question_types=types_list, num_questions=num_questions)

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
    """批改练习并自动写入错题本。"""
    artifact = _storage.get_artifact(request.artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="题目集不存在")
    questions = artifact.get("content")
    if not isinstance(questions, list) or not 0 <= request.question_index < len(questions):
        raise HTTPException(status_code=422, detail="题目序号无效")
    question = questions[request.question_index]
    reference = str(question.get("answer", "")) if isinstance(question, dict) else ""
    score = _answer_score(request.user_answer, reference)
    result = _storage.record_quiz_attempt(
        artifact_id=request.artifact_id,
        question_index=request.question_index,
        user_answer=request.user_answer.strip(),
        is_correct=score >= 0.72,
        score=score,
        feedback="回答正确" if score >= 0.72 else "已加入错题本，请结合解析复习",
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


# =============== Main ===============

def run_server() -> None:
    """启动本地 FastAPI 服务。"""
    import uvicorn

    global _uvicorn_server
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="info")
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


if __name__ == "__main__":
    run_server()
