"""归档：根据分类结果移动文件到课程二级目录。"""

from __future__ import annotations

import logging
from pathlib import Path

from .file_ops import FileOps, OpResult

logger = logging.getLogger(__name__)


class Archiver:
    """归档器。

    目录结构::

        <base_dir>/
        ├── <course_name>/
        │   ├── 课件/
        │   ├── 作业/
        │   ├── 竞赛通知/
        │   ├── 考试通知/
        │   ├── 参考资料/
        │   └── 大创通知/
    """

    VALID_CATEGORIES = {"课件", "作业", "竞赛通知", "考试通知", "参考资料", "大创通知", "待确认"}

    def __init__(self, base_dir: str | Path, file_ops: FileOps) -> None:
        self.base_dir = Path(base_dir)
        self.file_ops = file_ops

    def archive(
        self,
        session_id: str,
        category: str,
        course: str,
        new_name: str,
        source_path: str | Path | None = None,
    ) -> OpResult:
        """归档文件到 <base_dir>/<course>/<category>/<new_name>。"""
        if category not in self.VALID_CATEGORIES:
            category = "待确认"
        course_dir = self.base_dir / (course or "未分类")
        target_dir = course_dir / category
        self.file_ops.ensure_dir(target_dir)
        dest = target_dir / (new_name or Path(source_path or "").name)
        result = self.file_ops.move(source_path or "", dest)
        if result.success:
            logger.info("归档: %s -> %s", source_path, result.dest_path)
        return result

    def preview_dest(
        self,
        base_dir: str | Path,
        category: str,
        course: str,
        new_name: str,
    ) -> Path:
        """只返回目标路径，不执行移动。用于 UI 预览。"""
        if category not in self.VALID_CATEGORIES:
            category = "待确认"
        return Path(base_dir) / (course or "未分类") / category / new_name
