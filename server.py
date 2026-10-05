"""FileMate FastAPI 服务器。"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import uuid
from collections import OrderedDict
from contextvars import ContextVar
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from filemate import __version__
from filemate.accounts import REMEMBER_SECONDS, AccountError, AccountStore
from filemate.career.models import (
    DeleteRequest,
    PlanConfirm,
    PositionEdit,
    PositionWrite,
    TrainingStart,
    WrittenAnswer,
)
from filemate.core.categories import CATEGORIES
from filemate.execution.confirmation_executor import (
    ConfirmationExecutor,
    ExecutionError,
)
from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.interview_review.models import VisualMetrics
from filemate.llm_client.credential_store import (
    CredentialStoreError,
    delete_stored_api_key,
    resolve_api_key,
    secure_store_available,
    set_stored_api_key,
)
from filemate.perception.parsers import PLAIN_TEXT_SUFFIXES
from filemate.portfolio.growth import GrowthRepository, ReportRequest
from filemate.portfolio.resume import Profile as ResumeProfile
from filemate.portfolio.resume import ResumeRepository, ResumeRequest
from filemate.study.semester import ConfirmSemester, SemesterConfig, SemesterRepository, TaskUpdate
from filemate.understanding.interview_bank_seed import SEED_QUESTIONS

# 加载 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=False)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"}
LEARNING_UPLOAD_SUFFIXES = ALLOWED_UPLOAD_SUFFIXES | {f".{suffix}" for suffix in PLAIN_TEXT_SUFFIXES}
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
IDENTITY_MODE = os.getenv(
    "FILEMATE_IDENTITY_MODE",
    "anonymous" if os.getenv("FILEMATE_ENV", "development").strip().lower()
    == "production" else "local",
).strip().lower()
if IDENTITY_MODE not in {"local", "anonymous"}:
    raise RuntimeError("FILEMATE_IDENTITY_MODE 只能是 local 或 anonymous")
IDENTITY_COOKIE_NAME = "filemate_identity"
IDENTITY_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
ACCOUNT_COOKIE_NAME = "filemate_session"


def _env_list(name: str, default: list[str]) -> list[str]:
    """读取逗号分隔的环境变量列表。"""
    raw_value = os.getenv(name, "")
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return values or default


APP_ENV = os.getenv("FILEMATE_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
ALLOWED_HOSTS = _env_list(
    "FILEMATE_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "test", "testserver", "tauri.localhost"],
)
CORS_ORIGINS = _env_list(
    "FILEMATE_CORS_ORIGINS",
    [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
)
_uvicorn_server: Any = None
ARCHIVE_DIR = Path(
    os.getenv(
        "FILEMATE_ARCHIVE_DIR",
        str(Path(__file__).resolve().parent / "archive"),
    )
).expanduser().resolve()

_TenantContext = tuple[str, Path, Path]
_tenant_context: ContextVar[_TenantContext | None] = ContextVar(
    "filemate_tenant_context",
    default=None,
)
MAX_OPEN_TENANT_STORAGES = max(
    8,
    int(os.getenv("FILEMATE_MAX_OPEN_TENANT_STORAGES", "32")),
)
TENANT_STORAGE_CACHE_LIMIT = MAX_OPEN_TENANT_STORAGES
_tenant_storages: OrderedDict[str, SQLiteStorage] = OrderedDict()
_active_tenants: dict[str, int] = {}
_tenant_storage_lock = threading.RLock()


def _load_identity_secret() -> bytes:
    """读取或生成本机身份签名密钥。"""
    configured = os.getenv("FILEMATE_IDENTITY_SECRET", "").strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("FILEMATE_IDENTITY_SECRET 至少需要 32 个字符")
        return configured.encode("utf-8")

    secret_path = DATA_DIR / "identity.secret"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoded = base64.urlsafe_b64encode(secrets.token_bytes(32))
        with secret_path.open("xb") as file_handle:
            file_handle.write(encoded)
        try:
            secret_path.chmod(0o600)
        except OSError:
            logger.warning("无法收紧身份密钥文件权限: %s", secret_path)
    except FileExistsError:
        pass
    secret = secret_path.read_bytes().strip()
    if len(secret) < 32:
        raise RuntimeError("身份签名密钥文件无效")
    return secret


_identity_secret = _load_identity_secret() if IDENTITY_MODE == "anonymous" else b""


def _sign_identity(identity_id: str) -> str:
    """签发不可伪造的匿名身份 cookie。"""
    signature = hmac.new(
        _identity_secret,
        identity_id.encode("ascii"),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{identity_id}.{encoded}"


def _verify_identity_cookie(value: str | None) -> str | None:
    """校验并返回匿名身份。"""
    if not value or "." not in value:
        return None
    identity_id, signature = value.rsplit(".", 1)
    if not re.fullmatch(r"u_[0-9a-f]{32}", identity_id):
        return None
    expected = _sign_identity(identity_id).rsplit(".", 1)[1]
    return identity_id if hmac.compare_digest(signature, expected) else None


def _tenant_storage(identity_id: str) -> SQLiteStorage:
    """延迟初始化单个匿名身份的独立数据库。"""
    with _tenant_storage_lock:
        storage = _tenant_storages.get(identity_id)
        if storage is not None:
            _tenant_storages.move_to_end(identity_id)
            return storage
        tenant_root = DATA_DIR / "users" / identity_id
        storage = SQLiteStorage(tenant_root / "filemate.db")
        storage.init_schema()
        storage.ensure_interview_questions(SEED_QUESTIONS)
        _tenant_storages[identity_id] = storage
        _evict_tenant_storages()
        return storage


def _evict_tenant_storages() -> None:
    """关闭最久未使用且没有在途请求的租户连接。"""
    while len(_tenant_storages) > MAX_OPEN_TENANT_STORAGES:
        evicted = False
        for identity_id, storage in tuple(_tenant_storages.items()):
            if _active_tenants.get(identity_id, 0) > 0:
                continue
            del _tenant_storages[identity_id]
            storage.close()
            evicted = True
            break
        if not evicted:
            break


def _close_tenant_storages() -> None:
    """关闭所有已打开的租户数据库连接。"""
    with _tenant_storage_lock:
        for storage in _tenant_storages.values():
            storage.close()
        _tenant_storages.clear()
        _active_tenants.clear()


class _StorageRouter:
    """按当前请求身份选择 SQLiteStorage。"""

    def __init__(self, local_storage: SQLiteStorage) -> None:
        self.local_storage = local_storage

    def __getattr__(self, name: str) -> Any:
        context = _tenant_context.get()
        storage = (
            _tenant_storage(context[0])
            if context is not None else self.local_storage
        )
        return getattr(storage, name)


def _current_identity_id() -> str:
    """返回当前请求的身份键。"""
    context = _tenant_context.get()
    return context[0] if context is not None else "local"


def _current_upload_root() -> Path:
    """返回当前身份的托管上传目录。"""
    context = _tenant_context.get()
    return context[1] if context is not None else UPLOAD_ROOT


def _current_archive_dir() -> Path:
    """返回当前身份的归档目录。"""
    context = _tenant_context.get()
    return context[2] if context is not None else ARCHIVE_DIR


async def _save_upload(file: UploadFile, *, learning_source: bool = False) -> tuple[Path, int]:
    """校验并保存上传文件，隔离同名文件与路径穿越。"""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    supported = LEARNING_UPLOAD_SUFFIXES if learning_source else ALLOWED_UPLOAD_SUFFIXES
    if Path(filename).suffix.lower() not in supported:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 25 MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    upload_dir = _current_upload_root() / uuid.uuid4().hex
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
    root = _current_upload_root().resolve(strict=False)
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
_local_storage = SQLiteStorage(DATABASE_PATH)
_local_storage.init_schema()
_local_storage.ensure_interview_questions(SEED_QUESTIONS)
_accounts = AccountStore(DATABASE_PATH) if IDENTITY_MODE == "anonymous" else None
_storage: SQLiteStorage | _StorageRouter = _StorageRouter(_local_storage)

# =============== Models ===============

class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


class LLMCredentialRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=512)


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


class SourceRightsRequest(BaseModel):
    rights_status: Literal[
        "unconfirmed", "self_owned", "authorized", "public"
    ]
    sharing_scope: Literal["private", "restricted", "shareable"] = "private"
    note: str = Field(default="", max_length=500)


class DataDeleteRequest(BaseModel):
    confirmed: bool = False
    confirmation_token: str = Field(default="", max_length=64)


class DigitalHumanPlaybackRequest(BaseModel):
    text_length: int = Field(ge=1, le=5000)
    avatar_id: Literal["filemate-campus", "filemate-portrait"]
    voice_id: str = Field(min_length=1, max_length=160)
    provider: Literal["web_speech"] = "web_speech"
    context_id: str | None = Field(default=None, max_length=80)
    message_index: int | None = Field(default=None, ge=0)


class DigitalHumanPlaybackFinishRequest(BaseModel):
    status: Literal["completed", "stopped", "failed"]
    error_code: str = Field(default="", max_length=80)


# =============== App ===============

app = FastAPI(
    title="FileMate API",
    version=__version__,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-FileMate-Shutdown-Token", "X-FileMate-Action", "X-FileMate-LLM-Key"],
)


@app.middleware("http")
async def isolate_model_credentials(request: Request, call_next):
    """浏览器密钥只用于显式模型请求，不进入共享配置。"""
    from filemate.llm_client.request_credentials import (
        is_model_request,
        model_request_key,
        validate_api_key,
    )

    value = request.headers.get("X-FileMate-LLM-Key")
    if value is None:
        return await call_next(request)
    if (
        not is_model_request(request.method, request.url.path)
        or request.headers.get("origin") not in CORS_ORIGINS
        or request.headers.get("X-FileMate-Action") != "model"
    ):
        return JSONResponse(status_code=403, content={
            "success": False, "data": None, "error": "密钥仅允许用于受信页面的模型请求",
        })
    try:
        value = validate_api_key(value)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={
            "success": False, "data": None, "error": str(exc),
        })
    with model_request_key(value):
        return await call_next(request)


@app.middleware("http")
async def reject_untrusted_browser_origins(request: Request, call_next):
    """阻止不受信网页向本地 Sidecar 或网站 API 发起状态变更。"""
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin not in CORS_ORIGINS
    ):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "data": None,
                "error": "请求来源不受信任",
            },
        )
    return await call_next(request)


@app.middleware("http")
async def isolate_anonymous_workspace(request: Request, call_next):
    """在公网模式下把每个匿名浏览器路由到独立数据目录。"""
    if IDENTITY_MODE == "local":
        return await call_next(request)

    session_token = request.cookies.get(ACCOUNT_COOKIE_NAME)
    account = await run_in_threadpool(_accounts.resolve_session, session_token)
    request.state.account = account
    request.state.session_expired = bool(session_token and not account)
    if request.state.session_expired and request.url.path not in {
        "/api/auth/me", "/api/auth/login", "/api/auth/register", "/api/auth/logout",
        "/api/auth/recover", "/api/health", "/health",
    } and request.method != "OPTIONS":
        return JSONResponse(status_code=401, content={
            "success": False, "data": None, "error": "登录已过期，请重新登录或退出后以游客继续",
        })
    identity_id = _verify_identity_cookie(
        request.cookies.get(IDENTITY_COOKIE_NAME)
    )
    if identity_id and await run_in_threadpool(_accounts.workspace_claimed, identity_id):
        identity_id = None
    should_issue_cookie = identity_id is None
    if identity_id is None:
        identity_id = f"u_{uuid.uuid4().hex}"
    guest_identity_id = identity_id
    if account:
        identity_id = account["workspace_id"]
    tenant_root = DATA_DIR / "users" / identity_id
    context = (identity_id, tenant_root / "inbox", tenant_root / "archive")
    with _tenant_storage_lock:
        _active_tenants[identity_id] = _active_tenants.get(identity_id, 0) + 1
    token = _tenant_context.set(context)
    try:
        response = await call_next(request)
    finally:
        _tenant_context.reset(token)
        with _tenant_storage_lock:
            remaining = _active_tenants.get(identity_id, 1) - 1
            if remaining > 0:
                _active_tenants[identity_id] = remaining
            else:
                _active_tenants.pop(identity_id, None)
            _evict_tenant_storages()
    if should_issue_cookie:
        response.set_cookie(
            key=IDENTITY_COOKIE_NAME,
            value=_sign_identity(guest_identity_id),
            max_age=IDENTITY_COOKIE_MAX_AGE,
            httponly=True,
            secure=IS_PRODUCTION,
            samesite="lax",
            path="/",
        )
    return response


class AccountRegisterRequest(BaseModel):
    email: str = Field(max_length=254)
    display_name: str = Field(max_length=30)
    password: SecretStr = Field(max_length=128)
    keep_guest_data: bool = True
    remember: bool = True


class AccountLoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: SecretStr = Field(max_length=128)
    remember: bool = True


class AccountRecoverRequest(BaseModel):
    email: str = Field(max_length=254)
    recovery_code: SecretStr = Field(max_length=64)
    password: SecretStr = Field(max_length=128)


def _account_service(request: Request) -> AccountStore:
    """账号写入要求 JSON 和自定义头，避免跨站表单请求。"""
    if _accounts is None:
        raise HTTPException(409, "本地独立模式无需账号；网站模式支持邮箱注册和登录")
    if request.headers.get("x-filemate-action") != "account" or request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(403, "请通过 FileMate 账号页面操作")
    return _accounts


def _account_response(data: dict[str, Any], token: str | None = None, remember: bool = False) -> JSONResponse:
    """会话只进入 HttpOnly Cookie，不返回给前端脚本。"""
    response = JSONResponse(content={"success": True, "data": data, "error": None}, headers={"Cache-Control": "no-store"})
    if token:
        response.set_cookie(ACCOUNT_COOKIE_NAME, token, max_age=REMEMBER_SECONDS if remember else None,
                            httponly=True, secure=IS_PRODUCTION, samesite="lax", path="/")
    return response


@app.exception_handler(AccountError)
async def account_exception_handler(request: Request, exc: AccountError) -> JSONResponse:
    del request
    return JSONResponse(status_code=exc.status, content={"success": False, "data": None, "error": str(exc)},
                        headers={"Cache-Control": "no-store", **({"Retry-After": "900"} if exc.status == 429 else {})})


@app.get("/api/auth/me")
def account_me(request: Request) -> JSONResponse:
    account = getattr(request.state, "account", None)
    return _account_response({"user": account["user"] if account else None,
                              "enabled": _accounts is not None,
                              "expired": getattr(request.state, "session_expired", False)})


@app.post("/api/auth/register")
def account_register(request: Request, payload: AccountRegisterRequest) -> JSONResponse:
    service = _account_service(request)
    if getattr(request.state, "account", None):
        raise HTTPException(409, "请先退出当前账号再注册")
    workspace_id = _current_identity_id() if payload.keep_guest_data else f"u_{uuid.uuid4().hex}"
    user, token, recovery = service.register(payload.email, payload.password.get_secret_value(), payload.display_name, workspace_id, payload.remember)
    service.logout(request.cookies.get(ACCOUNT_COOKIE_NAME))
    return _account_response({"user": user, "recovery_code": recovery}, token, payload.remember)


@app.post("/api/auth/login")
def account_login(request: Request, payload: AccountLoginRequest) -> JSONResponse:
    service = _account_service(request)
    user, token = service.login(payload.email, payload.password.get_secret_value(), payload.remember)
    service.logout(request.cookies.get(ACCOUNT_COOKIE_NAME))
    return _account_response({"user": user}, token, payload.remember)


@app.post("/api/auth/logout")
def account_logout(request: Request) -> JSONResponse:
    service = _account_service(request)
    service.logout(request.cookies.get(ACCOUNT_COOKIE_NAME))
    response = _account_response({"user": None})
    response.delete_cookie(ACCOUNT_COOKIE_NAME, httponly=True, secure=IS_PRODUCTION, samesite="lax", path="/")
    return response


@app.post("/api/auth/recover")
def account_recover(request: Request, payload: AccountRecoverRequest) -> JSONResponse:
    service = _account_service(request)
    recovery = service.recover(payload.email, payload.recovery_code.get_secret_value(), payload.password.get_secret_value())
    return _account_response({"recovery_code": recovery})


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """未捕获异常兜底：保持统一结构，日志留痕但不向客户端泄露内部细节。"""
    del request
    logger.exception("未捕获异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": "服务器内部错误"},
    )


# 内存存储 session（简化版，后续可以连数据库）
_sessions: dict[tuple[str, str], dict] = {}


def _session_cache_get(session_id: str) -> dict[str, Any] | None:
    """读取当前身份的 Session 缓存。"""
    return _sessions.get((_current_identity_id(), session_id))


def _session_cache_set(session_id: str, value: dict[str, Any]) -> None:
    """写入当前身份的 Session 缓存。"""
    _sessions[(_current_identity_id(), session_id)] = value


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
    _session_cache_set(session_id, _deserialize_session(updated))
    return _enrich_session(updated)


def _confirmation_executor() -> ConfirmationExecutor:
    """使用当前服务存储与归档目录构造执行器。"""
    return ConfirmationExecutor(storage=_storage, archive_dir=_current_archive_dir())


def _require_local_settings_access(request: Request) -> None:
    """模型密钥只能由回环地址上的本地应用管理。"""
    client_host = request.client.host if request.client else ""
    bind_host = os.getenv("FILEMATE_HOST", "127.0.0.1").strip().lower()
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="模型密钥只能在本机应用中配置")
    if IS_PRODUCTION or IDENTITY_MODE != "local" or bind_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="公网服务禁止通过界面修改模型密钥")


def _llm_settings_status() -> dict[str, Any]:
    """返回不包含密钥正文的模型配置状态。"""
    api_key, source = resolve_api_key()
    return {
        "provider": "DeepSeek",
        "model": os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        "configured": bool(api_key),
        "source": source,
        "secure_storage_available": secure_store_available(),
    }


@app.get("/api/llm/status", response_model=ApiResponse)
def public_llm_status():
    """读取模型可用性与当前数据空间标识，不读取或返回浏览器密钥。"""
    import hashlib

    context = _tenant_context.get()
    scope = context[0] if context else "local"
    status = _llm_settings_status()
    return ApiResponse(success=True, data={
        **status, "credential_scope": hashlib.sha256(scope.encode()).hexdigest(),
    })


@app.post("/api/llm/test", response_model=ApiResponse)
def test_llm_connection(request: Request):
    """主动发起小额模型请求，验证鉴权与实际响应。"""
    import time

    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.llm_client.exceptions import LLMError

    if request.headers.get("origin") not in CORS_ORIGINS or request.headers.get("X-FileMate-Action") != "model":
        raise HTTPException(status_code=403, detail="请从应用设置主动测试模型连接")
    started = time.monotonic()
    try:
        config = LLMConfig.from_env()
        reply = LLMClient(config).call(
            messages=[{"role": "user", "content": "只回复OK"}],
            max_tokens=16, timeout=20, retry=1,
        )
        if not isinstance(reply, str) or not reply.strip():
            raise HTTPException(status_code=502, detail="模型返回空内容，请稍后重试")
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ApiResponse(success=True, data={
        "verified": True, "provider": "DeepSeek", "model": config.model,
        "latency_ms": round((time.monotonic() - started) * 1000),
    })

# =============== Routes ===============

@app.get("/")
def root():
    return {"message": "FileMate API", "version": __version__}


@app.get("/api/health", response_model=ApiResponse)
def health_check():
    """供 Web 与桌面壳检测本地服务状态。"""
    return ApiResponse(success=True, data={"version": __version__})


def _require_digital_human_enabled() -> None:
    """允许独立关闭数字人，不影响既有学习接口。"""
    if os.getenv("FILEMATE_ENABLE_DIGITAL_HUMAN", "1") == "0":
        raise HTTPException(status_code=503, detail="数字人功能已暂时关闭")


@app.get("/api/digital-human/playbacks", response_model=ApiResponse)
def list_digital_human_playbacks(limit: int = Query(30, ge=1, le=100)):
    """列出当前身份的播报元数据。"""
    _require_digital_human_enabled()
    return ApiResponse(
        success=True, data=_storage.list_digital_human_playbacks(limit=limit),
    )


@app.post("/api/digital-human/playbacks", response_model=ApiResponse)
def create_digital_human_playback(request: DigitalHumanPlaybackRequest):
    """记录开始播放，不接收或保存讲解正文。"""
    _require_digital_human_enabled()
    if (request.context_id is None) != (request.message_index is None):
        raise HTTPException(status_code=422, detail="会话和消息序号必须同时提供")
    if request.context_id is not None:
        context = _storage.get_document_context(request.context_id)
        if context is None:
            raise HTTPException(status_code=404, detail="学习会话不存在")
        history = context.get("chat_history") or []
        if request.message_index >= len(history):
            raise HTTPException(status_code=422, detail="讲解消息不存在")
        message = history[request.message_index]
        if message.get("role") != "assistant":
            raise HTTPException(status_code=422, detail="只能讲解已保存的 AI 回答")
        if len(str(message.get("content") or "").strip()) != request.text_length:
            raise HTTPException(status_code=409, detail="回答内容已变化，请重新打开讲解")
    playback = _storage.create_digital_human_playback(
        text_length=request.text_length,
        avatar_id=request.avatar_id,
        voice_id=request.voice_id,
        provider=request.provider,
        context_id=request.context_id,
        message_index=request.message_index,
    )
    return ApiResponse(success=True, data=playback)


@app.patch("/api/digital-human/playbacks/{playback_id}", response_model=ApiResponse)
def finish_digital_human_playback(
    playback_id: str, request: DigitalHumanPlaybackFinishRequest,
):
    """记录播放完成、用户停止或语音失败。"""
    _require_digital_human_enabled()
    playback = _storage.finish_digital_human_playback(
        playback_id, request.status, request.error_code,
    )
    if playback is None:
        raise HTTPException(status_code=404, detail="播报记录不存在")
    return ApiResponse(success=True, data=playback)


@app.delete("/api/digital-human/playbacks/{playback_id}", response_model=ApiResponse)
def delete_digital_human_playback(playback_id: str):
    """移除当前身份的一条播报元数据。"""
    _require_digital_human_enabled()
    return ApiResponse(
        success=True,
        data={"deleted": _storage.delete_digital_human_playback(playback_id)},
    )


@app.post(
    "/api/digital-human/playbacks/{playback_id}/restore",
    response_model=ApiResponse,
)
def restore_digital_human_playback(playback_id: str):
    """撤销播报记录软删除，不会重新播放语音。"""
    _require_digital_human_enabled()
    return ApiResponse(
        success=True,
        data={"restored": _storage.restore_digital_human_playback(playback_id)},
    )


@app.get("/settings/llm", response_model=ApiResponse)
def get_llm_settings(request: Request):
    """读取本机模型配置状态，绝不返回密钥正文。"""
    _require_local_settings_access(request)
    return ApiResponse(success=True, data=_llm_settings_status())


@app.put("/settings/llm", response_model=ApiResponse)
def update_llm_settings(request: Request, data: LLMCredentialRequest):
    """把用户自己的 DeepSeek 密钥写入操作系统安全凭据库。"""
    _require_local_settings_access(request)
    api_key = data.api_key.strip()
    if len(api_key) < 10 or any(character.isspace() for character in api_key):
        raise HTTPException(status_code=422, detail="API 密钥格式无效")
    try:
        set_stored_api_key(api_key)
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(success=True, data=_llm_settings_status())


@app.delete("/settings/llm", response_model=ApiResponse)
def remove_llm_settings(request: Request):
    """删除当前系统用户保存的 DeepSeek 密钥。"""
    _require_local_settings_access(request)
    try:
        removed = delete_stored_api_key()
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(
        success=True,
        data={**_llm_settings_status(), "removed": removed},
    )


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
        _session_cache_set(session.session_id, result)

        # 阶段级失败（损坏/加密文件）→ 返回 success=False，前端 ElMessage.error 已就绪
        if session.error:
            return ApiResponse(success=False, data=result, error=session.error)
        return ApiResponse(success=True, data=result)
    except Exception as exc:
        _managed_file_status(str(file_path), remove=True)
        logger.exception("处理失败: %s", file.filename)
        raise HTTPException(status_code=500, detail="文件处理失败") from exc


@app.get("/sessions/{session_id}", response_model=ApiResponse)
def get_session(session_id: str):
    """获取 session 详情。"""
    session = _session_cache_get(session_id)
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
    session = _session_cache_get(session_id) or _storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not data.accepted:
        _storage.update_session(session_id, status="skipped")
        _storage.log_operation(session_id, "reject", detail="用户跳过")
        updated = _storage.get_session(session_id)
        if updated is not None:
            _session_cache_set(session_id, _deserialize_session(updated))
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
        _session_cache_set(session_id, _deserialize_session(updated))
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
        _session_cache_set(session_id, _deserialize_session(updated))
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
    if _storage.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    execution = _storage.get_active_execution(session_id)
    ics_path_value = execution.get("ics_path") if execution else None
    if not ics_path_value:
        raise HTTPException(status_code=404, detail="ICS file not found")
    ics_path = Path(str(ics_path_value)).expanduser().resolve(strict=False)
    allowed_root = _current_archive_dir().resolve(strict=False)
    if ics_path.suffix.lower() != ".ics" or not ics_path.is_relative_to(allowed_root):
        raise HTTPException(status_code=403, detail="ICS file path is outside workspace")
    if not ics_path.is_file():
        raise HTTPException(status_code=404, detail="ICS file not found")
    content = ics_path.read_text(encoding="utf-8")
    return ApiResponse(success=True, data=content)


def _public_source(
    source: dict[str, Any],
    *,
    include_text: bool = False,
) -> dict[str, Any]:
    """过滤内部工作区与服务器文件系统字段。"""
    hidden = {"source_path", "workspace_id"}
    if not include_text:
        hidden.add("raw_text")
    return {key: value for key, value in source.items() if key not in hidden}


@app.get("/knowledge/sources", response_model=ApiResponse)
def list_knowledge_sources(limit: int = Query(50, ge=1, le=200)):
    """列出本地工作区中的持久化资料源。"""
    sources = []
    for source in _storage.list_sources(limit=limit):
        item = _public_source(source)
        item["text_length"] = len(source.get("raw_text", ""))
        sources.append(item)
    return ApiResponse(success=True, data=sources)


class CodingSubmissionRequest(BaseModel):
    problem_id: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=100000)
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    language: Literal["cpp17"] = "cpp17"


class CodingReviewRequest(BaseModel):
    mode: Literal["local", "llm"] = "local"
    allow_external_model: bool = False


class CodingNotesRequest(BaseModel):
    notes: str = Field(max_length=8000)


def _require_programming_enabled() -> None:
    if os.getenv("FILEMATE_ENABLE_PROGRAMMING", "1") == "0":
        raise HTTPException(status_code=503, detail="编程评测暂未启用，原有学习功能仍可使用")


def _coding_repository():
    from filemate.programming.repository import CodingRepository

    context = _tenant_context.get()
    return CodingRepository(_tenant_storage(context[0]) if context else
                            (_storage.local_storage if isinstance(_storage, _StorageRouter) else _storage))


def _coding_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, KeyError) else 409,
                         detail="提交或题目不存在" if isinstance(exc, KeyError) else str(exc))


@app.get("/api/programming/status", response_model=ApiResponse)
def programming_status():
    from filemate.programming.service import status

    _require_programming_enabled()
    return ApiResponse(success=True, data=status())


@app.post("/api/programming/setup", response_model=ApiResponse)
def programming_setup():
    from filemate.programming.service import status
    from filemate.programming.toolchain import prepare_toolchain
    from filemate.programming.windows_sandbox import SandboxUnavailable

    _require_programming_enabled()
    try:
        if os.name == "nt":
            prepare_toolchain()
        result = status(force=True)
    except (SandboxUnavailable, OSError) as exc:
        logger.warning("编程环境准备失败 (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="无法准备隔离环境，请检查工具链或部署代理后重试") from exc
    repository = _coding_repository()
    with repository.storage._write_lock:
        repository._event(None, "environment_checked", {"ready": result["ready"]})
        repository.storage._conn().commit()
    return ApiResponse(success=True, data=result)


@app.get("/api/programming/problems", response_model=ApiResponse)
def programming_problems():
    from filemate.programming.problems import PROBLEMS, public_problem

    _require_programming_enabled()
    return ApiResponse(success=True, data=[public_problem(problem) for problem in PROBLEMS])


@app.get("/api/programming/overview", response_model=ApiResponse)
def programming_overview():
    from filemate.programming.feedback import evidence_profile
    from filemate.programming.service import recover

    _require_programming_enabled()
    repository = _coding_repository()
    recover(repository)
    submissions = repository.list(100)
    return ApiResponse(success=True, data={"submissions": submissions[:100],
                                          "profile": evidence_profile(repository.evidence()),
                                          "evidence_scope": "all_active_completed_submissions",
                                          "events": repository.events()})


@app.post("/api/programming/submissions", response_model=ApiResponse)
def create_coding_submission(request: CodingSubmissionRequest):
    from filemate.programming.problems import get_problem

    _require_programming_enabled()
    if not request.code.strip():
        raise HTTPException(status_code=422, detail="请输入 C++ 代码")
    if len(request.code.encode("utf-8")) > 100000:
        raise HTTPException(status_code=422, detail="源代码不能超过 100 KB")
    try:
        result = _coding_repository().create(get_problem(request.problem_id), request.code, request.request_key)
    except (KeyError, ValueError) as exc:
        raise _coding_error(exc) from exc
    return ApiResponse(success=True, data=result)


@app.get("/api/programming/submissions/{submission_id}", response_model=ApiResponse)
def get_coding_submission(submission_id: str):
    _require_programming_enabled()
    try:
        return ApiResponse(success=True, data=_coding_repository().get(submission_id))
    except KeyError as exc:
        raise _coding_error(exc) from exc


@app.post("/api/programming/submissions/{submission_id}/run", response_model=ApiResponse)
def run_coding_submission(submission_id: str):
    from filemate.programming.service import execute
    from filemate.programming.windows_sandbox import SandboxUnavailable

    _require_programming_enabled()
    try:
        result = execute(_coding_repository(), submission_id)
    except (KeyError, ValueError) as exc:
        raise _coding_error(exc) from exc
    except SandboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(success=True, data=result)


@app.post("/api/programming/submissions/{submission_id}/review", response_model=ApiResponse)
def review_coding_submission(submission_id: str, request: CodingReviewRequest):
    from filemate.execution.storage import _now_iso
    from filemate.programming.feedback import local_feedback, model_feedback

    _require_programming_enabled()
    repository = _coding_repository()
    try:
        submission = repository.get(submission_id)
    except KeyError as exc:
        raise _coding_error(exc) from exc
    if submission["status"] != "completed" or not submission["active"] or submission["data_error"]:
        raise HTTPException(status_code=409, detail="请先完成有效评测，再生成代码复盘")
    if request.mode == "llm" and not request.allow_external_model:
        raise HTTPException(status_code=422, detail="请确认允许将题面、代码和测试结果发送给已配置的模型")
    provider = "external_model" if request.mode == "llm" else "local_rules"
    if isinstance(submission.get("review"), dict) and submission["review"].get("provider") == provider:
        return ApiResponse(success=True, data=submission)
    try:
        if request.mode == "llm":
            from filemate.llm_client import LLMClient

            review = model_feedback(LLMClient(), submission)
        else:
            review = local_feedback(submission)
    except Exception as exc:
        logger.warning("代码模型复盘失败 (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="模型复盘失败，判题与已有复盘均已保留，可稍后重试") from exc
    review["created_at"] = _now_iso()
    with repository.storage._write_lock:
        latest = repository.get(submission_id)
        if not latest["active"] or latest["data_error"]:
            raise HTTPException(status_code=409, detail="提交状态已变化，请刷新记录")
        result = repository.update(submission_id, payload={"review": review}, event="review_saved")
    return ApiResponse(success=True, data=result)


@app.post("/api/programming/submissions/{submission_id}/notes", response_model=ApiResponse)
def save_coding_notes(submission_id: str, request: CodingNotesRequest):
    _require_programming_enabled()
    repository = _coding_repository()
    try:
        with repository.storage._write_lock:
            row = repository.get(submission_id)
            if row["status"] in {"queued", "running"} or not row["active"]:
                raise ValueError("请在评测结束后保存有效提交的笔记")
            result = repository.update(submission_id, payload={"notes": request.notes}, event="notes_saved")
    except (KeyError, ValueError) as exc:
        raise _coding_error(exc) from exc
    return ApiResponse(success=True, data=result)


@app.post("/api/programming/submissions/{submission_id}/{action}", response_model=ApiResponse)
def transition_coding_submission(submission_id: str, action: Literal["cancel", "undo", "restore"]):
    from filemate.programming.service import cancel

    _require_programming_enabled()
    repository = _coding_repository()
    try:
        result = cancel(repository, submission_id) if action == "cancel" else repository.transition(submission_id, action)
    except (KeyError, ValueError) as exc:
        raise _coding_error(exc) from exc
    return ApiResponse(success=True, data=result)


class GraphDraftRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=128)
    mode: Literal["local", "llm"] = "local"
    allow_external_model: bool = False


class GraphPlanRequest(BaseModel):
    evidence_revision: str = Field(min_length=64, max_length=64)


def _require_graph_enabled() -> None:
    if os.getenv("FILEMATE_ENABLE_KNOWLEDGE_GRAPH", "1") == "0":
        raise HTTPException(status_code=503, detail="知识图谱暂未启用，原有学习功能仍可使用")


@app.get("/api/knowledge-graph", response_model=ApiResponse)
def knowledge_graph(limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0, le=1000000),
                    q: str = Query("", max_length=160), batch_offset: int = Query(0, ge=0, le=1000000)):
    from filemate.study.graph_projection import graph_page
    from filemate.study.knowledge_graph import build_graph

    _require_graph_enabled()
    with _storage.read_snapshot() as snapshot:
        return ApiResponse(success=True, data=graph_page(build_graph(snapshot), limit=limit,
                           offset=offset, q=q, batch_offset=batch_offset))


@app.get("/api/knowledge-graph/nodes/{node_id}", response_model=ApiResponse)
def graph_node_detail(node_id: str):
    from filemate.study.knowledge_graph import build_graph

    _require_graph_enabled()
    with _storage.read_snapshot() as snapshot:
        node = next((item for item in build_graph(snapshot)["nodes"] if item["id"] == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail="知识点不存在或来源已变化")
    return ApiResponse(success=True, data=node)


@app.get("/api/knowledge-graph/batches/{batch_id}", response_model=ApiResponse)
def graph_batch_detail(batch_id: str):
    _require_graph_enabled()
    batch = _storage.get_graph_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="图谱批次不存在")
    return ApiResponse(success=True, data={**batch, "payload_loaded": True})


@app.post("/api/knowledge-graph/drafts", response_model=ApiResponse)
def create_graph_draft(request: GraphDraftRequest):
    from filemate.study.knowledge_graph import (
        INPUT_LIMIT,
        LLMGraphProvider,
        extract_local,
        validate_graph,
    )

    _require_graph_enabled()
    with _storage._write_lock:
        source = _storage.get_source(request.source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="资料不存在")
        revision = _storage.get_source_revision(request.source_id)
        chunks = _storage.list_source_chunks(request.source_id)
    if request.mode == "llm" and not request.allow_external_model:
        raise HTTPException(status_code=422, detail="请确认允许将资料正文发送给已配置的模型")
    text = source["raw_text"][:INPUT_LIMIT]
    try:
        if request.mode == "llm":
            from filemate.llm_client import LLMClient, LLMConfig

            raw = LLMGraphProvider(LLMClient(LLMConfig.from_env())).extract(text)
        else:
            raw = extract_local(text)
        payload = validate_graph(raw, text, request.source_id, chunks)
        payload["source_truncated"] = len(source["raw_text"]) > INPUT_LIMIT
        payload["external_model_authorized"] = request.mode == "llm"
    except Exception as exc:
        # 只记录错误类型，供应商异常可能包含密钥或用户正文。
        logger.warning("知识图谱提取失败 (%s)", type(exc).__name__)
        try:
            _storage.save_graph_batch(request.source_id, revision, request.mode,
                                      {"nodes": [], "edges": []},
                                      error_code=type(exc).__name__)
        except ValueError:
            raise HTTPException(status_code=409, detail="提取期间资料已变化，请刷新后重试") from exc
        detail = ("未能提取可核对的知识点。可使用标题、术语定义或明确关系句，或选择模型提取。"
                  if isinstance(exc, (ValueError, TypeError)) else "模型提取失败，原图谱未改变，请稍后重试或使用本地提取。")
        raise HTTPException(status_code=422 if isinstance(exc, (ValueError, TypeError)) else 502, detail=detail) from exc
    try:
        batch = _storage.save_graph_batch(request.source_id, revision, request.mode, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="提取期间资料已变化，请刷新后重试") from exc
    return ApiResponse(success=True, data=batch)


@app.post("/api/knowledge-graph/batches/{batch_id}/{action}", response_model=ApiResponse)
def change_graph_batch(batch_id: str, action: Literal["confirm", "undo", "restore"]):
    _require_graph_enabled()
    try:
        batch = _storage.transition_graph_batch(batch_id, action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="图谱批次不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(success=True, data=batch)


def _graph_plan_suggestion(node_id: str) -> dict[str, Any]:
    from filemate.study.knowledge_graph import build_graph, recommend_plan

    try:
        return recommend_plan(build_graph(_storage), node_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="知识点不存在或资料已变化，请刷新图谱") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/knowledge-graph/nodes/{node_id}/plan", response_model=ApiResponse)
def preview_graph_plan(node_id: str):
    _require_graph_enabled()
    with _storage._write_lock:
        return ApiResponse(success=True, data=_graph_plan_suggestion(node_id))


@app.post("/api/knowledge-graph/nodes/{node_id}/plan", response_model=ApiResponse)
def confirm_graph_plan(node_id: str, request: GraphPlanRequest):
    from filemate.study.knowledge_graph import to_study_plan

    _require_graph_enabled()
    with _storage._write_lock:
        suggestion = _graph_plan_suggestion(node_id)
        if suggestion["evidence_revision"] != request.evidence_revision:
            raise HTTPException(status_code=409, detail="学习证据已变化，请重新预览后确认")
        result = _storage.save_graph_study_plan(
            suggestion["source_id"], node_id, request.evidence_revision, to_study_plan(suggestion),
        )
    return ApiResponse(success=True, data=result)


@app.post("/api/knowledge-graph/plans/{plan_id}/{action}", response_model=ApiResponse)
def change_graph_plan(plan_id: str, action: Literal["undo", "restore"]):
    _require_graph_enabled()
    try:
        result = (_storage.undo_graph_study_plan(plan_id) if action == "undo"
                  else _storage.restore_graph_study_plan(plan_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="图谱学习计划不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(success=True, data=result)


@app.post("/knowledge/import", response_model=ApiResponse)
async def import_learning_source(file: Annotated[UploadFile, File()]):
    """仅在本地解析和入库，不调用外部模型。"""
    from filemate.perception import FileParser
    from filemate.understanding.retrieval import split_document

    path, size = await _save_upload(file, learning_source=True)
    retained = False
    try:
        parsed = await run_in_threadpool(FileParser().parse, str(path))
        text = parsed.get("raw_text", "")
        if parsed.get("error") or not text.strip():
            raise HTTPException(status_code=422, detail="无法提取正文，请使用包含文字的资料")
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"filemate:local:{file_hash}").hex
        source = _storage.get_source(stable_id)
        if source is None:
            source_id = _storage.save_source(
                original_name=path.name, source_path=str(path), raw_text=text,
                media_type=mimetypes.guess_type(path.name)[0] or "",
                file_hash=file_hash, metadata={"size_bytes": size},
            )
            retained = True
            _storage.replace_source_chunks(source_id, split_document(text))
            source = _storage.get_source(source_id)
        return ApiResponse(
            success=True,
            data=_public_source(source, include_text=True),
        )
    finally:
        if not retained:
            # 只清理此次上传生成的副本，不触碰用户原件或已有资料。
            path.unlink(missing_ok=True)
            path.parent.rmdir()


@app.post("/knowledge/sources/{source_id}/contexts", response_model=ApiResponse)
def start_source_context(source_id: str):
    """为已有资料新建可恢复会话，不生成产物或调用模型。"""
    source = _storage.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if not source["raw_text"].strip():
        raise HTTPException(status_code=422, detail="资料没有可用正文，请重新导入")
    ctx_id = uuid.uuid4().hex
    _storage.save_document_context(
        ctx_id=ctx_id, source_id=source_id, context_text=source["raw_text"],
        metadata={"filename": source["original_name"], "origin": "learning_workspace"},
    )
    return ApiResponse(success=True, data=_storage.get_document_context(ctx_id))


class WorkspaceArtifactRequest(BaseModel):
    artifact_type: Literal["summary", "notes", "knowledge_cards", "questions"]
    count: int = Field(default=5, ge=1, le=10)
    allow_external_model: bool = False


@app.post("/knowledge/sources/{source_id}/artifacts", response_model=ApiResponse)
def generate_source_artifact(source_id: str, request: WorkspaceArtifactRequest):
    """复用已入库正文，生成产物但不重建资料或清空会话。"""
    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.understanding.workspace import generate_workspace_artifact

    source = _storage.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if not request.allow_external_model:
        raise HTTPException(status_code=422, detail="请先确认允许将资料正文发送给已配置的模型")
    if not source["raw_text"].strip():
        raise HTTPException(status_code=422, detail="资料没有可用正文")
    try:
        content = generate_workspace_artifact(
            LLMClient(LLMConfig.from_env()), text=source["raw_text"],
            title=source["original_name"], kind=request.artifact_type, count=request.count,
        )
    except Exception as exc:
        logger.warning("学习产物生成失败 (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="生成失败，未保存无效内容，请稍后重试") from exc
    labels = {"summary": "摘要", "notes": "笔记", "knowledge_cards": "知识卡", "questions": "练习题"}
    input_limit = 2500 if request.artifact_type == "questions" else 12000
    artifact = _storage.save_source_artifact(
        source_id=source_id, artifact_type=request.artifact_type, content=content,
        title=f"{source['original_name']} · {labels[request.artifact_type]}",
        metadata={"origin": "learning_workspace", "external_model_authorized": True,
                  "input_characters": min(len(source["raw_text"]), input_limit),
                  "source_truncated": len(source["raw_text"]) > input_limit},
    )
    if artifact is None:
        raise HTTPException(status_code=409, detail="生成期间资料已被删除，结果未保存")
    return ApiResponse(success=True, data=artifact)


@app.get("/knowledge/sources/{source_id}", response_model=ApiResponse)
def get_knowledge_source(source_id: str):
    """读取单个资料源及其文本。"""
    source = _storage.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return ApiResponse(
        success=True,
        data=_public_source(source, include_text=True),
    )


@app.get("/knowledge/sources/{source_id}/lineage", response_model=ApiResponse)
def get_knowledge_source_lineage(source_id: str):
    """读取从原始资料到学习证据的可追溯资产链。"""
    lineage = _storage.get_source_lineage(source_id)
    if lineage is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    public_lineage = dict(lineage)
    if isinstance(public_lineage.get("source"), dict):
        public_lineage["source"] = _public_source(
            public_lineage["source"],
            include_text=True,
        )
    return ApiResponse(success=True, data=public_lineage)


@app.put("/knowledge/sources/{source_id}/rights", response_model=ApiResponse)
def update_source_rights(source_id: str, request: SourceRightsRequest):
    """声明资料权利来源与允许的分享范围。"""
    from filemate.core.trusted_agents import select_agents

    try:
        rights = _storage.set_source_rights(
            source_id=source_id,
            rights_status=request.rights_status,
            sharing_scope=request.sharing_scope,
            note=request.note,
        )
    except ValueError as exc:
        status_code = 404 if "不存在" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    run = _storage.create_agent_run(
        task_type="source_rights",
        goal="校验资料授权声明与分享边界",
        selected_agents=select_agents("source_rights"),
        context_refs={"source_id": source_id},
    )
    _storage.append_agent_step(
        run_id=run["run_id"],
        agent_name="安全 Agent",
        input_refs={"source_id": source_id},
        output_summary=(
            f"授权状态已设为 {request.rights_status}，"
            f"分享范围为 {request.sharing_scope}"
        ),
    )
    _storage.finish_agent_run(run["run_id"])
    _storage.save_agent_memory(
        memory_type="operation",
        scope_id=source_id,
        source_type="source_rights",
        source_id=source_id,
        summary=(
            f"资料授权：{request.rights_status}；"
            f"分享范围：{request.sharing_scope}"
        ),
        allowed_agents=["安全 Agent"],
    )
    return ApiResponse(success=True, data=rights)


@app.get("/trust/overview", response_model=ApiResponse)
def get_trust_overview(limit: int = Query(50, ge=1, le=200)):
    """汇总真实 Agent 轨迹、共享记忆元数据与资料授权。"""
    from filemate.core.trusted_agents import describe_roles

    return ApiResponse(
        success=True,
        data={
            "roles": describe_roles(),
            "runs": _storage.list_agent_runs(limit=limit),
            "memories": _storage.list_agent_memories(limit=limit),
            "source_rights": _storage.list_source_rights(limit=limit),
            "mode": (
                "local"
                if os.getenv("FILEMATE_INTERVIEW_LOCAL_ONLY") == "1"
                else "local_with_authorized_model"
            ),
            "guarantees": [
                "资料正文保存在本机工作区，授权状态默认未确认、仅自己可用",
                "Agent 轨迹只记录来源标识和执行摘要，不复制面试回答原文",
                "共享记忆可查看、可单条删除，删除后不再向 Agent 提供",
                "授权未确认的资料不能调整为受限分享或可分享",
            ],
        },
    )


@app.delete("/agents/memories/{memory_id}", response_model=ApiResponse)
def delete_agent_memory(memory_id: str):
    """撤销一条共享记忆的后续使用权限。"""
    from filemate.core.trusted_agents import select_agents

    deleted = _storage.soft_delete_agent_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="共享记忆不存在或已删除")
    run = _storage.create_agent_run(
        task_type="memory_deletion",
        goal="撤销共享记忆的后续使用权限",
        selected_agents=select_agents("memory_deletion"),
        context_refs={"memory_id": memory_id},
    )
    _storage.append_agent_step(
        run_id=run["run_id"],
        agent_name="安全 Agent",
        input_refs={"memory_id": memory_id},
        output_summary="共享记忆已撤销，后续 Agent 查询默认不可见",
    )
    _storage.finish_agent_run(run["run_id"])
    return ApiResponse(success=True, data={"deleted": True})


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
    return ApiResponse(success=True, data=[_artifact_integrity(item) for item in artifacts])


def _artifact_integrity(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact["artifact_type"] != "questions":
        return artifact
    from filemate.study.question_validation import validate_question

    try:
        questions = artifact["content"]
        if not isinstance(questions, list) or not questions:
            raise ValueError("题集为空")
        for question in questions:
            validate_question(question, legacy=True)
    except (ValueError, TypeError):
        return {**artifact, "metadata": {**artifact.get("metadata", {}), "question_data_error": True}}
    return artifact


@app.get("/knowledge/artifacts/{artifact_id}", response_model=ApiResponse)
def get_knowledge_artifact(artifact_id: str):
    """读取可编辑的学习产物详情。"""
    artifact = _storage.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="学习产物不存在")
    return ApiResponse(success=True, data=_artifact_integrity(artifact))


@app.patch("/knowledge/artifacts/{artifact_id}", response_model=ApiResponse)
def update_knowledge_artifact(
    artifact_id: str,
    request: ArtifactUpdateRequest,
):
    """保存用户对摘要、笔记、卡片或题目的修订。"""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="标题不能为空")
    existing = _storage.get_artifact(artifact_id)
    if existing and existing["artifact_type"] == "questions" and existing["content"] != request.content:
        from filemate.study.question_validation import validate_question

        try:
            if not isinstance(request.content, list) or not 1 <= len(request.content) <= 1000:
                raise ValueError("题集必须包含1至1000道题")
            normalized = [validate_question(item, legacy=True) for item in request.content]
            if len({item["stem"].casefold() for item in normalized}) != len(normalized):
                raise ValueError("题干重复")
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"题集校验失败：{exc}") from exc
    if existing and isinstance(existing.get("metadata"), dict) and existing["metadata"].get("origin") == "career_plan":
        raise HTTPException(status_code=409, detail="岗位学习计划保留确认时的证据，请更新进度或重新预览新计划")
    if existing and existing["artifact_type"] in {"coding_submission", "interview_report", "career_training", "skill_tree", "resume_profile", "resume", "semester", "semester_history", "growth_report"}:
        raise HTTPException(status_code=409, detail="评测报告不能直接修改，请在对应工作台更新原始记录或复盘笔记")
    try:
        artifact = _storage.update_artifact(
            artifact_id,
            title=title[:200],
            content=request.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


class _StagedSourceFile:
    def __init__(self, path_value: str, shared: bool):
        self.status = _managed_file_status(path_value)
        self.status.pop("path", None)
        self.status["shared"] = shared
        self.original = Path(path_value).resolve()
        self.staged: Path | None = None
        self.backup: bytes | None = None
        if self.status["managed"] and self.status["exists"] and not shared:
            self.staged = self.original.with_name(".delete-" + uuid.uuid4().hex)
            self.original.rename(self.staged)
            self.status["removed"] = True

    def rollback(self) -> None:
        if self.staged is not None:
            if self.staged.exists():
                self.staged.rename(self.original)
            elif self.backup is not None:
                self.original.parent.mkdir(parents=True, exist_ok=True)
                with self.original.open("xb") as stream:
                    stream.write(self.backup)

    def finish(self) -> None:
        if self.staged is not None:
            self.backup = self.staged.read_bytes()
            self.staged.unlink()
            try:
                self.original.parent.rmdir()
            except OSError:
                pass


@app.get("/knowledge/sources/{source_id}/delete-preview", response_model=ApiResponse)
def preview_knowledge_source_deletion(source_id: str):
    preview = _storage.source_deletion_preview(source_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Source not found")
    preview["managed_file"] = _managed_file_status(preview.pop("source_path"))
    preview["managed_file"].pop("path", None)
    return ApiResponse(success=True, data=preview)


@app.delete("/knowledge/sources/{source_id}", response_model=ApiResponse)
def delete_knowledge_source(source_id: str, request: DataDeleteRequest | None = None):
    if request is None or not request.confirmed or not request.confirmation_token:
        if _storage.get_source(source_id) is None:
            raise HTTPException(status_code=404, detail="Source not found")
        raise HTTPException(status_code=422, detail="删除前必须预览并明确确认")
    try:
        result = _storage.confirmed_source_delete(
            source_id, request.confirmation_token, _StagedSourceFile,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="文件清理失败，请重新检查资料状态") from exc
    return ApiResponse(success=True, data=result)


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
    retained = False
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
        retained = True

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
    finally:
        if not retained:
            _managed_file_status(str(file_path), remove=True)


@app.post("/ai/knowledge-cards", response_model=ApiResponse)
async def ai_knowledge_cards(
    file: Annotated[UploadFile, File()],
    num_cards: Annotated[int, Form()] = 10,
    card_format: Annotated[str, Form()] = "front_back",
):
    """AI知识卡生成：上传PDF/文档，生成AI知识卡片。"""
    file_path, _ = await _save_upload(file)
    retained = False
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
        retained = True

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
    finally:
        if not retained:
            _managed_file_status(str(file_path), remove=True)


@app.post("/ai/questions", response_model=ApiResponse)
async def ai_questions(
    file: Annotated[UploadFile, File()],
    question_types: Annotated[str | None, Form()] = None,
    num_questions: Annotated[int, Form(ge=1, le=30)] = 10,
):
    """AI题目提取：上传PDF/文档，提取练习题目。"""
    file_path, _ = await _save_upload(file)
    retained = False
    logger.info("[AI Questions] Received file: %s", file_path.name)

    try:
        # 解析文件获取文本
        from filemate.perception import FileParser
        parser = FileParser()
        parsed = parser.parse(str(file_path))
        if parsed.get("error"):
            raise HTTPException(status_code=422, detail=str(parsed["error"]))
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
        requested_types = [_map_type(t) for t in types_list] if types_list else ["choice"]
        types_to_generate = list(dict.fromkeys(requested_types))
        per_type, remainder = divmod(num_questions, len(types_to_generate))
        generation_errors: list[str] = []
        for index, qtype in enumerate(types_to_generate):
            requested_count = per_type + (1 if index < remainder else 0)
            if requested_count == 0:
                continue
            try:
                batch = generate_questions_with_llm(
                    llm=llm,
                    subject=subject,
                    knowledge_point=knowledge_point,
                    count=requested_count,
                    question_type=qtype,
                    context=chunks,
                )
                all_questions.extend(batch)
            except RuntimeError as exc:
                generation_errors.append(str(exc))
                continue

        if not all_questions:
            logger.warning("AI 题目生成无有效结果: %s", generation_errors)
            raise HTTPException(status_code=502, detail="AI 题目生成失败")
        questions = all_questions[:num_questions]

        ctx_id, source_id, artifact_id = _persist_ai_context(
            file_path=file_path,
            text=text,
            artifact_type="questions",
            content=questions,
            title=f"{file_path.stem} · 练习题",
            metadata={"count": len(questions), "types": types_list or []},
        )
        retained = True

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
    finally:
        if not retained:
            _managed_file_status(str(file_path), remove=True)


@app.post("/ai/notes", response_model=ApiResponse)
async def ai_notes(
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()] = "outline",
):
    """AI笔记提取：上传PDF/文档，提取结构化笔记。"""
    file_path, _ = await _save_upload(file)
    retained = False
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
        retained = True

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
    finally:
        if not retained:
            _managed_file_status(str(file_path), remove=True)


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
    retained = False
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
        retained = True
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
    finally:
        if not retained:
            _managed_file_status(str(file_path), remove=True)


class ChatRequest(BaseModel):
    ctx_id: str
    question: str
    chat_history: list[dict] | None = None
    mode: Literal["answer", "socratic", "feynman"] = "answer"


class QuizAttemptRequest(BaseModel):
    artifact_id: str
    question_index: int
    user_answer: str
    expected_question: dict[str, Any] | None = None


class InterviewStartRequest(BaseModel):
    target_role: str = Field(max_length=120)
    scenario: Literal["求职面试", "竞赛答辩", "保研复试", "知识讲解"] = "求职面试"
    difficulty: Literal["入门", "标准", "压力面"] = "标准"
    source_id: str | None = Field(default=None, max_length=64)
    focus_wrong_id: str | None = Field(default=None, max_length=64)
    goal_id: str | None = Field(default=None, max_length=64)
    allow_external_analysis: bool | None = None


class InterviewFluencyMarker(BaseModel):
    second: float = Field(ge=0, le=3600)
    kind: Literal["long_pause", "filler"]
    label: str = Field(min_length=1, max_length=80)


class InterviewFluencyMetrics(BaseModel):
    duration_seconds: float = Field(ge=0, le=3600)
    filler_count: int = Field(default=0, ge=0, le=100)
    long_pause_count: int = Field(default=0, ge=0, le=100)
    source: Literal["speech_recognition"] = "speech_recognition"
    markers: list[InterviewFluencyMarker] = Field(default_factory=list, max_length=100)
    recording_offset_seconds: float | None = Field(default=None, ge=0, le=1800, allow_inf_nan=False)


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    fluency_metrics: InterviewFluencyMetrics | None = None
    question_index: int | None = Field(default=None, ge=0, le=100)
    request_key: str | None = Field(default=None, min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    visual_metrics: VisualMetrics | None = None


class InterviewAnalysisRequest(BaseModel):
    external_consent: bool = False


class InterviewPrivacyRequest(BaseModel):
    confirmed: bool = False
    confirmation_token: str = Field(default="", max_length=64)


class InterviewQuestionCreate(BaseModel):
    scenario: Literal["求职面试", "竞赛答辩", "保研复试", "知识讲解"]
    difficulty: Literal["入门", "标准", "压力面"]
    text: str = Field(min_length=1, max_length=1000)
    enabled: bool = True


class InterviewQuestionUpdate(BaseModel):
    scenario: Literal["求职面试", "竞赛答辩", "保研复试", "知识讲解"] | None = None
    difficulty: Literal["入门", "标准", "压力面"] | None = None
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    enabled: bool | None = None


class StudyPlanDayRequest(BaseModel):
    completed: bool


class DailyCoachPreferencesRequest(BaseModel):
    available_minutes: int = Field(ge=10, le=240)
    item_order: list[str] = Field(default_factory=list, max_length=50)


class ReverseGoalRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    goal_type: Literal["exam", "competition", "job", "postgraduate", "custom"]
    deadline: date
    target_score: int | None = Field(default=None, ge=0, le=100)
    source_id: str | None = Field(default=None, max_length=64)


class GoalTaskUpdateRequest(BaseModel):
    completed: bool


class WrongDiagnosisUpdateRequest(BaseModel):
    error_cause: Literal[
        "unconfirmed",
        "concept_gap",
        "memory_gap",
        "reasoning_break",
        "expression_gap",
        "option_confusion",
        "careless",
    ]
    note: str = Field(default="", max_length=300)


def _answer_score(user_answer: str, reference_answer: str) -> float:
    """计算适用于客观题与短答案的稳定相似度。"""
    def normalize(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())

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


def _goal_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """把目标 Artifact 转成前端合同。"""
    content = dict(artifact.get("content") or {})
    content["tasks"] = [dict(task) for task in content.get("tasks") or []]
    for task in content["tasks"]:
        reason = _oral_evidence_invalid_reason(task)
        if reason:
            task["status"] = "invalidated"
            task["invalidated_reason"] = reason
    content["goal_id"] = artifact["artifact_id"]
    content["created_at"] = artifact["created_at"]
    content["updated_at"] = artifact["updated_at"]
    return content


def _oral_evidence_invalid_reason(task: dict[str, Any]) -> str | None:
    """核对口头训练任务引用的作答、错题和资料版本。"""
    if task.get("task_id") != "explain-wrong-aloud":
        return None
    evidence = task.get("evidence_ref") or {}
    if (not evidence.get("attempt_id") or not evidence.get("source_revision")
            or not evidence.get("question_revision")
            or not evidence.get("diagnosis_revision")):
        return "旧任务缺少作答或资料版本证据，请重新规划。"
    wrong = _storage.get_wrong_question(str(task.get("focus_wrong_id") or ""))
    if wrong is None or wrong.get("source_id") != task.get("source_id"):
        return "原错题或关联资料已不存在，请重新规划。"
    if wrong.get("mastered"):
        return "这道错题已通过复练掌握，请重新规划。"
    if (wrong.get("artifact_id") != evidence.get("artifact_id")
            or wrong.get("question_index") != evidence.get("question_index")):
        return "错题对应题目已变化，请重新规划。"
    artifact = _storage.get_artifact(str(wrong["artifact_id"]))
    questions = artifact.get("content") if artifact else None
    index = int(wrong["question_index"])
    if (not isinstance(questions, list) or index >= len(questions)
            or _question_revision(questions[index]) != evidence["question_revision"]):
        return "原练习题内容已变化，请重新规划。"
    latest = _storage.get_latest_wrong_attempt(str(wrong["wrong_id"]))
    if latest is None or latest["attempt_id"] != evidence["attempt_id"]:
        return "这道题已有更新的失败作答，请重新规划。"
    if _diagnosis_revision(wrong) != evidence["diagnosis_revision"]:
        return "错因诊断已更新，请重新规划训练方式。"
    source_evidence = task.get("source_evidence") or {}
    if source_evidence.get("status") not in {"matched", "unavailable"}:
        return "旧任务缺少资料片段定位状态，请重新规划。"
    if source_evidence.get("status") == "matched":
        chunk = _storage.get_source_chunk(str(source_evidence.get("chunk_id") or ""))
        if (
            chunk is None
            or chunk.get("source_id") != task.get("source_id")
            or _chunk_revision(chunk) != source_evidence.get("chunk_revision")
        ):
            return "引用的资料片段已变化，请重新规划并核对来源。"
    if _storage.get_source_revision(str(task["source_id"])) != evidence["source_revision"]:
        return "资料内容已变化，请重新规划并重新核对训练题。"
    return None


def _question_revision(question: Any) -> str:
    """生成不暴露题目和参考答案的内容指纹。"""
    value = json.dumps(question, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _diagnosis_revision(wrong: dict[str, Any]) -> str:
    """生成知识点与错因诊断指纹。"""
    value = json.dumps(
        {
            "knowledge_key": wrong.get("knowledge_key"),
            "knowledge_label": wrong.get("knowledge_label"),
            "error_cause": wrong.get("error_cause"),
            "error_cause_source": wrong.get("error_cause_source"),
            "error_cause_note": wrong.get("error_cause_note"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _chunk_revision(chunk: dict[str, Any]) -> str:
    """生成资料分块内容指纹，不把正文复制到任务。"""
    value = json.dumps(
        {
            "chunk_id": chunk.get("chunk_id"),
            "chunk_index": chunk.get("chunk_index"),
            "page_number": chunk.get("page_number"),
            "content": chunk.get("content"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _select_source_evidence(
    source_id: str,
    wrong: dict[str, Any],
) -> dict[str, Any]:
    """为错题选择一个可核对的本地词法匹配片段。"""
    from filemate.understanding.retrieval import rank_chunks

    chunks = _storage.list_source_chunks(source_id)
    question = wrong.get("question") or {}
    stem = (
        str(question.get("stem") or question.get("question") or "")
        if isinstance(question, dict) else ""
    )
    query = " ".join(
        part for part in (str(wrong.get("knowledge_label") or ""), stem) if part.strip()
    )
    ranked = rank_chunks(query, chunks, limit=1)
    if not ranked:
        return {
            "status": "unavailable",
            "method": "local_bm25",
            "reason": "未找到有词法重叠的资料片段，请人工核对原资料。",
        }
    chunk = ranked[0]
    return {
        "status": "matched",
        "method": "local_bm25",
        "chunk_id": chunk["chunk_id"],
        "chunk_index": chunk["chunk_index"],
        "page_number": chunk.get("page_number"),
        "score": chunk["score"],
        "chunk_revision": _chunk_revision(chunk),
        "reason": "本地词法匹配结果，需要结合原资料核对。",
    }


def _run_goal_agents(
    *,
    title: str,
    source_id: str | None,
    gap_count: int,
    task_count: int,
    focus_wrong_id: str | None = None,
    attempt_id: str | None = None,
    knowledge_key: str | None = None,
    error_cause: str | None = None,
    source_chunk_id: str | None = None,
) -> str:
    """记录规划与学习教练的真实协作步骤。"""
    from filemate.core.trusted_agents import select_agents

    run = _storage.create_agent_run(
        task_type="study_plan",
        goal=f"从真实学习证据反推目标：{title}",
        selected_agents=select_agents("study_plan"),
        context_refs={
            "source_id": source_id,
            "focus_wrong_id": focus_wrong_id,
            "attempt_id": attempt_id,
            "knowledge_key": knowledge_key,
            "error_cause": error_cause,
            "source_chunk_id": source_chunk_id,
        },
    )
    _storage.append_agent_step(
        run_id=run["run_id"],
        agent_name="规划 Agent",
        input_refs={"source_id": source_id, "analytics": "local_snapshot"},
        output_summary=f"已对照本地行为证据识别 {gap_count} 个待提升项",
    )
    _storage.append_agent_step(
        run_id=run["run_id"],
        agent_name="学习教练 Agent",
        input_refs={
            "gap_count": gap_count,
            "focus_wrong_id": focus_wrong_id,
            "attempt_id": attempt_id,
            "knowledge_key": knowledge_key,
            "error_cause": error_cause,
            "source_chunk_id": source_chunk_id,
        },
        output_summary=f"已生成 {task_count} 项可执行任务并分配截止日期",
    )
    _storage.finish_agent_run(run["run_id"])
    return str(run["run_id"])


def _select_focus_wrong(source_id: str | None) -> dict[str, Any] | None:
    """选择当前资料里一条未掌握错题。"""
    if not source_id:
        return None
    wrong_questions = _storage.list_wrong_questions(
        mastered=False, source_id=source_id, limit=1,
    )
    if not wrong_questions:
        return None
    wrong = dict(wrong_questions[0])
    artifact = _storage.get_artifact(str(wrong["artifact_id"]))
    questions = artifact.get("content") if artifact else None
    index = int(wrong["question_index"])
    if not isinstance(questions, list) or index >= len(questions):
        return None
    if questions[index] != wrong["question"]:
        return None
    attempt = _storage.get_latest_wrong_attempt(str(wrong["wrong_id"]))
    if attempt is None:
        return None
    wrong["attempt_id"] = attempt["attempt_id"]
    wrong["attempt_at"] = attempt["created_at"]
    wrong["source_revision"] = _storage.get_source_revision(source_id)
    wrong["question_revision"] = _question_revision(questions[index])
    wrong["diagnosis_revision"] = _diagnosis_revision(wrong)
    wrong["source_evidence"] = _select_source_evidence(source_id, wrong)
    return wrong


@app.post("/goals/reverse-plan", response_model=ApiResponse)
def create_reverse_goal(request: ReverseGoalRequest):
    """从目标和真实学习证据反推缺口与行动任务。"""
    if request.deadline < datetime.now().astimezone().date():
        raise HTTPException(status_code=422, detail="目标截止日期不能早于今天")
    source = _storage.get_source(request.source_id) if request.source_id else None
    if request.source_id and source is None:
        raise HTTPException(status_code=404, detail="所选目标资料不存在")

    from filemate.study import build_reverse_goal_plan

    plan = build_reverse_goal_plan(
        title=request.title,
        goal_type=request.goal_type,
        deadline=request.deadline,
        target_score=request.target_score,
        analytics=_storage.get_learning_analytics(source_id=request.source_id),
        source_id=request.source_id,
        source_name=source.get("original_name") if source else None,
        focus_wrong=_select_focus_wrong(request.source_id),
    )
    run_id = _run_goal_agents(
        title=request.title,
        source_id=request.source_id,
        gap_count=sum(1 for item in plan["gaps"] if item["status"] == "gap"),
        task_count=len(plan["tasks"]),
        focus_wrong_id=next(
            (item["focus_wrong_id"] for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        attempt_id=next(
            (item["evidence_ref"]["attempt_id"] for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        knowledge_key=next(
            (item.get("knowledge_key") for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        error_cause=next(
            (item.get("error_cause") for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        source_chunk_id=next(
            ((item.get("source_evidence") or {}).get("chunk_id")
             for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
    )
    plan["last_agent_run_id"] = run_id
    artifact_id = _storage.save_artifact(
        artifact_type="reverse_goal_plan",
        source_id=request.source_id,
        title=request.title.strip(),
        content=plan,
        metadata={"goal_type": request.goal_type, "agent_run_id": run_id},
    )
    _storage.save_agent_memory(
        memory_type="session",
        scope_id=artifact_id,
        source_type="reverse_goal",
        source_id=artifact_id,
        summary=f"目标：{request.title.strip()}；截止：{request.deadline.isoformat()}",
        allowed_agents=["规划 Agent", "学习教练 Agent"],
    )
    artifact = _storage.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=500, detail="目标计划保存失败")
    return ApiResponse(success=True, data=_goal_from_artifact(artifact))


@app.get("/goals", response_model=ApiResponse)
def list_reverse_goals(limit: int = Query(20, ge=1, le=100)):
    """列出已保存的目标反推计划。"""
    artifacts = _storage.list_artifacts(
        artifact_type="reverse_goal_plan",
        limit=limit,
    )
    return ApiResponse(
        success=True,
        data=[_goal_from_artifact(item) for item in artifacts],
    )


@app.patch("/goals/{goal_id}/tasks/{task_id}", response_model=ApiResponse)
def update_reverse_goal_task(
    goal_id: str,
    task_id: str,
    request: GoalTaskUpdateRequest,
):
    """持久化目标任务完成状态。"""
    artifact = _storage.get_artifact(goal_id)
    if artifact is None or artifact.get("artifact_type") != "reverse_goal_plan":
        raise HTTPException(status_code=404, detail="目标计划不存在")
    content = dict(artifact.get("content") or {})
    tasks = list(content.get("tasks") or [])
    matched = False
    for task in tasks:
        if str(task.get("task_id")) == task_id:
            reason = _oral_evidence_invalid_reason(task)
            if reason:
                raise HTTPException(status_code=409, detail=reason)
            task["status"] = "completed" if request.completed else "pending"
            matched = True
            break
    if not matched:
        raise HTTPException(status_code=404, detail="目标任务不存在")
    content["tasks"] = tasks
    updated = _storage.update_artifact(
        goal_id,
        title=str(artifact["title"]),
        content=content,
    )
    return ApiResponse(success=True, data=_goal_from_artifact(updated))


@app.post("/goals/{goal_id}/replan", response_model=ApiResponse)
def replan_reverse_goal(goal_id: str):
    """根据当前证据重新计算缺口，并保留已完成任务。"""
    artifact = _storage.get_artifact(goal_id)
    if artifact is None or artifact.get("artifact_type") != "reverse_goal_plan":
        raise HTTPException(status_code=404, detail="目标计划不存在")
    current = dict(artifact.get("content") or {})
    deadline = date.fromisoformat(str(current["deadline"]))
    if deadline < datetime.now().astimezone().date():
        raise HTTPException(status_code=409, detail="目标已过截止日期，请新建目标")
    source_id = artifact.get("source_id")
    source = _storage.get_source(source_id) if source_id else None

    from filemate.study import build_reverse_goal_plan

    plan = build_reverse_goal_plan(
        title=str(current["title"]),
        goal_type=str(current["goal_type"]),
        deadline=deadline,
        target_score=current.get("target_score"),
        analytics=_storage.get_learning_analytics(source_id=source_id),
        source_id=source_id,
        source_name=source.get("original_name") if source else None,
        previous_tasks=current.get("tasks") or [],
        focus_wrong=_select_focus_wrong(source_id),
    )
    invalidated = list(current.get("invalidated_tasks") or [])
    for task in current.get("tasks") or []:
        reason = _oral_evidence_invalid_reason(task)
        if reason:
            invalidated.append({
                "focus_wrong_id": task.get("focus_wrong_id"),
                "attempt_id": (task.get("evidence_ref") or {}).get("attempt_id"),
                "reason": reason,
                "invalidated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            })
    plan["invalidated_tasks"] = invalidated[-20:]
    run_id = _run_goal_agents(
        title=str(current["title"]),
        source_id=source_id,
        gap_count=sum(1 for item in plan["gaps"] if item["status"] == "gap"),
        task_count=len(plan["tasks"]),
        focus_wrong_id=next(
            (item["focus_wrong_id"] for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        attempt_id=next(
            (item["evidence_ref"]["attempt_id"] for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        knowledge_key=next(
            (item.get("knowledge_key") for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        error_cause=next(
            (item.get("error_cause") for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
        source_chunk_id=next(
            ((item.get("source_evidence") or {}).get("chunk_id")
             for item in plan["tasks"]
             if item["task_id"] == "explain-wrong-aloud"), None,
        ),
    )
    plan["last_agent_run_id"] = run_id
    updated = _storage.update_artifact(
        goal_id,
        title=str(artifact["title"]),
        content=plan,
    )
    return ApiResponse(success=True, data=_goal_from_artifact(updated))


@app.post("/quiz/attempts", response_model=ApiResponse)
def submit_quiz_attempt(request: QuizAttemptRequest):
    """批改练习并自动写入错题本（接入统一判题 check_answer）。"""
    artifact = _storage.get_artifact(request.artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="题目集不存在")
    if artifact["artifact_type"] != "questions":
        raise HTTPException(status_code=422, detail="该产物不是题目集")
    if (artifact.get("metadata", {}).get("question_revision")
            and not artifact.get("metadata", {}).get("read_only_snapshot")
            and request.expected_question is None):
        raise HTTPException(status_code=409, detail="题集已修订，请刷新页面后提交带题目快照的作答")
    questions = artifact.get("content")
    if not isinstance(questions, list) or not 0 <= request.question_index < len(questions):
        raise HTTPException(status_code=422, detail="题目序号无效")

    raw_question = questions[request.question_index]
    if not isinstance(raw_question, dict):
        raise HTTPException(status_code=422, detail="题目数据格式无效")
    if request.expected_question is not None and request.expected_question != raw_question:
        raise HTTPException(status_code=409, detail="题目已更新，请刷新题集后重新作答")
    from filemate.study.question_validation import validate_question

    try:
        question = validate_question(raw_question, legacy=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="题目数据不完整或不一致，原记录保留，请重新生成或修订题集") from exc
    user_answer = (request.user_answer or "").strip()

    from filemate.study import check_answer
    is_correct = check_answer(question, user_answer)
    score = 1.0 if is_correct else 0.0

    try:
        result = _storage.record_quiz_attempt(
            artifact_id=request.artifact_id,
            question_index=request.question_index,
            user_answer=user_answer,
            is_correct=is_correct,
            score=score,
            feedback="回答正确" if is_correct else "已加入错题本，请结合解析复习",
            expected_question=raw_question,
        )
    except QuestionRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="题目集已删除，请重新打开资料") from exc
    return ApiResponse(success=True, data=result)


@app.get("/wrongbook", response_model=ApiResponse)
def list_wrongbook(
    mastered: bool | None = Query(False),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000000),
    q: str = Query("", max_length=160),
    source_id: str | None = Query(None, max_length=80),
):
    """读取错题本。"""
    return ApiResponse(
        success=True,
        data=_storage.wrong_question_page(mastered=mastered, limit=limit, offset=offset,
                                          q=q, source_id=source_id)["items"],
    )


@app.get("/wrongbook/page", response_model=ApiResponse)
def wrongbook_page(mastered: bool | None = Query(False), limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0, le=1000000), q: str = Query("", max_length=160),
                  source_id: str | None = Query(None, max_length=80), due_only: bool = False,
                  error_cause: str | None = Query(None, pattern="^(unconfirmed|concept_gap|memory_gap|reasoning_break|expression_gap|option_confusion|careless)$")):
    return ApiResponse(success=True, data=_storage.wrong_question_page(
        mastered=mastered, limit=limit, offset=offset, q=q, source_id=source_id,
        error_cause=error_cause, due_only=due_only,
    ))


@app.get("/analytics/overview", response_model=ApiResponse)
def learning_analytics():
    """返回学习闭环与模拟面试的本地统计。"""
    return ApiResponse(success=True, data=_storage.get_learning_analytics())


def _growth_repository():
    if os.getenv('FILEMATE_ENABLE_GROWTH_REPORT', '1').lower() in {'0', 'false', 'off'}:
        raise HTTPException(status_code=503, detail='成长报告已关闭，原学习记录保留')
    return GrowthRepository(_storage)


@app.post('/api/growth/reports', response_model=ApiResponse)
def generate_growth_report(request: ReportRequest):
    return ApiResponse(success=True, data=_growth_repository().generate(request))


@app.get('/api/growth/reports', response_model=ApiResponse)
def list_growth_reports():
    return ApiResponse(success=True, data=_growth_repository().list())


def _get_growth_report(identifier: str):
    try:
        return _growth_repository().get(identifier)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='成长报告不存在') from exc
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(status_code=409, detail='成长报告数据异常，原内容保留') from exc


@app.get('/api/growth/reports/{identifier}', response_model=ApiResponse)
def get_growth_report(identifier: str):
    return ApiResponse(success=True, data=GrowthRepository.projection(_get_growth_report(identifier)))


@app.get('/api/growth/reports/{identifier}/evidence', response_model=ApiResponse)
def growth_report_evidence(identifier: str, offset: int = Query(0, ge=0, le=1000000), limit: int = Query(20, ge=1, le=100)):
    records = _get_growth_report(identifier)['records']
    return ApiResponse(success=True, data={'items': records[offset:offset + limit], 'total': len(records), 'offset': offset, 'limit': limit})


@app.get('/api/growth/reports/{identifier}/export')
def export_growth_report(identifier: str, format: Literal['json', 'markdown'] = 'markdown'):
    result = _get_growth_report(identifier)
    content = result['markdown'] if format == 'markdown' else json.dumps(result, ensure_ascii=False, indent=2)
    return Response(content, media_type='text/markdown' if format == 'markdown' else 'application/json', headers={'Content-Disposition': 'attachment; filename="growth-report.' + ('md' if format == 'markdown' else 'json') + '"', 'Cache-Control': 'no-store'})


def _semester_repository():
    if os.getenv('FILEMATE_ENABLE_SEMESTER', '1').lower() in {'0', 'false', 'off'}:
        raise HTTPException(status_code=503, detail='学期模式已关闭，原课程与进度保留')
    return SemesterRepository(_storage)


@app.get('/api/semester', response_model=ApiResponse)
def get_semester():
    try:
        return ApiResponse(success=True, data=_semester_repository().read())
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail='学期数据异常，原内容保留') from exc


@app.post('/api/semester/preview', response_model=ApiResponse)
def preview_semester(request: SemesterConfig):
    try:
        return ApiResponse(success=True, data=_semester_repository().preview(request))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail='课程、资料或学期版本无效，请刷新后检查配置') from exc


@app.post('/api/semester/confirm', response_model=ApiResponse)
def confirm_semester(request: ConfirmSemester):
    try:
        return ApiResponse(success=True, data=_semester_repository().confirm(request))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail='预览已变化或失效，请重新预览；原课程与进度保留') from exc


@app.patch('/api/semester/tasks/{identifier}', response_model=ApiResponse)
def update_semester_task(identifier: str, request: TaskUpdate):
    try:
        return ApiResponse(success=True, data=_semester_repository().update(identifier, request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='学期任务不存在') from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail='学期任务版本或数据无效，请刷新') from exc


def _resume_repository():
    if os.getenv("FILEMATE_ENABLE_RESUME", "1").lower() in {"0", "false", "off"}:
        raise HTTPException(status_code=503, detail="简历功能已关闭，原资料保留")
    return ResumeRepository(_storage)


@app.get("/api/resume/profile", response_model=ApiResponse)
def resume_profile():
    try:
        profile = _resume_repository().profile()
        return ApiResponse(success=True, data=profile.model_dump() if profile else None)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="个人事实数据异常，原内容保留") from exc


@app.put("/api/resume/profile", response_model=ApiResponse)
def save_resume_profile(request: ResumeProfile):
    try:
        return ApiResponse(success=True, data=_resume_repository().save_profile(request))
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="关联作品不存在，请在当前空间重新选择") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/resume/generate", response_model=ApiResponse)
def generate_resume(request: ResumeRequest):
    repository = _resume_repository()
    if request.mode == "llm" and not request.allow_external_model:
        raise HTTPException(status_code=422, detail="请先同意将教育、技能、项目事实及目标岗位发送给配置的模型；姓名和联系方式不发送")
    try:
        from filemate.llm_client import LLMClient, LLMConfig

        llm = LLMClient(LLMConfig.from_env()) if request.mode == "llm" else None
        return ApiResponse(success=True, data=repository.generate(request, llm))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="事实版本或选材结果无效，请刷新个人事实再生成；原资料和简历保留") from exc
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="关联作品已删除，请修订个人事实") from exc
    except Exception as exc:
        logger.warning("简历生成失败 (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="模型选材暂不可用；原资料与旧简历保留，可选择直接排版") from exc


@app.get("/api/resume", response_model=ApiResponse)
def list_resumes():
    return ApiResponse(success=True, data=_resume_repository().list())


@app.get("/api/resume/{identifier}", response_model=ApiResponse)
def get_resume(identifier: str):
    try:
        return ApiResponse(success=True, data=_resume_repository().get(identifier))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="简历不存在") from exc
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(status_code=409, detail="简历数据异常，原内容保留") from exc


@app.get("/api/resume/{identifier}/export")
def export_resume(identifier: str, format: Literal["markdown", "json"] = "markdown"):
    result = get_resume(identifier).data
    content = result["markdown"] if format == "markdown" else json.dumps(result, ensure_ascii=False, indent=2)
    return Response(content, media_type="text/markdown" if format == "markdown" else "application/json",
                    headers={"Content-Disposition": 'attachment; filename="resume.' + ("md" if format == "markdown" else "json") + '"', "Cache-Control": "no-store"})


def _skills_repository():
    from filemate.study.skills import SkillTreeRepository

    if os.getenv("FILEMATE_ENABLE_SKILL_TREE", "1").lower() in {"0", "false", "off"}:
        raise HTTPException(status_code=503, detail="技能树已关闭，原学习数据保留")
    return SkillTreeRepository(_storage)


@app.get("/api/skills/tree", response_model=ApiResponse)
def get_skill_tree():
    try:
        return ApiResponse(success=True, data=_skills_repository().view())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="技能树数据异常，原数据保留，请导出检查或恢复备份") from exc


@app.put("/api/skills/tree", response_model=ApiResponse)
def save_skill_tree(request: dict[str, Any]):
    from pydantic import ValidationError

    from filemate.study.skills import SkillTree

    try:
        tree = SkillTree.model_validate(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="技能配置格式或数量不符合要求") from exc
    try:
        return ApiResponse(success=True, data=_skills_repository().save(tree))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/skills/targets", response_model=ApiResponse)
def skill_targets(q: str = Query("", max_length=160)):
    _skills_repository()
    from filemate.study.question_validation import validate_question

    targets = []
    pattern = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = _storage._conn().execute(
        "SELECT artifact_id,content,title FROM artifacts WHERE artifact_type='questions' AND (lower(content) LIKE ? ESCAPE '\\' OR lower(title) LIKE ? ESCAPE '\\') ORDER BY created_at DESC,rowid DESC",
        (pattern, pattern),
    )
    for artifact in rows:
        try:
            questions = json.loads(artifact["content"])
        except (ValueError, TypeError):
            continue
        if not isinstance(questions, list):
            continue
        for index, question in enumerate(questions):
            try:
                normalized = validate_question(question, legacy=True)
            except (ValueError, TypeError):
                continue
            if q.strip() and q.strip().casefold() not in (normalized["stem"] + " " + artifact["title"]).casefold():
                continue
            targets.append({"kind": "quiz", "target_id": artifact["artifact_id"], "question_index": index,
                            "label": normalized["stem"][:160]})
            if len(targets) >= 500:
                break
        if len(targets) >= 500:
            break
    coding_rows = _storage._conn().execute("SELECT submission_id FROM coding_submissions WHERE lower(problem_id) LIKE ? ESCAPE '\\' OR submission_id LIKE ? ESCAPE '\\' ORDER BY created_at DESC,rowid DESC LIMIT 100", (pattern, pattern))
    for row in coding_rows:
        submission = _coding_repository().get(row["submission_id"])
        if submission["active"] and not submission["data_error"]:
            targets.append({"kind": "coding", "target_id": submission["submission_id"],
                            "label": "编程 · " + submission["problem_id"], "question_index": None})
    for interview in _storage._conn().execute("SELECT interview_id,target_role FROM interview_sessions WHERE lower(target_role) LIKE ? ESCAPE '\\' OR interview_id LIKE ? ESCAPE '\\' ORDER BY created_at DESC,rowid DESC LIMIT 50", (pattern, pattern)):
        targets.append({"kind": "interview", "target_id": interview["interview_id"],
                        "label": "面试 · " + interview["target_role"], "question_index": None})
    return ApiResponse(success=True, data=targets)


@app.patch("/wrongbook/{wrong_id}/diagnosis", response_model=ApiResponse)
def update_wrongbook_diagnosis(
    wrong_id: str,
    request: WrongDiagnosisUpdateRequest,
):
    """保存用户确认的错因分类和备注。"""
    try:
        wrong = _storage.update_wrong_diagnosis(
            wrong_id,
            error_cause=request.error_cause,
            note=request.note,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "错题不存在" else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return ApiResponse(success=True, data=wrong)


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
    """按证据、用户顺序和可用时长生成今日队列。"""
    from filemate.study.daily_coach import select_daily_queue, wrong_review_guidance

    today = datetime.now().astimezone().date()
    preferences = _storage.get_daily_coach_preferences(today.isoformat())
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
        exam_soon = bool(exam and 0 <= (exam - today).days <= 3)
        urgency = "high" if overdue or exam_soon else "normal"
        if overdue:
            reason = f"原定 {scheduled.isoformat()}，建议今天补上"
        elif due_today:
            reason = "这是计划中的今日任务"
        elif scheduled:
            reason = f"下一学习日为 {scheduled.isoformat()}"
        else:
            reason = "下一项未完成学习任务"
        if exam_soon and not overdue:
            reason += f"；距考试 {(exam - today).days} 天"
        items.append(
            {
                "item_id": f"plan:{saved['plan_id']}:{day_index}",
                "kind": "plan_day",
                "priority": urgency,
                "score": 90 if overdue else 78 if exam_soon else 70 if due_today else 45,
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
    for wrong in wrong_questions:
        question = wrong.get("question") or {}
        guidance = wrong_review_guidance(wrong, today)
        items.append(
            {
                "item_id": f"wrong:{wrong['wrong_id']}",
                "kind": "wrong_question",
                "priority": guidance["priority"],
                "score": guidance["score"],
                "title": str(question.get("stem") or question.get("question") or "待复习错题"),
                "reason": guidance["reason"],
                "duration_minutes": guidance["duration_minutes"],
                "error_cause": guidance["error_cause"],
                "error_cause_source": guidance["error_cause_source"],
                "artifact_id": wrong["artifact_id"],
                "question_index": wrong["question_index"],
                "question_snapshot": question,
                "wrong_id": wrong["wrong_id"],
                "explanation": question.get("explanation", ""),
                "route": "/wrongbook",
            }
        )

    recommended, deferred_count = select_daily_queue(
        items,
        available_minutes=preferences["available_minutes"],
        item_order=preferences["item_order"],
    )
    return ApiResponse(
        success=True,
        data={
            "date": today.isoformat(),
            "items": recommended,
            "active_plan_count": len(active_plans),
            "pending_wrong_count": len(wrong_questions),
            "available_minutes": preferences["available_minutes"],
            "item_order": preferences["item_order"],
            "deferred_count": deferred_count,
            "recommended_minutes": sum(
                int(item["duration_minutes"]) for item in recommended
            ),
        },
    )


@app.put("/review/today/preferences", response_model=ApiResponse)
def update_daily_coach_preferences(request: DailyCoachPreferencesRequest):
    """保存今天的时间预算与手动任务顺序。"""
    if any(len(item_id) > 100 for item_id in request.item_order):
        raise HTTPException(status_code=422, detail="任务标识过长")
    try:
        _storage.set_daily_coach_preferences(
            datetime.now().astimezone().date().isoformat(),
            available_minutes=request.available_minutes,
            item_order=request.item_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return today_review()


@app.get("/interview/questions", response_model=ApiResponse)
def list_interview_questions(
    scenario: str | None = Query(None),
    difficulty: str | None = Query(None),
    enabled: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """列出面试题库题目。"""
    return ApiResponse(
        success=True,
        data=_storage.list_interview_questions(
            scenario=scenario,
            difficulty=difficulty,
            enabled=enabled,
            limit=limit,
        ),
    )


@app.post("/interview/questions", response_model=ApiResponse)
def create_interview_question(request: InterviewQuestionCreate):
    """新增面试题库题目。"""
    try:
        question_id = _storage.create_interview_question(
            scenario=request.scenario,
            difficulty=request.difficulty,
            text=request.text,
            enabled=1 if request.enabled else 0,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponse(
        success=True,
        data=_storage.get_interview_question(question_id),
    )


@app.patch("/interview/questions/{question_id}", response_model=ApiResponse)
def update_interview_question(question_id: str, request: InterviewQuestionUpdate):
    """更新面试题库题目。"""
    updates = {
        key: value
        for key, value in request.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if not updates:
        raise HTTPException(status_code=422, detail="没有可更新的字段")
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    try:
        ok = _storage.update_interview_question(question_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="题目不存在")
    return ApiResponse(
        success=True,
        data=_storage.get_interview_question(question_id),
    )


@app.delete("/interview/questions/{question_id}", response_model=ApiResponse)
def delete_interview_question(question_id: str):
    """删除面试题库题目。"""
    ok = _storage.delete_interview_question(question_id)
    if not ok:
        raise HTTPException(status_code=404, detail="题目不存在")
    return ApiResponse(success=True, data={"deleted": True})


@app.post("/interviews", response_model=ApiResponse)
def start_interview(request: InterviewStartRequest):
    """创建一场可持续复盘的模拟面试。"""
    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.understanding import (
        build_interview_questions,
        build_source_grounded_question,
        build_wrong_grounded_question,
    )


    source = None
    context_excerpt = ""
    source_context_mode = "none"
    if request.source_id:
        source = _storage.get_source(request.source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="所选面试资料不存在")
        rights = _storage.get_source_rights(request.source_id)
        if rights and rights["rights_status"] != "unconfirmed":
            context_excerpt = str(source.get("raw_text", ""))[:2000]
            source_context_mode = "authorized_excerpt"
        else:
            source_context_mode = "local_metadata_only"
    focus_wrong = None
    linked_task = None
    if request.focus_wrong_id:
        if source is None:
            raise HTTPException(status_code=422, detail="错题训练需要先选择资料")
        focus_wrong = _storage.get_wrong_question(request.focus_wrong_id)
        if (
            focus_wrong is None
            or focus_wrong.get("source_id") != request.source_id
            or focus_wrong.get("mastered")
        ):
            raise HTTPException(status_code=422, detail="所选错题已失效，请重新规划目标")
    if request.goal_id:
        goal_artifact = _storage.get_artifact(request.goal_id)
        goal_content = goal_artifact.get("content") if goal_artifact else None
        linked_task = next(
            (
                task for task in (goal_content.get("tasks") or [])
                if task.get("task_id") == "explain-wrong-aloud"
                and task.get("focus_wrong_id") == request.focus_wrong_id
            ), None,
        ) if isinstance(goal_content, dict) else None
        if (
            not goal_artifact
            or goal_artifact.get("artifact_type") != "reverse_goal_plan"
            or goal_artifact.get("source_id") != request.source_id
            or not request.focus_wrong_id
            or linked_task is None
            or _oral_evidence_invalid_reason(linked_task) is not None
        ):
            raise HTTPException(status_code=422, detail="目标训练关联已失效，请重新规划目标")

    source_evidence = None
    if focus_wrong and request.source_id:
        source_evidence = (
            dict(linked_task.get("source_evidence") or {})
            if linked_task is not None
            else _select_source_evidence(request.source_id, focus_wrong)
        )

    try:
        if os.getenv("FILEMATE_INTERVIEW_LOCAL_ONLY") == "1" or request.allow_external_analysis is False:
            raise RuntimeError("本地选题模式")
        llm = LLMClient(LLMConfig.from_env())
    except Exception:  # noqa: BLE001 - 未配置 LLM 时使用确定性选题
        llm = None

    questions, question_ids = build_interview_questions(
        _storage,
        llm,
        scenario=request.scenario,
        difficulty=request.difficulty,
        target_role=request.target_role,
        limit=5,
        context_excerpt=context_excerpt,
    )
    from filemate.core.trusted_agents import select_agents

    target_role = request.target_role.strip() or "通用岗位"
    if source is not None:
        grounded_question = (
            build_wrong_grounded_question(
                str(source["original_name"]),
                focus_wrong["question"],
                error_cause=str(focus_wrong.get("error_cause") or "unconfirmed"),
                knowledge_label=str(focus_wrong.get("knowledge_label") or ""),
            )
            if focus_wrong else build_source_grounded_question(
                str(source["original_name"]), request.scenario, target_role,
            )
        )
        remaining = [
            (question, question_id)
            for question, question_id in zip(questions, question_ids, strict=True)
            if question != grounded_question
        ][:4]
        questions = [grounded_question, *[item[0] for item in remaining]]
        question_ids = [None, *[item[1] for item in remaining]]
    run = _storage.create_agent_run(
        task_type="interview_session",
        goal=f"围绕{target_role}完成可复盘的{request.scenario}",
        selected_agents=select_agents("interview_session"),
        context_refs={
            "scenario": request.scenario,
            "allow_external_analysis": request.allow_external_analysis,
            "difficulty": request.difficulty,
            "question_ids": question_ids,
            "source_id": request.source_id,
            "source_context_mode": source_context_mode,
            "focus_wrong_id": request.focus_wrong_id,
            "goal_id": request.goal_id,
            "attempt_id": (
                (linked_task.get("evidence_ref") or {}).get("attempt_id")
                if request.goal_id else None
            ),
            "knowledge_key": (
                linked_task.get("knowledge_key")
                if request.goal_id else focus_wrong.get("knowledge_key") if focus_wrong else None
            ),
            "error_cause": (
                linked_task.get("error_cause")
                if request.goal_id else focus_wrong.get("error_cause") if focus_wrong else None
            ),
            "source_evidence": source_evidence,
            "source_chunk_id": (
                source_evidence.get("chunk_id") if source_evidence else None
            ),
        },
    )
    interview = _storage.create_interview(
        target_role=target_role,
        scenario=request.scenario,
        difficulty=request.difficulty,
        questions=questions,
        question_ids=question_ids,
        agent_run_id=run["run_id"],
    )
    _storage.append_agent_step(
        run_id=run["run_id"],
        agent_name="面试 Agent",
        input_refs={
            "interview_id": interview["interview_id"],
            "question_ids": question_ids,
            "focus_wrong_id": request.focus_wrong_id,
            "source_chunk_id": (
                source_evidence.get("chunk_id") if source_evidence else None
            ),
        },
        output_summary=(
            f"已按{request.scenario}·{request.difficulty}选择 "
            f"{len(questions)} 道问题"
        ),
    )
    _storage.save_agent_memory(
        memory_type="session",
        scope_id=interview["interview_id"],
        source_type="interview_goal",
        source_id=interview["interview_id"],
        summary=(
            f"目标：{target_role}；场景：{request.scenario}"
            + (
                f"；依据资料：{source['original_name']}"
                if source is not None
                else ""
            )
        ),
        allowed_agents=["面试 Agent", "评价 Agent"],
    )
    interview["current_question"] = interview["questions"][0]
    interview["source_context"] = {
        "source_id": request.source_id,
        "source_name": source["original_name"] if source is not None else None,
        "mode": source_context_mode,
        "focus_wrong_id": request.focus_wrong_id,
        "goal_id": request.goal_id,
        "source_evidence": source_evidence,
    }
    return ApiResponse(success=True, data=interview)


def _attach_interview_source_context(interview: dict[str, Any]) -> None:
    """从 Agent 运行记录恢复面试资料来源，不复制资料正文。"""
    run_id = interview.get("agent_run_id")
    run = _storage.get_agent_run(run_id) if run_id else None
    refs = run.get("context_refs", {}) if run else {}
    source_id = refs.get("source_id")
    source = _storage.get_source(source_id) if source_id else None
    interview["source_context"] = {
        "source_id": source_id,
        "source_name": source.get("original_name") if source else None,
        "mode": refs.get("source_context_mode", "none"),
        "focus_wrong_id": refs.get("focus_wrong_id"),
        "goal_id": refs.get("goal_id"),
        "source_evidence": refs.get("source_evidence"),
    }


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
    _attach_interview_source_context(interview)
    return ApiResponse(success=True, data=interview)


@app.post("/interviews/{interview_id}/answers", response_model=ApiResponse)
def answer_interview(interview_id: str, request: InterviewAnswerRequest):
    """评估当前回答并推进到下一题。"""
    interview = _storage.get_interview(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    digest = hashlib.sha256(json.dumps(
        request.model_dump(exclude={"request_key"}), ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()
    if request.request_key:
        previous = next((turn for turn in interview["turns"]
                         if turn.get("answer_key") == request.request_key), None)
        if previous:
            if previous.get("answer_digest") != digest:
                raise HTTPException(status_code=409, detail="重复请求键的回答内容不同")
            return get_interview(interview_id)
    if interview["status"] == "completed":
        raise HTTPException(status_code=409, detail="模拟面试已完成")
    if not request.answer.strip():
        raise HTTPException(status_code=422, detail="回答不能为空")
    if request.question_index is not None and request.question_index != interview["current_index"]:
        raise HTTPException(status_code=409, detail="面试进度已更新，请刷新后继续")
    if request.visual_metrics:
        _require_interview_review_enabled()

    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.understanding import InterviewEvaluator

    index = interview["current_index"]
    question = interview["questions"][index]
    run = _storage.get_agent_run(interview["agent_run_id"]) if interview.get("agent_run_id") else None
    context_refs = run.get("context_refs", {}) if run else {}
    private_wrong_question = bool(
        context_refs.get("focus_wrong_id")
        and context_refs.get("source_context_mode") == "local_metadata_only"
    )
    try:
        if (
            os.getenv("FILEMATE_INTERVIEW_LOCAL_ONLY") == "1"
            or interview["scenario"] == "知识讲解"
            or private_wrong_question
            or context_refs.get("allow_external_analysis") is False
        ):
            raise RuntimeError("本地评分模式")
        evaluator = InterviewEvaluator(LLMClient(LLMConfig.from_env()))
    except Exception:  # noqa: BLE001 - 未配置模型或隐私模式下使用本地评分
        evaluator = InterviewEvaluator(None)
    evaluation = evaluator.evaluate(
        question,
        request.answer,
        interview["target_role"],
        request.fluency_metrics.model_dump() if request.fluency_metrics else None,
    )
    try:
        updated = _storage.save_interview_turn(
            interview_id=interview_id,
            question_index=index,
            question=question,
            answer=request.answer.strip(),
            score=evaluation["score"],
            dimensions=evaluation["dimensions"],
            feedback=evaluation["feedback"],
            fluency_metrics=evaluation.get("fluency"),
            scoring_mode=evaluation["scoring_mode"],
            scoring_version="v2.4",
            visual_metrics=request.visual_metrics.model_dump() if request.visual_metrics else None,
            content_analysis=evaluation.get("content_analysis"),
            answer_key=request.request_key, answer_digest=digest,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "模拟面试不存在" else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    run_id = interview.get("agent_run_id")
    if run_id:
        _storage.append_agent_step(
            run_id=run_id,
            agent_name="评价 Agent",
            input_refs={
                "interview_id": interview_id,
                "question_index": index,
            },
            output_summary=(
                f"第 {index + 1} 题：{evaluation['score'] if evaluation['score'] is not None else '内容待评估'}；"
                f"已记录 {len(evaluation['dimensions'])} 个评分维度"
            ),
        )
        _storage.save_agent_memory(
            memory_type="growth",
            scope_id=interview_id,
            source_type="interview_turn",
            source_id=f"{interview_id}:{index}",
            summary=(
                f"{interview['scenario']}第 {index + 1} 题得分 "
                f"{evaluation['score'] if evaluation['score'] is not None else '待评估'}，用于后续复盘"
            ),
            allowed_agents=["评价 Agent", "规划 Agent", "学习教练 Agent"],
        )
        if updated["status"] == "completed":
            _storage.finish_agent_run(run_id)
    if updated["status"] == "completed" and context_refs.get("goal_id"):
        goal_artifact = _storage.get_artifact(str(context_refs["goal_id"]))
        if goal_artifact and goal_artifact.get("artifact_type") == "reverse_goal_plan":
            goal_content = dict(goal_artifact.get("content") or {})
            tasks = list(goal_content.get("tasks") or [])
            for task in tasks:
                if (
                    task.get("task_id") == "explain-wrong-aloud"
                    and task.get("focus_wrong_id") == context_refs.get("focus_wrong_id")
                    and goal_artifact.get("source_id") == context_refs.get("source_id")
                    and _oral_evidence_invalid_reason(task) is None
                ):
                    task["status"] = "completed"
                    goal_content["tasks"] = tasks
                    _storage.update_artifact(
                        str(context_refs["goal_id"]),
                        title=str(goal_artifact["title"]), content=goal_content,
                    )
                    break
    next_index = updated["current_index"]
    updated["current_question"] = (
        updated["questions"][next_index]
        if next_index < len(updated["questions"])
        else None
    )
    updated["latest_evaluation"] = evaluation
    _attach_interview_source_context(updated)
    return ApiResponse(success=True, data=updated)


def _require_interview_review_enabled():
    if os.getenv("FILEMATE_ENABLE_INTERVIEW_REVIEW", "1") == "0":
        raise HTTPException(status_code=503, detail="面试增强暂未启用，原有文字和语音练习仍可使用")


def _interview_review_repository():
    from filemate.interview_review.repository import ReviewRepository

    context = _tenant_context.get()
    storage = (_tenant_storage(context[0]) if context else
               (_storage.local_storage if isinstance(_storage, _StorageRouter) else _storage))
    return ReviewRepository(storage)


def _interview_review_error(exc: Exception):
    return HTTPException(status_code=404 if isinstance(exc, KeyError) else 409,
                         detail="面试或回答不存在" if isinstance(exc, KeyError) else str(exc))


@app.get("/interview/review/status", response_model=ApiResponse)
def interview_review_status():
    return ApiResponse(success=True, data={
        "enabled": os.getenv("FILEMATE_ENABLE_INTERVIEW_REVIEW", "1") != "0",
        "version": "2.4", "video_uploaded": False, "calibration": "待校准",
    })


@app.get("/interviews/{interview_id}/review", response_model=ApiResponse)
def get_interview_report(interview_id: str):
    _require_interview_review_enabled()
    try:
        repo = _interview_review_repository()
        return ApiResponse(success=True, data={"report": repo.report(interview_id),
                                               "events": repo.events(interview_id)})
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.post("/interviews/{interview_id}/review", response_model=ApiResponse)
def generate_interview_report(interview_id: str):
    _require_interview_review_enabled()
    try:
        return ApiResponse(success=True, data=_interview_review_repository().generate(interview_id))
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.post("/interviews/{interview_id}/turns/{turn_id}/analyze", response_model=ApiResponse)
def analyze_interview_turn(interview_id: str, turn_id: str, request: InterviewAnalysisRequest):
    _require_interview_review_enabled()
    if not request.external_consent:
        raise HTTPException(status_code=422, detail="请先确认向已配置模型发送问题与回答；音视频不会外发")
    if os.getenv("FILEMATE_INTERVIEW_LOCAL_ONLY") == "1":
        raise HTTPException(status_code=503, detail="当前面试处于本地模式，未向外部模型发送数据")
    repo = _interview_review_repository()
    try:
        interview, revision = repo.snapshot(interview_id)
        turn = next((item for item in interview["turns"] if item["turn_id"] == turn_id), None)
        if not turn:
            raise KeyError(turn_id)
        if turn.get("analysis_data_error"):
            raise ValueError("分析数据异常，请先清空分析；原回答保留")
        if turn.get("content_analysis", {}).get("source") == "llm_reference":
            return get_interview(interview_id)
        _attach_interview_source_context(interview)
        refs = interview.get("source_context") or {}
        if refs.get("focus_wrong_id") and refs.get("mode") == "local_metadata_only":
            raise HTTPException(status_code=403, detail="所选私有错题尚未授权外发，内容分析仅可本地复盘")
        from filemate.llm_client import LLMClient, LLMConfig
        from filemate.understanding import InterviewEvaluator

        try:
            evaluation = InterviewEvaluator(LLMClient(LLMConfig.from_env())).evaluate(
                turn["question"], turn["answer"], interview["target_role"], turn.get("fluency_metrics"),
            )
        except Exception as exc:  # noqa: BLE001 - 模型不可用时保留原始面试证据
            from filemate.interview_review.content import analysis_failure

            evaluation = {"scoring_mode": "local_fallback", "analysis_error": analysis_failure(exc)}
        if evaluation["scoring_mode"] != "llm":
            detail = evaluation.get("analysis_error", {}).get(
                "message", "模型分析未完成，请重试这一题；原回答、节奏与报告保留",
            )
            raise HTTPException(status_code=502, detail=detail)
        updated = repo.apply_analysis(interview_id, turn_id, revision, evaluation)
        _attach_interview_source_context(updated)
        return ApiResponse(success=True, data=updated)
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.post("/interviews/{interview_id}/analysis/cancel", response_model=ApiResponse)
def cancel_interview_analysis(interview_id: str):
    _require_interview_review_enabled()
    try:
        return ApiResponse(success=True, data=_interview_review_repository().cancel(interview_id))
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.post("/interviews/{interview_id}/analysis/clear", response_model=ApiResponse)
def clear_interview_analysis(interview_id: str, request: InterviewPrivacyRequest):
    _require_interview_review_enabled()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请确认清空内容评分、视觉观察和报告；原回答与节奏保留")
    try:
        data = _interview_review_repository().clear(interview_id)
        _attach_interview_source_context(data)
        return ApiResponse(success=True, data=data)
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.get("/interviews/{interview_id}/delete-preview", response_model=ApiResponse)
def preview_interview_delete(interview_id: str):
    _require_interview_review_enabled()
    try:
        return ApiResponse(success=True, data=_interview_review_repository().delete_preview(interview_id))
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.delete("/interviews/{interview_id}", response_model=ApiResponse)
def delete_interview(interview_id: str, request: InterviewPrivacyRequest):
    _require_interview_review_enabled()
    if not request.confirmed or len(request.confirmation_token) != 64:
        raise HTTPException(status_code=422, detail="请先预览并确认本场练习的删除影响")
    try:
        return ApiResponse(success=True, data=_interview_review_repository().delete(
            interview_id, request.confirmation_token,
        ))
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


@app.get("/interviews/{interview_id}/review/export")
def export_interview_report(interview_id: str, format: Literal["json", "markdown", "pdf"] = "json"):
    _require_interview_review_enabled()
    from filemate.interview_review.reports import report_markdown, report_pdf

    repo = _interview_review_repository()
    try:
        report = repo.report(interview_id)
        if report is None:
            raise ValueError("请先生成当前记录的复盘报告")
        if format == "pdf":
            content, mime, extension = report_pdf(report), "application/pdf", "pdf"
        elif format == "markdown":
            content, mime, extension = report_markdown(report).encode(), "text/markdown; charset=utf-8", "md"
        else:
            content, mime, extension = json.dumps(report, ensure_ascii=False, indent=2).encode(), "application/json", "json"
        repo.log_export(interview_id, format)
        return Response(content=content, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="filemate-interview-{interview_id}.{extension}"',
            "Cache-Control": "no-store",
        })
    except (KeyError, ValueError) as exc:
        raise _interview_review_error(exc) from exc


def _career_repository() -> Any:
    from filemate.career.repository import CareerRepository

    if os.getenv("FILEMATE_ENABLE_CAREER", "1") == "0":
        raise HTTPException(status_code=503, detail="求职训练中心暂未启用，原学习功能仍可使用")
    context = _tenant_context.get()
    storage = (_tenant_storage(context[0]) if context else
               (_storage.local_storage if isinstance(_storage, _StorageRouter) else _storage))
    return CareerRepository(storage)


def _career_call(method: str, *args: Any) -> ApiResponse:
    try:
        return ApiResponse(success=True, data=getattr(_career_repository(), method)(*args))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 409,
                            detail="岗位或训练不存在" if isinstance(exc, KeyError) else str(exc)) from exc


@app.get("/api/career/status", response_model=ApiResponse)
def career_status() -> ApiResponse:
    return ApiResponse(success=True, data={"enabled": os.getenv("FILEMATE_ENABLE_CAREER", "1") != "0",
                                           "version": "2.5", "live_recruitment": False})


@app.get("/api/career/catalog", response_model=ApiResponse)
def career_catalog() -> ApiResponse:
    _career_repository()
    from filemate.career.catalog import CATALOG

    return ApiResponse(success=True, data=CATALOG)


class CareerExtractRequest(BaseModel):
    description: str = Field(min_length=10, max_length=12000)


@app.post("/api/career/extract", response_model=ApiResponse)
def career_extract(request: CareerExtractRequest) -> ApiResponse:
    _career_repository()
    from filemate.career.catalog import extract_requirements

    if not request.description.strip():
        raise HTTPException(status_code=422, detail="请输入岗位描述")
    return ApiResponse(success=True, data={"requirements": extract_requirements(request.description),
                                           "method": "本地词表提取，保存前需核对原句和分类"})


@app.get("/api/career/positions", response_model=ApiResponse)
def career_positions() -> ApiResponse:
    return _career_call("list")


@app.post("/api/career/positions", response_model=ApiResponse)
def create_career_position(request: PositionWrite) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请核对岗位要求和来源后确认保存")
    return _career_call("create", request.position.model_dump(mode="json"), request.request_key)


@app.get("/api/career/positions/{identifier}", response_model=ApiResponse)
def get_career_position(identifier: str) -> ApiResponse:
    return _career_call("get", identifier)


@app.patch("/api/career/positions/{identifier}", response_model=ApiResponse)
def edit_career_position(identifier: str, request: PositionEdit) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请确认岗位修改，既有训练保留原快照")
    return _career_call("edit", identifier, request.position.model_dump(mode="json"), request.expected_revision)


@app.post("/api/career/positions/{identifier}/state/{action}", response_model=ApiResponse)
def transition_career_position(identifier: str, action: Literal["undo", "restore"], request: DeleteRequest) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请确认撤销或恢复此岗位")
    return _career_call("transition", identifier, action)


@app.get("/api/career/positions/{identifier}/evidence", response_model=ApiResponse)
def career_evidence(identifier: str) -> ApiResponse:
    return _career_call("comparison", identifier)


@app.get("/api/career/positions/{identifier}/trainings", response_model=ApiResponse)
def career_trainings(identifier: str) -> ApiResponse:
    return _career_call("trainings", identifier)


@app.post("/api/career/positions/{identifier}/trainings", response_model=ApiResponse)
def create_career_training(identifier: str, request: TrainingStart) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请确认按当前岗位快照创建训练")
    return _career_call("start", identifier, request.kind, request.request_key, request.expected_revision)


@app.get("/api/career/trainings/{identifier}", response_model=ApiResponse)
def career_training(identifier: str) -> ApiResponse:
    return _career_call("training", identifier)


@app.post("/api/career/trainings/{identifier}/answers", response_model=ApiResponse)
def career_written_answers(identifier: str, request: WrittenAnswer) -> ApiResponse:
    return _career_call("answer_written", identifier, request.answers)


@app.get("/api/career/positions/{identifier}/delete-preview", response_model=ApiResponse)
def career_delete_preview(identifier: str) -> ApiResponse:
    return _career_call("preview_delete", identifier)


@app.delete("/api/career/positions/{identifier}", response_model=ApiResponse)
def delete_career_position(identifier: str, request: DeleteRequest) -> ApiResponse:
    _career_repository()
    if not request.confirmed or len(request.confirmation_token) != 64:
        raise HTTPException(status_code=422, detail="请预览并确认删除范围")
    return _career_call("delete", identifier, request.confirmation_token)


@app.get("/api/career/events", response_model=ApiResponse)
def career_events() -> ApiResponse:
    return _career_call("events")


@app.get("/api/career/overview", response_model=ApiResponse)
def career_overview() -> ApiResponse:
    return _career_call("overview")


@app.get("/api/career/positions/{identifier}/plan-preview", response_model=ApiResponse)
def career_plan_preview(identifier: str) -> ApiResponse:
    return _career_call("plan_preview", identifier)


@app.get("/api/career/positions/{identifier}/plans", response_model=ApiResponse)
def career_plans(identifier: str) -> ApiResponse:
    return _career_call("plans", identifier)


@app.post("/api/career/positions/{identifier}/plans", response_model=ApiResponse)
def save_career_plan(identifier: str, request: PlanConfirm) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请先核对学习建议并确认保存")
    return _career_call("save_plan", identifier, request.evidence_revision)


@app.post("/api/career/positions/{identifier}/plans/{plan_id}/{action}", response_model=ApiResponse)
def transition_career_plan(identifier: str, plan_id: str, action: Literal["undo", "restore"], request: DeleteRequest) -> ApiResponse:
    _career_repository()
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="请确认学习计划状态变更")
    return _career_call("transition_plan", identifier, plan_id, action)


@app.get("/api/career/trainings/{identifier}/export")
def export_career_training(identifier: str, format: Literal["json", "markdown"] = "json") -> Response:
    repo = _career_repository()
    try:
        row = repo.training(identifier)
        if row["data_error"]:
            raise ValueError("训练数据异常，原记录保留，暂不能导出")
        if format == "json":
            content, mime, extension = json.dumps(row, ensure_ascii=False, indent=2), "application/json", "json"
        else:
            p = row["payload"]["position"]
            content = (f"# {p['company']} · {p['title']}训练快照\n\n"
                       f"来源：{p['source']}\n\n采集时间：{p['collected_at']}\n\n"
                       "平台原创模拟训练，不是企业真题或录用判断。\n\n```json\n"
                       + json.dumps(row["payload"], ensure_ascii=False, indent=2) + "\n```\n")
            mime, extension = "text/markdown; charset=utf-8", "md"
        with repo.storage._write_lock, repo.storage._conn():
            repo.event(row["position_id"], "exported", identifier, {"format": format})
        return Response(content=content.encode(), media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="filemate-career-{identifier}.{extension}"',
            "Cache-Control": "no-store",
        })
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 409,
                            detail="训练不存在" if isinstance(exc, KeyError) else str(exc)) from exc


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
        if not matches:
            answer = "当前资料中没有找到可核对的依据。请补充相关资料，或换一个更具体的问题。"
            history = _storage.append_context_messages(ctx_id, [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer, "citations": []},
            ])
            return ApiResponse(success=True, data={
                "ctx_id": ctx_id, "question": question, "answer": answer,
                "mode": request.mode, "citations": [], "answerable": False,
                "reason": "insufficient_evidence", "chat_history": history[-10:],
            })
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
        answer = await run_in_threadpool(
            chatbot.answer,
            question,
            context,
            chat_history=persisted_history,
            mode=request.mode,
        )
        cited_ids = {int(value) for value in re.findall(r"\[引用\s*(\d+)\]", answer)}
        allowed_ids = {item["id"] for item in citations}
        if not cited_ids or not cited_ids <= allowed_ids:
            raise ValueError("模型回答缺少有效引用，请重试")
        citations = [item for item in citations if item["id"] in cited_ids]
        chat_history = _storage.append_context_messages(
            ctx_id,
            [
                {"role": "user", "content": question},
                {
                    "role": "assistant",
                    "content": answer,
                    "citations": citations,
                },
            ],
        )

        result = {
            "ctx_id": ctx_id,
            "question": question,
            "answer": answer,
            "answerable": True,
            "mode": request.mode,
            "citations": citations,
            "chat_history": chat_history[-10:],
        }

        return ApiResponse(success=True, data=result)
    except Exception as exc:
        logger.exception("AI问答失败")
        raise HTTPException(status_code=502, detail="AI 问答失败") from exc


@app.get("/ai/contexts", response_model=ApiResponse)
async def list_ai_contexts(
    source_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """列出 AI 问答会话列表（最近更新的排在前面）。"""
    try:
        sessions = _storage.list_document_contexts(source_id=source_id, limit=limit)
        return ApiResponse(success=True, data=sessions)
    except Exception as exc:
        logger.exception("列出 AI 会话失败")
        raise HTTPException(status_code=502, detail="列出 AI 会话失败") from exc


@app.get("/ai/contexts/{ctx_id}", response_model=ApiResponse)
async def get_ai_context(ctx_id: str):
    """获取单个 AI 问答会话的完整内容。"""
    ctx = _storage.get_document_context(ctx_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse(success=True, data=ctx)


# =============== Main ===============

def run_server() -> None:
    """启动本地 FastAPI 服务。"""
    import uvicorn

    host = os.getenv("FILEMATE_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.getenv("FILEMATE_PORT", "8001"))
    except ValueError as exc:
        raise ValueError("FILEMATE_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("FILEMATE_PORT must be between 1 and 65535")

    global _uvicorn_server
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    _uvicorn_server = uvicorn.Server(config)
    _uvicorn_server.run()


if __name__ == "__main__":
    run_server()
