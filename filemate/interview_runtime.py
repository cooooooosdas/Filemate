"""Server-owned continuous clock, bounded simulated tasks and durable receipts."""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from filemate.interview_coach.models import CoachMutationResult, Command, SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository, digest, freeze_question
from filemate.interview_config import DraftContent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def guard_legacy_write(conn, sid: str) -> None:
    if conn.execute("SELECT 1 FROM interview_runtime WHERE interview_id=?", (sid,)).fetchone():
        raise CoachError("runtime_command_required")


def runtime_projection(conn, sid: str, timestamp: datetime | None = None) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM interview_runtime WHERE interview_id=?", (sid,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result.pop("prepare_key")
    result.pop("prepare_digest")
    instant = timestamp or utc_now()
    result["server_now"] = instant.isoformat()
    result["remaining_seconds"] = (
        max(0, (datetime.fromisoformat(row["deadline"]) - instant).total_seconds())
        if row["deadline"]
        else row["duration_seconds"]
    )
    result["event_cooldown_seconds"] = (
        max(0, 15 - (instant - datetime.fromisoformat(row["last_audience_at"])).total_seconds())
        if row["last_audience_at"]
        else 0
    )
    result["tasks"] = [
        dict(r)
        for r in conn.execute(
            "SELECT task_index,task_id,kind,title,prompt,status,attempt_id FROM interview_tasks WHERE interview_id=? ORDER BY task_index",
            (sid,),
        )
    ]
    result["events"] = [
        dict(r)
        for r in conn.execute(
            "SELECT sequence,event_key,kind,task_index,text,attempt_id,created_at FROM interview_events WHERE interview_id=? ORDER BY sequence",
            (sid,),
        )
    ]
    return result


def runtime_evidence(runtime: dict[str, Any] | None) -> dict[str, Any] | None:
    if runtime is None:
        return None
    return {
        k: runtime[k] for k in ("status", "started_at", "deadline", "ended_at", "tasks", "events")
    }


def normalize_restored_runtime(conn) -> None:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='interview_runtime'"
    ).fetchone():
        return
    conn.execute("UPDATE interview_runtime SET status='interrupted' WHERE status='running'")
    for row in conn.execute("SELECT interview_id FROM interview_runtime").fetchall():
        conn.execute(
            "UPDATE interview_runtime SET revision=revision+1,version_token=? WHERE interview_id=?",
            (uuid.uuid4().hex, row[0]),
        )


def reserve_runtime_ai(conn, sid: str) -> None:
    row = conn.execute("SELECT * FROM interview_runtime WHERE interview_id=?", (sid,)).fetchone()
    if not row:
        return
    if row["status"] != "running" or (
        row["deadline"] and utc_now() >= datetime.fromisoformat(row["deadline"])
    ):
        raise CoachError("runtime_not_running")
    if row["ai_reserved"] + 2 > 12:
        raise CoachError("runtime_ai_budget_exhausted", 429)
    # The evaluator permits one repair: reserving both calls also bounds failed runs.
    conn.execute(
        "UPDATE interview_runtime SET ai_reserved=ai_reserved+2 WHERE interview_id=?", (sid,)
    )


def runtime_analysis_allowed(conn, sid: str) -> bool:
    row = conn.execute(
        "SELECT status,deadline FROM interview_runtime WHERE interview_id=?", (sid,)
    ).fetchone()
    return row is None or (
        row["status"] == "running"
        and bool(row["deadline"])
        and utc_now() < datetime.fromisoformat(row["deadline"])
    )


class RuntimeCommand(Command):
    kind: Literal["start", "resume", "submit", "advance", "event", "skip", "finish"]
    expected_token: str = Field(min_length=16, max_length=80)
    task_index: int | None = Field(default=None, ge=0, le=100)
    answer: str | None = Field(default=None, min_length=1, max_length=12000)
    expected_attempt_id: str | None = Field(default=None, max_length=80)
    fluency_metrics: dict[str, Any] | None = None
    visual_metrics: dict[str, Any] | None = None


class PrepareRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: DraftContent
    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


