"""独立能力目标、前置条件与实际训练证据的技能树。"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from filemate.execution.storage import SQLiteStorage, _now_iso
from filemate.study.knowledge_graph import _after_question_revision, mastery_metrics
from filemate.study.question_validation import validate_question

TREE_ID = "personal-skill-tree-v1"


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["quiz", "coding", "interview"]
    target_id: str = Field(min_length=1, max_length=80)
    question_index: int | None = Field(default=None, ge=0, le=100000)
    required_successes: int = Field(default=1, ge=1, le=20)


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    skill_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    prerequisites: list[str] = Field(default_factory=list, max_length=200)
    criteria: list[Criterion] = Field(default_factory=list, max_length=20)


class SkillTree(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    skills: list[Skill] = Field(default_factory=list, max_length=200)


class SkillTreeRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def read(self) -> SkillTree:
        """读取个人配置；损坏时明确拒绝，不覆盖历史数据。"""
        artifact = self.storage.get_artifact(TREE_ID)
        if artifact is None:
            return SkillTree()
        if artifact["artifact_type"] != "skill_tree":
            raise ValueError("技能树记录类型异常，原数据保留")
        tree = SkillTree.model_validate(artifact["content"])
        self._validate_links(tree)
        return tree

    @staticmethod
    def _validate_links(tree: SkillTree) -> None:
        ids = [skill.skill_id for skill in tree.skills]
        if len(set(ids)) != len(ids):
            raise ValueError("技能标识重复")
        by_id = {skill.skill_id: skill for skill in tree.skills}
        resolved: set[str] = set()
        pending = set(ids)
        for skill in tree.skills:
            if len(set(skill.prerequisites)) != len(skill.prerequisites) or any(key not in by_id for key in skill.prerequisites):
                raise ValueError("前置技能不存在或重复")
            keys = [(c.kind, c.target_id, c.question_index) for c in skill.criteria]
            if len(set(keys)) != len(keys):
                raise ValueError("同一技能内不能重复关联相同验收记录")
        while pending:
            ready = {key for key in pending if set(by_id[key].prerequisites) <= resolved}
            if not ready:
                raise ValueError("前置技能包含循环或自引用")
            pending -= ready
            resolved |= ready

    def _criterion(self, criterion: Criterion, *, require_target: bool) -> dict[str, Any]:
        """只统计可回读的实际记录，删除或修订证据后重新计算。"""
        count = 0
        records: list[dict[str, str]] = []
        available = True
        if criterion.kind != "quiz" and criterion.question_index is not None:
            raise ValueError("非课程练习不使用题目序号")
        if criterion.kind == "coding" and criterion.required_successes != 1:
            raise ValueError("单个编程提交以一次有效AC验收，多次练习请关联不同提交")
        if criterion.kind == "quiz":
            artifact = self.storage.get_artifact(criterion.target_id)
            questions = artifact.get("content") if artifact else None
            index = criterion.question_index
            available = bool(artifact and artifact["artifact_type"] == "questions" and isinstance(questions, list)
                             and index is not None and index < len(questions))
            if available:
                try:
                    validate_question(questions[index], legacy=True)
                except (ValueError, TypeError):
                    available = False
            if available:
                rows = self.storage._conn().execute(
                    "SELECT rowid AS evidence_sequence,* FROM quiz_attempts WHERE artifact_id=? AND question_index=? ORDER BY created_at DESC,rowid DESC",
                    (criterion.target_id, index),
                ).fetchall()
                for row in rows:
                    if row["is_correct"] == 1 and row["score"] == 1 and _after_question_revision(dict(row), artifact) and mastery_metrics([dict(row)])["sample_count"] == 1:
                        count += 1
                        if len(records) < 5:
                            records.append({"record_id": row["attempt_id"], "href": "/ai-tools?artifact=" + criterion.target_id})
        elif criterion.kind == "coding":
            from filemate.programming.repository import CodingRepository

            try:
                submission = CodingRepository(self.storage).get(criterion.target_id)
            except KeyError:
                available = False
            else:
                available = not submission["data_error"] and bool(submission["active"])
                if available and submission["status"] == "completed" and submission["result"].get("verdict") == "AC":
                    count = 1
                    records = [{"record_id": criterion.target_id, "href": "/programming?submission=" + criterion.target_id}]
        else:
            interview = self.storage.get_interview(criterion.target_id)
            available = interview is not None
            if interview:
                count = sum(bool(str(turn.get("answer", "")).strip()) for turn in interview.get("turns", []))
                records = [{"record_id": criterion.target_id, "href": "/interview?interview=" + criterion.target_id}] if count else []
        if require_target and not available:
            raise ValueError("验收证据不存在、已撤销或不可用，请在当前学习空间重新选择")
        return {**criterion.model_dump(), "available": available, "observed_successes": count,
                "met": available and count >= criterion.required_successes, "records": records}

    def save(self, tree: SkillTree) -> dict[str, Any]:
        """验证前置图与权限，用修订号避免静默覆盖另一窗口的修改。"""
        self._validate_links(tree)
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self.read()
            if current.revision != tree.revision:
                raise ValueError("技能树已更新，请刷新后再保存")
            previous = {skill.skill_id: [c.model_dump() for c in skill.criteria] for skill in current.skills}
            for skill in tree.skills:
                for criterion in skill.criteria:
                    self._criterion(criterion, require_target=criterion.model_dump() not in previous.get(skill.skill_id, []))
            saved = tree.model_copy(update={"revision": tree.revision + 1}).model_dump()
            if current.revision:
                conn.execute("UPDATE artifacts SET content=?,updated_at=? WHERE artifact_id=?",
                             (json.dumps(saved, ensure_ascii=False), _now_iso(), TREE_ID))
            else:
                conn.execute("INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) VALUES(?, 'skill_tree', '我的技能树', ?, ?)",
                             (TREE_ID, json.dumps(saved, ensure_ascii=False), '{"schema_version":1,"origin":"skill_tree"}'))
        return self.view()

    def view(self) -> dict[str, Any]:
        """目标完成状态来自验收条件，不等同于能力掌握度认证。"""
        tree = self.read()
        evidence = {skill.skill_id: [self._criterion(c, require_target=False) for c in skill.criteria] for skill in tree.skills}
        own_met = {skill.skill_id: bool(evidence[skill.skill_id]) and all(c["met"] for c in evidence[skill.skill_id]) for skill in tree.skills}
        satisfied: set[str] = set()
        for _ in tree.skills:
            before = len(satisfied)
            for skill in tree.skills:
                if own_met[skill.skill_id] and set(skill.prerequisites) <= satisfied:
                    satisfied.add(skill.skill_id)
            if len(satisfied) == before:
                break
        return {**tree.model_dump(), "evidence": evidence,
                "states": {skill.skill_id: "conditions_met" if skill.skill_id in satisfied else
                           "prerequisites_pending" if own_met[skill.skill_id] else
                           "pending_assessment" if not skill.criteria else "in_progress" for skill in tree.skills},
                "rule": "这是自定义能力目标的验收状态；正确作答、编译器AC或面试回答次数均可回读，不是专业能力评分。"}
