"""把岗位实际训练记录转换为可确认、可撤销的现役学习计划。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from filemate.execution.storage import _now_iso

from .repository import digest

if TYPE_CHECKING:
    from .repository import CareerRepository


class CareerPlans:
    def __init__(self, repository: CareerRepository) -> None:
        self.repository = repository
        self.storage = repository.storage

    def raw(self, position_id: str) -> list[dict[str, Any]]:
        """按持久事件关联读取计划，载荷损坏也保留删除归属。"""
        return [
            dict(row)
            for row in self.storage._conn().execute(
                "SELECT p.*,a.content,a.metadata FROM study_plans p JOIN artifacts a "
                "ON a.artifact_id=p.artifact_id WHERE p.plan_id IN "
                "(SELECT CASE WHEN json_valid(detail) THEN json_extract(detail,'$.plan_id') END "
                "FROM career_events WHERE position_id=? AND action='plan_saved') "
                "ORDER BY p.created_at DESC,p.rowid DESC",
                (position_id,),
            )
        ]

    @staticmethod
    def view(row: dict[str, Any], position_id: str) -> dict[str, Any]:
        """读取原计划和进度，损坏时标记而不改写原字节。"""
        result = {
            key: row[key]
            for key in (
                "plan_id",
                "artifact_id",
                "title",
                "status",
                "created_at",
                "updated_at",
            )
        }
        try:
            for field in ("created_at", "updated_at"):
                timestamp = datetime.fromisoformat(row[field])
                result[field] = (
                    timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
                ).isoformat()
            plan, completed, metadata = (
                json.loads(row[key]) for key in ("plan_data", "completed_days", "metadata")
            )
            if (
                not isinstance(metadata, dict)
                or metadata.get("origin") != "career_plan"
                or metadata.get("position_id") != position_id
                or not isinstance(plan, dict)
                or plan != json.loads(row["content"])
            ):
                raise ValueError("plan ownership or snapshot")
            days = plan["daily_plan"]
            if (
                not isinstance(days, list)
                or not 1 <= len(days) <= 7
                or not isinstance(completed, list)
                or any(type(item) is not int or not 0 <= item < len(days) for item in completed)
                or len(set(completed)) != len(completed)
                or row["status"] not in {"active", "archived", "completed"}
                or plan.get("daily_minutes") != 30
            ):
                raise ValueError("plan structure")
            basis = plan.get("career_basis")
            if (
                not isinstance(basis, dict)
                or basis.get("position_id") != position_id
                or basis.get("version") != "career-plan-v1"
                or basis.get("evidence_revision") != metadata.get("evidence_revision")
            ):
                raise ValueError("plan evidence")
            for index, day in enumerate(days):
                if (
                    not isinstance(day, dict)
                    or day.get("day") != index + 1
                    or not isinstance(day.get("focus"), str)
                    or not day["focus"]
                    or day.get("duration_minutes") != 30
                    or not isinstance(day.get("tasks"), list)
                    or not day["tasks"]
                    or any(not isinstance(task, str) or not task for task in day["tasks"])
                    or not isinstance(day.get("training_actions"), list)
                ):
                    raise ValueError("plan day")
                datetime.fromisoformat(day["date"])
                for action in day["training_actions"]:
                    if (
                        not isinstance(action, dict)
                        or not isinstance(action.get("label"), str)
                        or not isinstance(action.get("route"), str)
                        or action["route"].split("?")[0]
                        not in {"/career", "/knowledge-graph", "/programming", "/interview"}
                    ):
                        raise ValueError("plan route")
            result.update(plan_data=plan, completed_days=completed, data_error=False)
        except (ValueError, TypeError, KeyError):
            result.update(plan_data=None, completed_days=[], data_error=True)
        return result

    def list(self, position_id: str) -> list[dict[str, Any]]:
        """撤销岗位仍可回看由它创建的学习计划。"""
        self.repository.get(position_id)
        return [self.view(row, position_id) for row in self.raw(position_id)]

    def preview(self, position_id: str) -> dict[str, Any]:
        """预览确定性建议，只依据当前有效证据，不生成能力分数。"""
        with self.storage._write_lock:
            role = self.repository.usable(position_id)
            comparison = self.repository.comparison(position_id)
            latest: dict[str, tuple[datetime, int, int, str, bool]] = {}
            now = datetime.now(timezone.utc)
            for row in self.storage._conn().execute(
                "SELECT t.training_id,t.rowid,"
                "(SELECT MAX(e.event_id) FROM career_events e WHERE e.training_id=t.training_id "
                "AND e.action='written_submitted') AS answer_order "
                "FROM career_trainings t WHERE t.position_id=? AND t.kind='written'",
                (position_id,),
            ):
                training = self.repository.training(row[0])
                if training["data_error"] or not training["payload"].get("result"):
                    continue
                payload = training["payload"]
                submitted = datetime.fromisoformat(payload["result"]["submitted_at"])
                if submitted > now:
                    continue
                for question in payload["questions"]:
                    key = question["skill"]
                    item = (
                        submitted,
                        row["answer_order"] or 0,
                        row["rowid"],
                        training["training_id"],
                        payload["result"]["answers"][question["id"]] == question["correct"],
                    )
                    if key not in latest or item[:3] > latest[key][:3]:
                        latest[key] = item
            steps = []
            for skill in comparison["skills"]:
                label = skill["label"]
                answered = latest.get(label)
                pending = sum(
                    node["metrics"]["pending_wrong_count"] for node in skill["graph_nodes"]
                )
                coding = skill["coding_evidence"][0] if skill["coding_evidence"] else None
                failed = bool(
                    (answered and not answered[4])
                    or pending
                    or (coding and coding["verdict"] != "AC")
                )
                sampled = bool(answered or skill["recent_graph_samples"] or skill["coding_count"])
                status = "建议复练" if failed else "继续验证" if sampled else "待评测"
                reasons, actions = [], []
                if answered:
                    reasons.append(
                        f"最近一轮该知识点基础题{'答对' if answered[4] else '答错'}（{answered[0].date().isoformat()}）；训练 {answered[3]}"
                    )
                    actions.append(
                        {
                            "label": "回看基础作答",
                            "route": "/career?"
                            + urlencode({"position": position_id, "training": answered[3]}),
                        }
                    )
                if skill["graph_nodes"]:
                    node = skill["graph_nodes"][0]
                    reasons.append(
                        f"关联知识节点最近窗口共有{skill['recent_graph_samples']}次作答、{pending}条待复习关联，节点之间可能重合"
                    )
                    actions.append(
                        {
                            "label": "回看知识出处",
                            "route": "/knowledge-graph?" + urlencode({"node": node["id"]}),
                        }
                    )
                if coding:
                    reasons.append(
                        f"最近相关C++17提交为{coding['verdict']}；提交 {coding['submission_id']}"
                    )
                    actions.append(
                        {
                            "label": "回看代码提交",
                            "route": "/programming?"
                            + urlencode({"submission": coding["submission_id"]}),
                        }
                    )
                if skill["category"] in {"project", "communication"} and comparison["interviews"]:
                    interview = comparison["interviews"][0]
                    reasons.append(
                        f"该岗位已保存{sum(item['answered'] for item in comparison['interviews'])}题口头回答，需人工核对原回答"
                    )
                    actions.append(
                        {
                            "label": "回看岗位面试",
                            "route": "/interview?"
                            + urlencode({"interview": interview["interview_id"]}),
                        }
                    )
                if not reasons:
                    reasons.append(
                        "尚无相关作答记录，先核对岗位原句并建立一次练习记录；未记录不代表不会"
                    )
                if label in {"Python", "Java"}:
                    reasons.append("当前代码执行仅支持C++17，请使用知识练习或口头说明验证此语言")
                actions.append(
                    {
                        "label": "继续岗位训练",
                        "route": "/career?" + urlencode({"position": position_id}),
                    }
                )
                steps.append(
                    {
                        "label": label,
                        "status": status,
                        "priority": "high" if failed else "medium",
                        "requirement_quote": skill["evidence"],
                        "reason": "；".join(reasons),
                        "actions": actions,
                        "order": len(steps),
                    }
                )
            steps.sort(
                key=lambda step: (
                    0 if step["status"] == "建议复练" else 1 if step["status"] == "待评测" else 2,
                    step["order"],
                )
            )
            steps = [
                {key: value for key, value in step.items() if key != "order"} for step in steps[:7]
            ]
            today = datetime.now(timezone.utc).astimezone().date()
            basis = {
                "version": "career-plan-v1",
                "position_id": position_id,
                "position_revision": role["revision"],
                "date": today.isoformat(),
                "steps": steps,
            }
            revision = digest(basis)
            method = "本地公开规则优先安排最近基础作答错误、待复习关联或最近失败代码提交；未训练项待评测。最多安排7项、每天建议30分钟，按最新证据另存计划，保留已有计划和进度。"
            plan = {
                "title": f"{role['position']['title']} · 岗位学习计划",
                "goal": "用实际练习验证岗位相关知识",
                "exam_date": (today + timedelta(days=len(steps))).isoformat(),
                "daily_minutes": 30,
                "total_days": len(steps),
                "strategy": method,
                "review_strategy": "训练量不代表能力达标或录用结果；完成后可根据新作答重新预览。",
                "checkpoints": [],
                "topics": [
                    {"name": step["label"], "priority": step["priority"], "reason": step["reason"]}
                    for step in steps
                ],
                "daily_plan": [
                    {
                        "day": index + 1,
                        "date": (today + timedelta(days=index)).isoformat(),
                        "focus": step["label"],
                        "review_method": "核对出处 + 主动回忆 + 一次练习",
                        "duration_minutes": 30,
                        "tasks": [
                            step["reason"],
                            "核对岗位原句，完成相关练习并保存结果，再用自己的话解释",
                        ],
                        "training_actions": step["actions"],
                    }
                    for index, step in enumerate(steps)
                ],
                "career_basis": basis | {"evidence_revision": revision},
            }
            return {
                "position_id": position_id,
                "position_revision": role["revision"],
                "steps": steps,
                "requirements_total": len(comparison["skills"]),
                "evidence_revision": revision,
                "method": method,
                "plan": plan,
            }

    def save(self, position_id: str, revision: str) -> dict[str, Any]:
        """确认当前证据后原子新增计划，已接收请求重试保留原进度。"""
        key = f"filemate:career-plan:{position_id}:{revision}"
        plan_id = uuid.uuid5(uuid.NAMESPACE_URL, key + ":plan").hex
        artifact_id = uuid.uuid5(uuid.NAMESPACE_URL, key + ":artifact").hex
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = next(
                (row for row in self.raw(position_id) if row["plan_id"] == plan_id), None
            )
            if existing:
                saved = self.view(existing, position_id)
                if saved["data_error"]:
                    raise ValueError("原计划数据异常，原字节保留，请重新预览")
                return saved
            preview = self.preview(position_id)
            if preview["evidence_revision"] != revision:
                raise ValueError("岗位或学习证据已变化，请重新预览后确认")
            plan = preview["plan"]
            now = _now_iso()
            content = json.dumps(plan, ensure_ascii=False)
            metadata = json.dumps(
                {
                    "origin": "career_plan",
                    "position_id": position_id,
                    "position_revision": preview["position_revision"],
                    "evidence_revision": revision,
                    "version": "career-plan-v1",
                }
            )
            conn.execute(
                "INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,title,content,metadata,created_at,updated_at) VALUES(?,'local','study_plan',?,?,?,?,?)",
                (artifact_id, plan["title"], content, metadata, now, now),
            )
            conn.execute(
                "INSERT INTO study_plans(plan_id,artifact_id,title,exam_date,daily_minutes,goal,plan_data,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    plan_id,
                    artifact_id,
                    plan["title"],
                    plan["exam_date"],
                    30,
                    plan["goal"],
                    content,
                    now,
                    now,
                ),
            )
            self.repository.event(
                position_id,
                "plan_saved",
                detail={"plan_id": plan_id, "days": len(preview["steps"])},
            )
        return next(plan for plan in self.list(position_id) if plan["plan_id"] == plan_id)

    def transition(self, position_id: str, plan_id: str, action: str) -> dict[str, Any]:
        """仅撤销或恢复本岗位创建的计划，保留已完成日期。"""
        if action not in {"undo", "restore"}:
            raise ValueError("无效计划状态")
        with self.storage._write_lock, self.storage._conn() as conn:
            raw = next((row for row in self.raw(position_id) if row["plan_id"] == plan_id), None)
            if raw is None:
                raise KeyError(plan_id)
            plan = self.view(raw, position_id)
            if action == "restore" and plan["data_error"]:
                raise ValueError("学习计划数据异常，原字节保留，不能恢复")
            status = (
                "archived"
                if action == "undo"
                else "completed"
                if len(plan["completed_days"]) == len(plan["plan_data"]["daily_plan"])
                else "active"
            )
            if plan["status"] != status:
                conn.execute(
                    "UPDATE study_plans SET status=?,updated_at=? WHERE plan_id=?",
                    (status, _now_iso(), plan_id),
                )
                self.repository.event(position_id, "plan_" + action, detail={"plan_id": plan_id})
        return next(plan for plan in self.list(position_id) if plan["plan_id"] == plan_id)
