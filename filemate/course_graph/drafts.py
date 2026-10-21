"""Persist per-source extraction claims without holding transactions over AI."""

import copy
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from filemate.course_graph.extraction import (
    EXTRACTOR_VERSION,
    INPUT_LIMIT,
    extract_local_course,
    validate_candidates,
)
from filemate.course_graph.models import CourseGraphError, digest, request_key_valid
from filemate.course_graph.repository import (
    get_request,
    record_change,
    require_course,
    transaction,
)
from filemate.execution.storage import SQLiteStorage
from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable


class DraftService:
    """Manage bounded draft groups and explicit resumable source work."""

    def __init__(self, storage: SQLiteStorage, provider_factory: Callable[[], Any],
                 clock: Callable[[], datetime]):
        self.storage, self.provider_factory, self.clock = storage, provider_factory, clock

    def _now(self) -> datetime:
        return self.clock().astimezone(timezone.utc)

    def _group(self, conn, course_id: str, draft_id: str) -> dict[str, Any]:
        require_course(conn, course_id)
        row = conn.execute("SELECT * FROM kg_changes WHERE course_id=? AND operation_id=? AND kind='draft'",
                           (course_id, draft_id)).fetchone()
        if row is None:
            raise CourseGraphError("draft_not_found", 404)
        result = dict(row)
        result["metadata"] = json.loads(row["metadata"])
        return result

    def _source_input(self, conn, course_id: str, source_id: str, mode: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM kg_course_sources WHERE course_id=? AND source_id=? AND active=1",
                           (course_id, source_id)).fetchone()
        revision = self.storage.get_source_revision(source_id)
        if row is None or revision is None:
            raise CourseGraphError("source_not_in_course", 404)
        return {"source_id": source_id, "source_revision": revision, "membership_revision": row["revision"],
                "mode": mode, "extractor_version": EXTRACTOR_VERSION}

    def _current(self, conn, row) -> bool:
        try:
            return row["input_digest"] == digest(self._source_input(conn, row["course_id"], row["source_id"], row["mode"]))
        except CourseGraphError:
            return False

    def create_group(self, course_id: str, source_ids: list[str], mode: str,
                     request_key: str) -> dict[str, Any]:
        request_key_valid(request_key)
        if mode not in {"local", "llm"} or not 1 <= len(source_ids) <= 10 or len(set(source_ids)) != len(source_ids):
            raise CourseGraphError("invalid_sources_or_mode", 422)
        with transaction(self.storage) as conn:
            require_course(conn, course_id)
            inputs = [self._source_input(conn, course_id, sid, mode) for sid in sorted(source_ids)]
            hashed = digest(inputs)
            previous = get_request(conn, course_id, request_key, "draft", hashed)
            if previous:
                did = previous["metadata"].get("draft_id", previous["operation_id"])
            else:
                same = conn.execute("""SELECT operation_id FROM kg_changes WHERE course_id=? AND kind='draft'
                                       AND input_digest=? AND status='applied' ORDER BY created_at LIMIT 1""",
                                    (course_id, hashed)).fetchone()
                did = same["operation_id"] if same else str(uuid4())
                record_change(conn, course_id, request_key, "draft", hashed,
                              {"draft_id": did, "sources": inputs}, None if same else did)
                if not same:
                    stamp = self._now().isoformat()
                    for item in inputs:
                        conn.execute("""INSERT INTO kg_extractions(extraction_id,draft_id,course_id,source_id,
                                        source_revision,mode,extractor_version,request_key,input_digest,status,
                                        created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?)""",
                                     (str(uuid4()), did, course_id, item["source_id"], item["source_revision"], mode,
                                      EXTRACTOR_VERSION, request_key, digest(item), stamp, stamp))
        return self.snapshot(course_id, did)

    def snapshot(self, course_id: str, draft_id: str) -> dict[str, Any]:
        with transaction(self.storage) as conn:
            group = self._group(conn, course_id, draft_id)
            conn.execute("""UPDATE kg_extractions SET status='interrupted',epoch=epoch+1,lease_until=NULL,
                            error_code='lease_expired',updated_at=? WHERE course_id=? AND draft_id=?
                            AND status='running' AND (lease_until IS NULL OR lease_until<=?)""",
                         (self._now().isoformat(), course_id, draft_id, self._now().isoformat()))
            return self.read_snapshot(conn, course_id, draft_id, group)

    def read_snapshot(self, conn, course_id: str, draft_id: str,
                      group: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read the same draft contract inside an existing confirmation transaction."""
        group = group or self._group(conn, course_id, draft_id)
        rows = conn.execute("SELECT * FROM kg_extractions WHERE course_id=? AND draft_id=? ORDER BY source_id",
                            (course_id, draft_id)).fetchall()
        sources = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            item["source_current"] = self._current(conn, row)
            sources.append(item)
        # 删除来源后仅保留操作中的匿名ID，正文候选由FK清除。
        for original in group["metadata"]["sources"]:
            if original["source_id"] not in {r["source_id"] for r in sources}:
                sources.append({"source_id": original["source_id"], "status": "unavailable", "payload": {},
                                "source_current": False})
        return {"course_id": course_id, "draft_id": draft_id, "status": group["status"],
                "input_digest": group["input_digest"], "revision_digest": digest(sources), "sources": sources}

    def extract_source(self, course_id: str, draft_id: str, source_id: str,
                       request_key: str, allow_external_model: bool) -> dict[str, Any]:
        request_key_valid(request_key)
        command = digest({"draft_id": draft_id, "source_id": source_id})
        call = False
        with transaction(self.storage) as conn:
            group = self._group(conn, course_id, draft_id)
            row = conn.execute("SELECT * FROM kg_extractions WHERE course_id=? AND draft_id=? AND source_id=?",
                               (course_id, draft_id, source_id)).fetchone()
            if row is None:
                raise CourseGraphError("extraction_not_found", 404)
            if row["mode"] == "llm" and allow_external_model is not True:
                raise CourseGraphError("model_consent_required", 422)
            repeated = get_request(conn, course_id, request_key, "extract", command)
            if not repeated:
                if group["status"] != "applied":
                    raise CourseGraphError("draft_cancelled")
                if not self._current(conn, row):
                    raise CourseGraphError("source_changed")
                if row["status"] == "running":
                    raise CourseGraphError("extraction_busy")
                record_change(conn, course_id, request_key, "extract", command,
                              {"draft_id": draft_id, "source_id": source_id, "extraction_id": row["extraction_id"]})
                if row["status"] not in {"ready", "partial"}:
                    cached = conn.execute("""SELECT extraction_id,payload,status FROM kg_extractions
                                             WHERE course_id=? AND input_digest=? AND mode=? AND extractor_version=?
                                             AND status IN ('ready','partial') AND extraction_id!=?
                                             ORDER BY created_at LIMIT 1""",
                                          (course_id, row["input_digest"], row["mode"], EXTRACTOR_VERSION,
                                           row["extraction_id"])).fetchone()
                    if cached:
                        payload = copy.deepcopy(json.loads(cached["payload"]))
                        payload["cache_origin"] = cached["extraction_id"]
                        for item in payload.get("nodes", []) + payload.get("edges", []):
                            item["decision"] = "pending"
                            item.pop("revision", None)
                            item.pop("review_status", None)
                            item.pop("published_id", None)
                        conn.execute("UPDATE kg_extractions SET status=?,payload=?,error_code=NULL,updated_at=? WHERE extraction_id=?",
                                     (cached["status"], json.dumps(payload, ensure_ascii=False), self._now().isoformat(),
                                      row["extraction_id"]))
                    else:
                        call, epoch = True, row["epoch"] + 1
                        source = self.storage.get_source(source_id)
                        text = source["raw_text"]
                        chunks = self.storage.list_source_chunks(source_id)
                        conn.execute("""UPDATE kg_extractions SET status='running',epoch=?,lease_until=?,payload='{}',
                                        error_code=NULL,updated_at=? WHERE extraction_id=?""",
                                     (epoch, (self._now() + timedelta(seconds=60)).isoformat(),
                                      self._now().isoformat(), row["extraction_id"]))
        if not call:
            return self.snapshot(course_id, draft_id)
        error = None
        payload = {}
        try:
            raw = self.provider_factory().extract(text[:INPUT_LIMIT]) if row["mode"] == "llm" else extract_local_course(text)
            payload = validate_candidates(raw, text, source_id, chunks)
        except BudgetExceeded:
            error = "budget_exceeded"
        except GovernanceUnavailable:
            error = "governance_unavailable"
        except Exception:  # noqa: BLE001 -- 第三方适配器异常只保留固定码，避免正文或密钥泄漏。
            error = "extraction_failed"
        with transaction(self.storage) as conn:
            current = conn.execute("SELECT * FROM kg_extractions WHERE extraction_id=?", (row["extraction_id"],)).fetchone()
            if current and current["epoch"] == epoch and current["status"] == "running":
                if (not self._current(conn, current) or current["lease_until"] <= self._now().isoformat()
                        or self._group(conn, course_id, draft_id)["status"] != "applied"):
                    conn.execute("""UPDATE kg_extractions SET status='interrupted',epoch=epoch+1,lease_until=NULL,
                                    payload='{}',error_code='input_changed',updated_at=? WHERE extraction_id=?""",
                                 (self._now().isoformat(), current["extraction_id"]))
                else:
                    status = "failed" if error else "partial" if payload["issues"] else "ready"
                    conn.execute("""UPDATE kg_extractions SET status=?,payload=?,error_code=?,lease_until=NULL,
                                    updated_at=? WHERE extraction_id=?""",
                                 (status, json.dumps(payload, ensure_ascii=False), error,
                                  self._now().isoformat(), current["extraction_id"]))
        return self.snapshot(course_id, draft_id)

    def cancel(self, course_id: str, draft_id: str, request_key: str) -> dict[str, Any]:
        request_key_valid(request_key)
        hashed = digest({"draft_id": draft_id})
        with transaction(self.storage) as conn:
            self._group(conn, course_id, draft_id)
            if not get_request(conn, course_id, request_key, "cancel", hashed):
                record_change(conn, course_id, request_key, "cancel", hashed, {"draft_id": draft_id})
                conn.execute("UPDATE kg_changes SET status='cancelled',updated_at=? WHERE operation_id=?",
                             (self._now().isoformat(), draft_id))
                conn.execute("""UPDATE kg_extractions SET status='cancelled',epoch=epoch+1,lease_until=NULL,
                                payload='{}',updated_at=? WHERE course_id=? AND draft_id=?
                                AND status IN ('pending','running','failed','interrupted')""",
                             (self._now().isoformat(), course_id, draft_id))
        return self.snapshot(course_id, draft_id)
