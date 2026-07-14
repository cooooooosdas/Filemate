"""实体抽取：从文本中提取课程名、截止时间等关键信息。"""

from __future__ import annotations

from typing import Any


class EntityExtractor:
    """实体抽取器。"""

    def extract(self, text: str) -> dict[str, Any]:
        """TODO(张金宝): 实现。

        输出格式::

            {
                "course_name": str | None,
                "task_description": str | None,
                "deadline": "YYYY-MM-DD" | None,
                "location": str | None,
                "extra_entities": dict,
            }
        """
        raise NotImplementedError("TODO(张金宝): 实体抽取")
