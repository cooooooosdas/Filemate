"""命名生成：根据提取信息生成规范文件名。"""

from __future__ import annotations


class Namer:
    """文件名生成器。输出格式: [课程]-[类型]-[任务]-[截止]-[状态]"""

    def generate(
        self,
        *,
        category: str,
        course: str,
        task: str,
        deadline: str,
        status: str = "待处理",
    ) -> str:
        """TODO(张金宝): 实现。"""
        raise NotImplementedError("TODO(张金宝): 命名生成")
