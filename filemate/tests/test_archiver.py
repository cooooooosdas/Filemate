"""归档器测试。TODO(徐书和)"""
from __future__ import annotations

from pathlib import Path

import pytest

from filemate.execution.archiver import Archiver
from filemate.execution.file_ops import FileOps


@pytest.fixture()
def ops() -> FileOps:
    return FileOps()


@pytest.fixture()
def archiver(tmp_path: Path, ops: FileOps) -> Archiver:
    return Archiver(tmp_path / "archive", ops)


class TestArchiver:
    def test_archive_basic(self, archiver: Archiver, tmp_path: Path) -> None:
        """基础归档：文件移动到 课程/分类 目录下。"""
        src = tmp_path / "lecture1.pdf"
        src.write_text("课程内容")

        result = archiver.archive(
            session_id="s1",
            category="课件",
            course="操作系统",
            new_name="操作系统-课件-第一章.pdf",
            source_path=src,
        )
        assert result.success
        assert not src.exists()
        dest = tmp_path / "archive" / "操作系统" / "课件" / "操作系统-课件-第一章.pdf"
        assert dest.exists()

    def test_archive_unknown_category_falls_back(self, archiver: Archiver, tmp_path: Path) -> None:
        """非法分类应归入 待确认。"""
        src = tmp_path / "unknown.pdf"
        src.write_text("内容")

        result = archiver.archive(
            session_id="s2",
            category="不存在的分类",
            course="任意课",
            new_name="test.pdf",
            source_path=src,
        )
        assert result.success
        # 确认归档到了 待确认 目录
        assert "待确认" in result.dest_path

    def test_archive_missing_source(self, archiver: Archiver) -> None:
        result = archiver.archive(
            session_id="s3",
            category="课件",
            course="操作系统",
            new_name="x.pdf",
            source_path="/path/does/not/exist.pdf",
        )
        assert not result.success
        assert "不存在" in result.error

    def test_preview_dest(self, archiver: Archiver) -> None:
        dest = archiver.preview_dest(
            base_dir=Path("/archive"),
            category="作业",
            course="数据结构",
            new_name="数据结构-作业-图算法.pdf",
        )
        expected = Path("/archive") / "数据结构" / "作业" / "数据结构-作业-图算法.pdf"
        assert dest == expected

    def test_preview_unknown_category(self, archiver: Archiver) -> None:
        dest = archiver.preview_dest(
            base_dir=Path("/archive"),
            category="奇怪分类",
            course="课程名",
            new_name="a.pdf",
        )
        assert "待确认" in str(dest)

    def test_preview_empty_course(self, archiver: Archiver) -> None:
        dest = archiver.preview_dest(
            base_dir=Path("/archive"),
            category="课件",
            course="",
            new_name="a.pdf",
        )
        assert "未分类" in str(dest)


class TestArchiverValidCategories:
    def test_all_standard_categories_accepted(self, archiver: Archiver) -> None:
        for cat in ["课件", "作业", "竞赛通知", "考试通知", "参考资料", "大创通知", "待确认"]:
            dest = archiver.preview_dest(
                base_dir=Path("/x"), category=cat, course="课", new_name="a.pdf"
            )
            assert cat in str(dest)