def build_tasks(content: DraftContent, seed: str) -> list[dict[str, Any]]:
    config = content.configuration
    scenario = config.session_scenario()
    facts = content.project_details.strip()
    if config.category == "creator" and not facts:
        raise ValueError("请先填写讲解主题与资料事实，或商品的已知事实；未知信息请明确标注")
    rng = random.Random(seed)
    topics = {
        "knowledge": [
            "用一个具体例子解释核心概念，并指出例子的适用边界。",
            "从新手最容易误解的一点开始，解释原理与实际用途。",
        ],
        "commerce": [
            "介绍商品的已知特点、适合的使用情境和信息缺口。",
            "回应一位需要比较商品的观众，说明已知信息与仍需核实之处。",
        ],
    }
    track = config.track if config.category == "creator" else "interview"
    topic = topics.get(
        track,
        [f"围绕{content.target_role or scenario}，说明一次真实实践、具体行动和可核实的结果。"],
    )
    selected = rng.choice(topic) if config.question_strategy == "random" else topic[0]
    rule = (
        "只使用下面给定的事实；不得编造效果、价格、资质或承诺。"
        if track == "commerce"
        else "只使用给定事实或自己的真实经历；不确定的内容请明确说明。"
    )
    prompts = [
        f"请做简短开场，说明你是谁、本次主题是什么，以及听众能获得什么。训练场景：{scenario}。",
        f"{selected}\n{rule}\n给定事实：{facts or '未提供资料；请以自己的真实经历作答。'}",
        (
            "模拟观众追问：你有什么证据支持刚才的说法？如果信息未知，你会怎样回应？"
            if track == "commerce"
            else "模拟听众追问：我还是不理解。请换一种解释，并指出你还不能确定的地方。"
        ),
        "请回顾本场表达：哪些说法有事实依据，哪些问题尚待核实，下一次具体改进什么？",
    ]
    return [
        {
            "task_index": i,
            "task_id": f"{seed[:12]}_{i}",
            "kind": kind,
            "title": title,
            "prompt": prompt,
        }
        for i, (kind, title, prompt) in enumerate(
            zip(
                ["opening", "topic", "challenge", "review"],
                ["开场展示", "主题任务", "互动挑战", "复盘"],
                prompts,
            )
        )
    ]


