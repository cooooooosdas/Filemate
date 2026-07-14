"""多里程碑识别：从长通知中提取所有时间节点。"""

from __future__ import annotations


class MilestoneDetector:
    """多里程碑识别器。"""

    def detect(self, text: str) -> list[dict[str, Any]]:
        """TODO(张金宝): 实现。

        输出格式::

            [
                {"event": str, "date": "YYYY-MM-DD", "order": int},
                ...
            ]
        """
        raise NotImplementedError("TODO(张金宝): 里程碑识别")
