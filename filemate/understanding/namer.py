"""命名生成：根据提取信息生成规范文件名。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 命名规范：[课程]-[类型]-[任务]-[截止]-[状态]
# 示例：[操作系统]-[作业]-[实验三]-[0415]-[待处理].docx

_VALID_CATEGORIES = {"课件", "作业", "竞赛通知", "考试通知", "参考资料", "大创通知", "待确认"}
_DEFAULT_STATUS = "待处理"
_MAX_LEN = 80  # 文件名（不含扩展名）最大长度


class Namer:
    """文件名生成器。

    接口契约::

        generate(*, category, course, task, deadline, status) -> str
        # 返回: "[课程]-[类型]-[任务]-[截止]-[状态]"（不含扩展名）
    """

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def generate(
        self,
        *,
        category: str,
        course: str,
        task: str,
        deadline: str,
        status: str = _DEFAULT_STATUS,
    ) -> str:
        """生成规范文件名。

        Parameters
        ----------
        category : str
            课件 / 作业 / 竞赛通知 / 考试通知 / 参考资料 / 大创通知 / 待确认
        course : str
            课程名（如"操作系统"）
        task : str
            任务描述（如"实验三"）
        deadline : str
            截止日期（"YYYY-MM-DD" 或 "MMDD"）
        status : str
            状态（默认"待处理"）

        Returns
        -------
        str — 不含扩展名的文件名
        """
        # 归一化
        category = category if category in _VALID_CATEGORIES else "待确认"
        course = self._clean(course) or "未分类"
        task = self._clean(task) or "未命名"
        status = self._clean(status) or _DEFAULT_STATUS

        # 格式化截止日期
        deadline_fmt = self._format_deadline(deadline)

        # 尝试用 LLM 优化（尤其是 task 字段的简洁化）
        task = self._maybe_refine_task(task, category, course)

        name = f"[{course}]-[{category}]-[{task}]-[{deadline_fmt}]-[{status}]"

        # 截断过长文件名（优先截断 course 和 task）
        if len(name) > _MAX_LEN:
            name = self._truncate(name, course, task, deadline_fmt, status, category)

        return name

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _clean(s: str) -> str:
        """移除方括号、换行、多余空格，防止文件名中出现非法字符。"""
        s = s.strip().replace("\n", " ").replace("\r", " ")
        s = re.sub(r"\[|\]", "", s)  # 用户输入的方括号去掉，避免嵌套
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def _format_deadline(raw: str) -> str:
        """YYYY-MM-DD → MMDD；已是 MMDD 或空则原样返回。"""
        raw = raw.strip()
        if not raw:
            return "待定"
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if m:
            return f"{m.group(2)}{m.group(3)}"
        if re.match(r"^\d{4}$", raw):
            return raw
        return raw.replace("-", "")[:6] or "待定"

    def _maybe_refine_task(self, task: str, category: str, course: str) -> str:
        """如果 task 过长（> 20 字），尝试用 LLM 精简。"""
        if len(task) <= 20:
            return task
        try:
            prompt = (
                "请把以下任务描述精简到 15 字以内，只返回精简后的文本，不要额外解释。\n"
                f"课程：{course}\n类别：{category}\n任务：{task}"
            )
            refined = self.llm.call(prompt=prompt, max_tokens=32, temperature=0.0).strip()
            refined = self._clean(refined)
            if 2 <= len(refined) <= 20:
                return refined
        except Exception as exc:
            logger.debug("LLM 精简任务名失败: %s", exc)
        # 失败则硬截断
        return task[:20]

    @staticmethod
    def _truncate(name: str, course: str, task: str, deadline: str, status: str, category: str) -> str:
        """超长时优先缩短 course 和 task。"""
        # 骨架不变，缩 course 和 task
        course_short = course[:10]
        task_short = task[:10]
        candidate = f"[{course_short}]-[{category}]-[{task_short}]-[{deadline}]-[{status}]"
        if len(candidate) > _MAX_LEN:
            candidate = f"[{course_short[:6]}]-[{category}]-[{task_short[:6]}]-[{deadline}]-[{status}]"
        return candidate
