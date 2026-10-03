"""岗位、训练快照与有限事件的原子持久化。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from filemate.execution.storage import SQLiteStorage, _now_iso

from .catalog import CATALOG
from .evidence import basic_questions, compare, interview_questions, recommended_problems
from .models import Position


def digest(value: Any) -> str:
    """将当前记录绑定到确认和幂等请求。"""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class CareerRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def event(
        self,
        position_id: str | None,
        action: str,
        training_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.storage._conn().execute(
            "INSERT INTO career_events(position_id,training_id,action,detail,created_at) VALUES(?,?,?,?,?)",
            (position_id, training_id, action, json.dumps(detail or {}), _now_iso()),
        )

    def get(self, identifier: str) -> dict[str, Any]:
        row = (
            self.storage._conn()
            .execute("SELECT * FROM career_positions WHERE position_id=?", (identifier,))
            .fetchone()
        )
        if not row:
            raise KeyError(identifier)
        result = dict(row)
        try:
            result["position"] = Position.model_validate_json(result.pop("payload")).model_dump(
                mode="json"
            )
            result["data_error"] = False
            collected = datetime.fromisoformat(result["position"]["collected_at"])
            result["age_days"] = max(0, (datetime.now(timezone.utc) - collected).days)
        except (ValueError, TypeError):
            result.update(position=None, data_error=True, age_days=None)
        result.pop("request_key", None)
        return result

    def usable(self, identifier: str, expected_revision: int | None = None) -> dict[str, Any]:
        row = self.get(identifier)
        if row["data_error"]:
            raise ValueError("岗位数据异常，原记录保留；可确认删除后重新导入")
        if not row["active"]:
            raise ValueError("岗位已撤销，请先恢复再创建训练")
        if expected_revision is not None and row["revision"] != expected_revision:
            raise ValueError("岗位要求已更新，请刷新后重新确认")
        return row

    def list(self) -> list[dict[str, Any]]:
        return [
            self.get(row[0])
            for row in self.storage._conn().execute(
                "SELECT position_id FROM career_positions ORDER BY updated_at DESC,rowid DESC LIMIT 200"
            )
        ]

    @staticmethod
    def verify_origin(position: dict[str, Any]) -> None:
        if position["source_kind"] == "official_snapshot" and position not in CATALOG:
            raise ValueError("仅内置已核对快照可标记为官方来源；自行导入请选用户导入")

    def create(self, position: dict[str, Any], key: str) -> dict[str, Any]:
        position = Position.model_validate(position).model_dump(mode="json")
        self.verify_origin(position)
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            prior = conn.execute(
                "SELECT position_id,payload FROM career_positions WHERE request_key=?", (key,)
            ).fetchone()
            if prior:
                if digest(json.loads(prior["payload"])) != digest(position):
                    raise ValueError("保存键已用于其他岗位内容")
                return self.get(prior["position_id"])
            identifier, now = uuid.uuid4().hex, _now_iso()
            conn.execute(
                "INSERT INTO career_positions(position_id,request_key,payload,created_at,updated_at) VALUES(?,?,?,?,?)",
                (identifier, key, json.dumps(position, ensure_ascii=False), now, now),
            )
            self.event(
                identifier, "created", detail={"requirements": len(position["requirements"])}
            )
        return self.get(identifier)

    def edit(self, identifier: str, position: dict[str, Any], revision: int) -> dict[str, Any]:
        position = Position.model_validate(position).model_dump(mode="json")
        self.verify_origin(position)
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            old = self.usable(identifier)
            if old["position"] == position:
                return old
            if old["revision"] != revision:
                raise ValueError("岗位已更新，请刷新后重新编辑")
            conn.execute(
                "UPDATE career_positions SET payload=?,revision=revision+1,updated_at=? WHERE position_id=?",
                (json.dumps(position, ensure_ascii=False), _now_iso(), identifier),
            )
            self.event(identifier, "edited")
        return self.get(identifier)

    def transition(self, identifier: str, action: Literal["undo", "restore"]) -> dict[str, Any]:
        if action not in {"undo", "restore"}:
            raise ValueError("无效岗位状态")
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            old = self.get(identifier)
            if action == "restore" and old["data_error"]:
                raise ValueError("损坏岗位不能恢复，请核对来源后重新导入")
            active = int(action == "restore")
            if old["active"] != active:
                conn.execute(
                    "UPDATE career_positions SET active=?,revision=revision+1,updated_at=? WHERE position_id=?",
                    (active, _now_iso(), identifier),
                )
                self.event(identifier, action)
        return self.get(identifier)

    def comparison(self, identifier: str) -> dict[str, Any]:
        with self.storage._write_lock:
            row = self.usable(identifier)
            return self._comparison(identifier, row["position"], row["revision"])

    def _comparison(
        self, identifier: str, position: dict[str, Any], revision: int
    ) -> dict[str, Any]:
        result = compare(self.storage, identifier, position, revision)
        completed = [
            t
            for t in self.trainings(identifier)
            if t["kind"] == "written" and not t["data_error"] and t["payload"].get("result")
        ]
        result["written"] = [
            {"training_id": t["training_id"], **t["payload"]["result"]} for t in completed
        ]
        result["mapping_method"] += (
            "基础题取本岗位最近100份训练中的已完成记录，同题跨轮作答可重复计数。"
        )
        for skill in result["skills"]:
            questions = [
                (q, t["payload"]["result"]["answers"][q["id"]])
                for t in completed
                for q in t["payload"]["questions"]
                if q["skill"] == skill["label"]
            ]
            skill["written_count"] = len(questions)
            skill["written_correct_count"] = sum(answer == q["correct"] for q, answer in questions)
            if questions:
                skill["status"] = "有训练记录"
                skill["notes"].append(
                    f"基础题已作答{len(questions)}次，答对{skill['written_correct_count']}次；允许跨轮重复题目。"
                )
                skill["notes"] = [
                    note for note in skill["notes"] if not note.startswith("尚无相关作答证据")
                ]
        return result

    def training(self, identifier: str) -> dict[str, Any]:
        row = (
            self.storage._conn()
            .execute(
                "SELECT t.*,a.content FROM career_trainings t JOIN artifacts a ON a.artifact_id=t.artifact_id WHERE t.training_id=?",
                (identifier,),
            )
            .fetchone()
        )
        if not row:
            raise KeyError(identifier)
        result = dict(row)
        result.pop("request_key", None)
        try:
            payload = json.loads(result.pop("content"))
            if not isinstance(payload, dict) or payload.get("version") != "2.5":
                raise ValueError("training format")
            Position.model_validate(payload["position"])
            if (
                type(payload.get("position_revision")) is not int
                or payload["position_revision"] < 1
            ):
                raise ValueError("revision format")
            if result["kind"] == "written":
                if payload.get("questions") != basic_questions(payload["position"]) or payload.get(
                    "problems"
                ) != recommended_problems(payload["position"]):
                    raise ValueError("written format")
                for q in payload["questions"]:
                    if not isinstance(q, dict) or not 0 <= q["correct"] < len(q["options"]):
                        raise ValueError("question format")
                if payload.get("result") is None:
                    payload["questions"] = [
                        {k: v for k, v in q.items() if k not in {"correct", "explanation"}}
                        for q in payload["questions"]
                    ]
                else:
                    answers, outcome = payload["result"]["answers"], payload["result"]
                    if (
                        outcome.get("source") != "platform_authored_basic_quiz"
                        or not isinstance(outcome.get("submitted_at"), str)
                        or datetime.fromisoformat(outcome["submitted_at"]).tzinfo is None
                        or type(outcome.get("total")) is not int
                        or type(outcome.get("correct")) is not int
                    ):
                        raise ValueError("result metadata")
                    if set(answers) != {q["id"] for q in payload["questions"]}:
                        raise ValueError("answer format")
                    if any(
                        type(answers[q["id"]]) is not int
                        or not 0 <= answers[q["id"]] < len(q["options"])
                        for q in payload["questions"]
                    ):
                        raise ValueError("answer range")
                    correct = sum(answers[q["id"]] == q["correct"] for q in payload["questions"])
                    total = len(payload["questions"])
                    if (
                        not total
                        or outcome["total"] != total
                        or outcome["correct"] != correct
                        or outcome["correct_rate"] != correct / total
                    ):
                        raise ValueError("result format")
            elif result["kind"] == "review":
                snapshot = payload["comparison"]
                if (
                    snapshot["position_id"] != result["position_id"]
                    or snapshot["position_revision"] != payload["position_revision"]
                    or not isinstance(snapshot["interviews"], list)
                    or not isinstance(snapshot["written"], list)
                    or not isinstance(snapshot["mapping_method"], str)
                    or not isinstance(snapshot["purpose"], str)
                    or not isinstance(snapshot["skills"], list)
                    or len(snapshot["skills"]) != len(payload["position"]["requirements"])
                ):
                    raise ValueError("review format")
                for skill, requirement in zip(
                    snapshot["skills"], payload["position"]["requirements"], strict=True
                ):
                    if (
                        not isinstance(skill, dict)
                        or any(skill.get(k) != v for k, v in requirement.items())
                        or any(
                            type(skill[key]) is not int or skill[key] < 0
                            for key in (
                                "coding_count",
                                "coding_ac_count",
                                "written_count",
                                "written_correct_count",
                            )
                        )
                    ):
                        raise ValueError("review skill format")
            result.update(payload=payload, data_error=False)
        except (ValueError, TypeError, KeyError):
            result.update(payload=None, data_error=True)
        return result

    def trainings(self, identifier: str) -> list[dict[str, Any]]:
        self.get(identifier)
        return [
            self.training(row[0])
            for row in self.storage._conn().execute(
                "SELECT training_id FROM career_trainings WHERE position_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100",
                (identifier,),
            )
        ]

    def start(
        self,
        identifier: str,
        kind: Literal["written", "interview", "review"],
        key: str,
        revision: int,
    ) -> dict[str, Any]:
        if kind not in {"written", "interview", "review"}:
            raise ValueError("无效训练类型")
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            prior = conn.execute(
                "SELECT * FROM career_trainings WHERE request_key=?", (key,)
            ).fetchone()
            if prior:
                record = self.training(prior["training_id"])
                if (
                    prior["position_id"] != identifier
                    or prior["kind"] != kind
                    or record["data_error"]
                    or record["payload"]["position_revision"] != revision
                ):
                    raise ValueError("训练键已用于其他记录或内容异常")
                return record
            position = self.usable(identifier, revision)["position"]
            tid, aid = uuid.uuid4().hex, uuid.uuid4().hex
            payload = {"version": "2.5", "position": position, "position_revision": revision}
            interview_id = None
            if kind == "written":
                payload.update(
                    questions=basic_questions(position),
                    problems=recommended_problems(position),
                    result=None,
                )
                if not payload["questions"] and not payload["problems"]:
                    raise ValueError("暂没有与该岗位要求关联的原创训练题；可先导入资料或创建面试")
            elif kind == "review":
                payload["comparison"] = self._comparison(identifier, position, revision)
            else:
                run = self.storage.create_agent_run(
                    task_type="career_interview",
                    goal="针对岗位快照开展口头训练",
                    selected_agents=["面试 Agent"],
                    context_refs={
                        "allow_external_analysis": False,
                        "career_position_id": identifier,
                        "career_training_id": tid,
                        "position_revision": revision,
                    },
                    commit=False,
                )
                interview = self.storage.create_interview(
                    target_role=f"{position['company']} · {position['title']}"[:120],
                    scenario="求职面试",
                    difficulty="标准",
                    questions=interview_questions(position),
                    agent_run_id=run["run_id"],
                    commit=False,
                )
                interview_id = interview["interview_id"]
                conn.execute(
                    "INSERT INTO agent_steps(step_id,run_id,sequence,agent_name,input_refs,output_summary) "
                    "VALUES(?,?,1,'面试 Agent',?,?)",
                    (
                        uuid.uuid4().hex,
                        run["run_id"],
                        json.dumps({"position_id": identifier, "interview_id": interview_id}),
                        "依据确认的岗位快照创建5道原创口头训练问题",
                    ),
                )
            conn.execute(
                "INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) VALUES(?,?,?,?,?)",
                (
                    aid,
                    "career_training",
                    f"{position['company']}岗位训练",
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps({"position_id": identifier, "training_id": tid}),
                ),
            )
            conn.execute(
                "INSERT INTO career_trainings(training_id,position_id,request_key,kind,artifact_id,interview_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (tid, identifier, key, kind, aid, interview_id, _now_iso()),
            )
            self.event(identifier, "training_created", tid, {"kind": kind})
        return self.training(tid)

    def answer_written(self, identifier: str, answers: dict[str, int]) -> dict[str, Any]:
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            row = self.training(identifier)
            if row["data_error"] or row["kind"] != "written":
                raise ValueError("训练数据异常或不是基础笔试，原记录保留")
            raw = conn.execute(
                "SELECT content FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)
            ).fetchone()[0]
            payload = json.loads(raw)
            questions = payload["questions"]
            if set(answers) != {q["id"] for q in questions} or not questions:
                raise ValueError("请完整回答本轮全部基础题")
            for q in questions:
                if type(answers[q["id"]]) is not int or not 0 <= answers[q["id"]] < len(
                    q["options"]
                ):
                    raise ValueError("作答选项超出范围")
            if payload["result"] is not None:
                if payload["result"]["answers"] != answers:
                    raise ValueError("本轮已经提交，重新练习请创建新一轮")
                return row
            correct = sum(answers[q["id"]] == q["correct"] for q in questions)
            payload["result"] = {
                "answers": answers,
                "correct": correct,
                "total": len(questions),
                "correct_rate": correct / len(questions),
                "submitted_at": _now_iso(),
                "source": "platform_authored_basic_quiz",
            }
            conn.execute(
                "UPDATE artifacts SET content=?,updated_at=? WHERE artifact_id=?",
                (json.dumps(payload, ensure_ascii=False), _now_iso(), row["artifact_id"]),
            )
            self.event(
                row["position_id"],
                "written_submitted",
                identifier,
                {"correct": correct, "total": len(questions)},
            )
        return self.training(identifier)

    def preview_delete(self, identifier: str) -> dict[str, Any]:
        from .planning import CareerPlans

        row = self.get(identifier)
        trainings = [
            list(t)
            for t in self.storage._conn().execute(
                "SELECT t.training_id,t.interview_id,a.content FROM career_trainings t JOIN artifacts a "
                "ON a.artifact_id=t.artifact_id WHERE t.position_id=? ORDER BY t.training_id",
                (identifier,),
            )
        ]
        plans = CareerPlans(self).raw(identifier)
        return {
            "training_count": len(trainings),
            "learning_plan_count": len(plans),
            "confirmation_token": digest([row, trainings, plans]),
            "scope": "本岗位、求职训练、对比快照及本岗位生成的学习计划和进度；保留原资料、图谱、编程提交、面试及其他学习计划。",
        }

    def delete(self, identifier: str, token: str) -> dict[str, bool]:
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            if not conn.execute(
                "SELECT 1 FROM career_positions WHERE position_id=?", (identifier,)
            ).fetchone():
                return {"deleted": True}
            preview = self.preview_delete(identifier)
            if token != preview["confirmation_token"]:
                raise ValueError("岗位或训练已更新，请重新预览删除影响")
            from .planning import CareerPlans

            for plan in CareerPlans(self).raw(identifier):
                conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (plan["artifact_id"],))
            conn.execute(
                "DELETE FROM artifacts WHERE artifact_id IN (SELECT artifact_id FROM career_trainings WHERE position_id=?)",
                (identifier,),
            )
            conn.execute("DELETE FROM career_positions WHERE position_id=?", (identifier,))
            conn.execute("DELETE FROM career_events WHERE position_id=?", (identifier,))
            self.event(None, "position_deleted", detail={"trainings": preview["training_count"],
                                                       "learning_plans": preview["learning_plan_count"]})
        return {"deleted": True}

    def plan_preview(self, identifier: str) -> dict[str, Any]:
        from .planning import CareerPlans

        return CareerPlans(self).preview(identifier)

    def save_plan(self, identifier: str, revision: str) -> dict[str, Any]:
        from .planning import CareerPlans

        return CareerPlans(self).save(identifier, revision)

    def plans(self, identifier: str) -> list[dict[str, Any]]:
        from .planning import CareerPlans

        return CareerPlans(self).list(identifier)

    def transition_plan(self, identifier: str, plan_id: str, action: str) -> dict[str, Any]:
        from .planning import CareerPlans

        return CareerPlans(self).transition(identifier, plan_id, action)

    def events(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.storage._conn().execute(
                "SELECT * FROM career_events ORDER BY event_id DESC LIMIT 100"
            )
        ]

    def overview(self) -> dict[str, Any]:
        """汇总保存的求职证据，不把训练完成量换算为能力分数。"""
        with self.storage._write_lock:
            conn = self.storage._conn()
            counts = {
                "positions": 0,
                "active_positions": 0,
                "trainings": 0,
                "completed_written": 0,
                "written_answers": 0,
                "written_correct": 0,
                "interviews": 0,
                "interview_answers": 0,
                "assessed_answers": 0,
                "review_snapshots": 0,
                "excluded_records": 0,
            }
            valid_positions: set[str] = set()
            updated: list[str] = []
            for row in conn.execute("SELECT position_id FROM career_positions"):
                position = self.get(row[0])
                if position["data_error"]:
                    counts["excluded_records"] += 1
                    continue
                counts["positions"] += 1
                counts["active_positions"] += int(bool(position["active"]))
                valid_positions.add(row[0])
                updated.append(position["updated_at"])
            recent = []
            seen_interviews: set[str] = set()
            for record in conn.execute(
                "SELECT training_id FROM career_trainings ORDER BY created_at DESC,rowid DESC"
            ):
                training = self.training(record[0])
                if training["data_error"] or training["position_id"] not in valid_positions:
                    counts["excluded_records"] += 1
                    continue
                counts["trainings"] += 1
                payload = training["payload"]
                updated.append(training["created_at"])
                if len(recent) < 5:
                    recent.append(
                        {
                            "training_id": training["training_id"],
                            "position_id": training["position_id"],
                            "kind": training["kind"],
                            "company": payload["position"]["company"],
                            "title": payload["position"]["title"],
                            "created_at": training["created_at"],
                        }
                    )
                if training["kind"] == "written" and payload.get("result"):
                    result = payload["result"]
                    counts["completed_written"] += 1
                    counts["written_answers"] += result["total"]
                    counts["written_correct"] += result["correct"]
                    updated.append(result["submitted_at"])
                elif training["kind"] == "review":
                    counts["review_snapshots"] += 1
                elif training["interview_id"] and training["interview_id"] not in seen_interviews:
                    session = self.storage.get_interview(training["interview_id"])
                    if session:
                        seen_interviews.add(training["interview_id"])
                        counts["interviews"] += 1
                        counts["interview_answers"] += len(session["turns"])
                        counts["assessed_answers"] += session["assessed_turn_count"]
                        updated.append(session["updated_at"])
            return {
                "version": "2.5",
                "counts": counts,
                "recent": recent,
                "updated_at": max(updated) if updated else None,
                "method": "汇总当前保存且有效的求职记录，包含已撤销岗位的历史训练。基础题可跨轮重复；完成量不代表能力或录用结果。删除求职岗位后该训练不再计入此处，保留的面试仍见原面试统计。",
            }
