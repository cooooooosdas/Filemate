"""归档：根据分类结果移动文件到课程二级目录。"""

from __future__ import annotations

from pathlib import Path
from .file_ops import FileOps, OpResult


class Archiver:
    """归档器。"""

    def __init__(self, base_dir: str | Path, file_ops: FileOps) -> None:
        self.base_dir = Path(base_dir)
        self.file_ops = file_ops

    def archive(
        self,
        session_id: str,
        category: str,
        course: str,
        new_name: str,
    ) -> OpResult:
        """TODO(徐书和): 实现目录创建 + 文件移动。"""
        raise NotImplementedError("TODO(徐书和)")