class RuntimeRepository:
    def __init__(self, storage, *, clock: Callable[[], datetime] = utc_now):
        self.storage = storage
        self.coach = CoachRepository(storage)
        self.clock = clock

    def prepare(self, content: DraftContent, request_key: str):
        if content.configuration.execution_mode != "timed":
            raise ValueError("连续计时会话需要选择实战模式")
        scenario = content.configuration.session_scenario()
        if content.source_id:
            raise ValueError("实战模式请粘贴已授权的主题／商品事实；本阶段不自动发送课程资料")
        with self.coach.transaction() as conn:
            old = conn.execute(
                "SELECT interview_id,prepare_digest FROM interview_runtime WHERE prepare_key=?",
                (request_key,),
            ).fetchone()
            if old:
                if old["prepare_digest"] != digest(content.model_dump()):
                    raise CoachError("runtime_request_conflict")
                return self.coach.snapshot(old["interview_id"])
            seed = uuid.uuid4().hex
            tasks = build_tasks(content, seed)
            session = self.storage.create_interview(
                target_role=content.target_role or scenario,
                scenario=scenario,
                difficulty=content.configuration.difficulty,
                questions=[t["prompt"] for t in tasks],
                configuration=content.configuration.model_dump(),
                commit=False,
            )
            sid = session["interview_id"]
            conn.execute(
                "INSERT INTO interview_runtime(interview_id,status,version_token,seed,duration_seconds,prepare_key,prepare_digest) VALUES (?,'prepared',?,?,?,?,?)",
                (
                    sid,
                    uuid.uuid4().hex,
                    seed,
                    content.configuration.duration_minutes * 60,
                    request_key,
                    digest(content.model_dump()),
                ),
            )
            for task in tasks:
                conn.execute(
                    "INSERT INTO interview_tasks(interview_id,task_index,task_id,kind,title,prompt) VALUES (?,?,?,?,?,?)",
                    (
                        sid,
                        task["task_index"],
                        task["task_id"],
                        task["kind"],
                        task["title"],
                        task["prompt"],
                    ),
                )
        return self.snapshot(sid)

    def _event(self, conn, sid, key, kind, *, text="", input_digest="", receipt=None):
        row = conn.execute(
            "SELECT current_task FROM interview_runtime WHERE interview_id=?", (sid,)
        ).fetchone()
        seq = conn.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM interview_events WHERE interview_id=?", (sid,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO interview_events(interview_id,sequence,event_key,kind,task_index,text,created_at,input_digest,receipt) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                sid,
                seq,
                key,
                kind,
                row[0],
                text,
                self.clock().isoformat(),
                input_digest,
                json.dumps(receipt or {}),
            ),
        )

    def _end(self, conn, sid, status):
        conn.execute(
            "UPDATE interview_runtime SET status=?,ended_at=?,revision=revision+1 WHERE interview_id=?",
            (status, self.clock().isoformat(), sid),
        )
        conn.execute(
            "UPDATE interview_sessions SET status='completed',updated_at=? WHERE interview_id=?",
            (self.clock().isoformat(), sid),
        )
        conn.execute(
            "UPDATE interview_coach_state SET phase='summary',external_consent=0,consent_revision=consent_revision+1,revision=revision+1 WHERE interview_id=?",
            (sid,),
        )
        conn.execute(
            "UPDATE interview_coach_analysis_runs SET status='cancelling' WHERE interview_id=? AND status='running'",
            (sid,),
        )
        conn.execute(
            "UPDATE interview_review_state SET revision=revision+1,input_digest='' WHERE interview_id=?",
            (sid,),
        )
        self._event(conn, sid, uuid.uuid4().hex, status)

    def snapshot(self, sid):
        with self.coach.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM interview_runtime WHERE interview_id=?", (sid,)
            ).fetchone()
            if not row:
                raise CoachError("runtime_not_found", 404)
            if (
                row["status"] in {"running", "interrupted"}
                and row["deadline"]
                and self.clock() >= datetime.fromisoformat(row["deadline"])
            ):
                self._end(conn, sid, "expired")
        result = self.coach.snapshot(sid)
        result.session["runtime"] = runtime_projection(self.storage._conn(), sid, self.clock())
        return result

    def command(self, sid, command: RuntimeCommand) -> CoachMutationResult:
        self.snapshot(sid)
        with self.coach.transaction() as conn:
            old = conn.execute(
                "SELECT * FROM interview_events WHERE interview_id=? AND event_key=?",
                (sid, command.request_key),
            ).fetchone()
            if old:
                if old["input_digest"] != digest(command.model_dump()):
                    raise CoachError("runtime_request_conflict")
                receipt = json.loads(old["receipt"])
            else:
                row = conn.execute(
                    "SELECT * FROM interview_runtime WHERE interview_id=?", (sid,)
                ).fetchone()
                if row["version_token"] != command.expected_token:
                    raise CoachError("runtime_token_conflict")
                if row["status"] in {"finished", "expired"}:
                    raise CoachError("runtime_not_running")
                if row["revision"] != command.expected_revision:
                    raise CoachError("runtime_revision_conflict")
                if command.task_index is not None and command.task_index != row["current_task"]:
                    raise CoachError("runtime_task_conflict")
                self._apply(conn, sid, row, command)
                conn.execute(
                    "UPDATE interview_runtime SET revision=revision+1 WHERE interview_id=?", (sid,)
                )
                receipt = {
                    "request_key": command.request_key,
                    "kind": command.kind,
                    "task_index": row["current_task"],
                }
                if command.kind == "submit":
                    receipt["attempt_id"] = conn.execute(
                        "SELECT attempt_id FROM interview_tasks WHERE interview_id=? AND task_index=?",
                        (sid, row["current_task"]),
                    ).fetchone()[0]
                self._event(
                    conn,
                    sid,
                    command.request_key,
                    command.kind,
                    input_digest=digest(command.model_dump()),
                    receipt=receipt,
                )
        return CoachMutationResult(snapshot=self.snapshot(sid), receipt=receipt)

    def _apply(self, conn, sid, row, cmd):
        instant = self.clock()
        if cmd.kind in {"start", "resume"}:
            wanted = "prepared" if cmd.kind == "start" else "interrupted"
            if row["status"] != wanted:
                raise CoachError("runtime_not_startable")
            deadline = (
                row["deadline"]
                or (instant + timedelta(seconds=row["duration_seconds"])).isoformat()
            )
            conn.execute(
                "UPDATE interview_runtime SET status='running',started_at=COALESCE(started_at,?),deadline=? WHERE interview_id=?",
                (instant.isoformat(), deadline, sid),
            )
            conn.execute(
                "UPDATE interview_tasks SET status='active' WHERE interview_id=? AND task_index=? AND status='pending'",
                (sid, row["current_task"]),
            )
            return
        if cmd.kind == "finish" and row["status"] in {"prepared", "interrupted", "running"}:
            self._end(conn, sid, "finished")
            return
        if row["status"] != "running" or instant >= datetime.fromisoformat(row["deadline"]):
            raise CoachError("runtime_not_running")
        if cmd.task_index is None:
            raise CoachError("runtime_task_required", 422)
        index = row["current_task"]
        task = conn.execute(
            "SELECT * FROM interview_tasks WHERE interview_id=? AND task_index=?", (sid, index)
        ).fetchone()
        if cmd.kind == "submit":
            from filemate.interview_coach.commands import local_evaluation

            if not cmd.answer or not cmd.answer.strip():
                raise CoachError("runtime_answer_required", 422)
            state = self.coach._state(conn, sid)
            answer = SubmitAnswer(
                request_key=cmd.request_key,
                expected_revision=state["revision"],
                question_index=index,
                answer=cmd.answer,
                expected_attempt_id=cmd.expected_attempt_id,
                fluency_metrics=cmd.fluency_metrics,
                visual_metrics=cmd.visual_metrics,
            )
            result = self.coach._submit_in_transaction(
                conn,
                sid,
                answer,
                local_evaluation(answer.answer, answer.fluency_metrics, speech_language="zh-CN"),
            )
            attempt_id = result.snapshot.current_attempt.attempt_id
            conn.execute(
                "UPDATE interview_sessions SET status='active' WHERE interview_id=?", (sid,)
            )
            conn.execute(
                "UPDATE interview_tasks SET status='answered',attempt_id=? WHERE interview_id=? AND task_index=?",
                (attempt_id, sid, index),
            )
            conn.execute(
                "UPDATE interview_events SET attempt_id=? WHERE interview_id=? AND task_index=? AND kind='audience' AND attempt_id IS NULL",
                (attempt_id, sid, index),
            )
        elif cmd.kind in {"advance", "skip"}:
            if cmd.kind == "skip":
                if task["kind"] != "challenge" or task["status"] == "answered":
                    raise CoachError("runtime_task_not_skippable")
                conn.execute(
                    "UPDATE interview_tasks SET status='skipped' WHERE interview_id=? AND task_index=?",
                    (sid, index),
                )
            elif task["status"] != "answered" or cmd.expected_attempt_id != task["attempt_id"]:
                raise CoachError("attempt_conflict")
            if index == 3:
                self._end(conn, sid, "finished")
            else:
                target = index + 1
                next_task = conn.execute(
                    "SELECT * FROM interview_tasks WHERE interview_id=? AND task_index=?",
                    (sid, target),
                ).fetchone()
                freeze_question(conn, sid, target, next_task["prompt"], instant.isoformat())
                conn.execute(
                    "UPDATE interview_runtime SET current_task=? WHERE interview_id=?",
                    (target, sid),
                )
                conn.execute(
                    "UPDATE interview_tasks SET status='active' WHERE interview_id=? AND task_index=?",
                    (sid, target),
                )
                conn.execute(
                    "UPDATE interview_sessions SET current_index=?,status='active' WHERE interview_id=?",
                    (target, sid),
                )
                entered = [
                    r[0]
                    for r in conn.execute(
                        "SELECT question_index FROM interview_coach_questions WHERE interview_id=? ORDER BY question_index",
                        (sid,),
                    )
                ]
                conn.execute(
                    "UPDATE interview_coach_state SET displayed_index=?,phase='question',entered_indices=?,revision=revision+1 WHERE interview_id=?",
                    (target, json.dumps(entered), sid),
                )
        elif cmd.kind == "event":
            if row["audience_count"] >= 30:
                raise CoachError("runtime_event_limit", 429)
            if (
                row["last_audience_at"]
                and (instant - datetime.fromisoformat(row["last_audience_at"])).total_seconds() < 15
            ):
                raise CoachError("runtime_event_cooldown", 429)
            comments = [
                "能举一个具体例子吗？",
                "这条信息有什么依据？",
                "如果条件变化，你的说法还成立吗？",
                "能用一句话总结重点吗？",
            ]
            text = comments[
                random.Random(f"{row['seed']}:{row['audience_count']}").randrange(len(comments))
            ]
            self._event(
                conn, sid, f"audience_{row['audience_count']}", "audience", text=f"模拟观众：{text}"
            )
            conn.execute(
                "UPDATE interview_runtime SET audience_count=audience_count+1,last_audience_at=? WHERE interview_id=?",
                (instant.isoformat(), sid),
            )
