"""文件操作测试。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from filemate.execution.file_ops import FileOps


@pytest.fixture()
def tmp(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def ops() -> FileOps:
    return FileOps()


class TestEnsureDir:
    def test_create_new(self, ops: FileOps, tmp: Path) -> None:
        target = tmp / "a" / "b" / "c"
        result = ops.ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_existing(self, ops: FileOps, tmp: Path) -> None:
        # tmp 已被 pytest 自动创建，无需再 mkdir
        result = ops.ensure_dir(tmp)
        assert result == tmp


class TestMove:
    def test_move_basic(self, ops: FileOps, tmp: Path) -> None:
        src = tmp / "src.txt"
        src.write_text("hello")
        dst = tmp / "dst.txt"
        res = ops.move(src, dst)
        assert res.success
        assert not src.exists()
        assert dst.exists()

    def test_move_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.move(tmp / "missing.txt", tmp / "dst.txt")
        assert not res.success
        assert "不存在" in res.error

    def test_move_creates_parent(self, ops: FileOps, tmp: Path) -> None:
        src = tmp / "src.txt"
        src.write_text("x")
        dst = tmp / "deep" / "nested" / "dst.txt"
        res = ops.move(src, dst)
        assert res.success
        assert dst.exists()

    def test_move_never_overwrites_existing_target(
        self,
        ops: FileOps,
        tmp: Path,
    ) -> None:
        src = tmp / "src.txt"
        dst = tmp / "dst.txt"
        src.write_text("source")
        dst.write_text("destination")

        res = ops.move(src, dst)

        assert not res.success
        assert "目标已存在" in res.error
        assert src.read_text() == "source"
        assert dst.read_text() == "destination"


class TestRename:
    def test_rename_basic(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "old.txt"
        p.write_text("x")
        res = ops.rename(p, "new.txt")
        assert res.success
        assert (tmp / "new.txt").exists()
        assert not p.exists()

    def test_rename_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.rename(tmp / "missing.txt", "new.txt")
        assert not res.success

    def test_rename_collision(self, ops: FileOps, tmp: Path) -> None:
        (tmp / "a.txt").write_text("1")
        (tmp / "b.txt").write_text("2")
        res = ops.rename(tmp / "a.txt", "b.txt")
        assert not res.success

    def test_rename_empty_name(self, ops: FileOps, tmp: Path) -> None:
        (tmp / "x.txt").write_text("x")
        res = ops.rename(tmp / "x.txt", "")
        assert not res.success
        assert "不能为空" in res.error

    def test_rename_invalid_name(self, ops: FileOps, tmp: Path) -> None:
        (tmp / "x.txt").write_text("x")
        res = ops.rename(tmp / "x.txt", "a/b.txt")  # 含路径分隔符
        assert not res.success
        assert "无效" in res.error


class TestHash:
    def test_stable(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "file.txt"
        p.write_text("hello world")
        h1 = ops.compute_hash(p)
        h2 = ops.compute_hash(p)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_content_diff(self, ops: FileOps, tmp: Path) -> None:
        (tmp / "a.txt").write_text("hello")
        (tmp / "b.txt").write_text("world")
        assert ops.compute_hash(tmp / "a.txt") != ops.compute_hash(tmp / "b.txt")

    def test_empty(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "empty.txt"
        p.write_text("")
        h = ops.compute_hash(p)
        assert h == hashlib.sha256().hexdigest()

    def test_missing_file_raises(self, ops: FileOps, tmp: Path) -> None:
        with pytest.raises(FileNotFoundError, match="文件不存在"):
            ops.compute_hash(tmp / "does_not_exist.txt")


class TestSuffix:
    def test_docx(self, ops: FileOps) -> None:
        assert ops.suffix("a.docx") == "docx"

    def test_uppercase(self, ops: FileOps) -> None:
        assert ops.suffix("A.PDF") == "pdf"

    def test_no_ext(self, ops: FileOps) -> None:
        assert ops.suffix("README") == ""


class TestCopy:
    def test_copy_basic(self, ops: FileOps, tmp: Path) -> None:
        src = tmp / "src.txt"
        src.write_text("hello")
        dst = tmp / "sub" / "dst.txt"
        res = ops.copy(src, dst)
        assert res.success
        assert src.exists()  # 源文件保留
        assert dst.exists()

    def test_copy_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.copy(tmp / "missing.txt", tmp / "dst.txt")
        assert not res.success
        assert "不存在" in res.error

    def test_copy_creates_parent(self, ops: FileOps, tmp: Path) -> None:
        src = tmp / "src.txt"
        src.write_text("data")
        dst = tmp / "deep" / "nested" / "copy.txt"
        res = ops.copy(src, dst)
        assert res.success
        assert dst.read_text() == "data"


class TestDelete:
    def test_delete_basic(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "to_delete.txt"
        p.write_text("delete me")
        res = ops.delete(p)
        assert res.success
        assert not p.exists()

    def test_delete_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.delete(tmp / "missing.txt")
        assert not res.success
        assert "不存在" in res.error

    def test_delete_empty_file(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "empty.txt"
        p.write_text("")
        res = ops.delete(p)
        assert res.success
        assert not p.exists()

    def test_delete_then_recreate(self, ops: FileOps, tmp: Path) -> None:
        """删除后同名文件可重新创建。"""
        p = tmp / "recreate.txt"
        p.write_text("first")
        ops.delete(p)
        p.write_text("second")
        assert p.read_text() == "second"


class TestFileOpsEdgeCases:
    def test_suffix_with_multiple_dots(self, ops: FileOps) -> None:
        assert ops.suffix("report.final.docx") == "docx"

    def test_suffix_hidden_file(self, ops: FileOps) -> None:
        # .gitignore 在 Python Path.suffix 中被视为无后缀（点开头 = 隐藏文件）
        assert ops.suffix(".gitignore") == ""
        assert ops.suffix(".env") == ""

    def test_is_supported_case_insensitive(self, ops: FileOps) -> None:
        assert ops.is_supported("A.DOCX")
        assert ops.is_supported("B.PDF")
        assert ops.is_supported("C.PPTX")

    def test_hash_large_content(self, ops: FileOps, tmp: Path) -> None:
        """哈希计算对大文件也正确。"""
        p = tmp / "big.bin"
        p.write_bytes(b"\x00" * 100_000)
        h = ops.compute_hash(p)
        assert len(h) == 64
        assert ops.compute_hash(p) == h  # 相同内容相同哈希

    def test_hash_binary_file(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "binary.bin"
        p.write_bytes(bytes(range(256)))
        h = ops.compute_hash(p)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_validate_filename_rejects_traversal(self, ops: FileOps) -> None:
        with pytest.raises(ValueError, match="路径分隔符"):
            ops.validate_filename("../secret.pdf")

    def test_validate_filename_rejects_windows_reserved_name(
        self,
        ops: FileOps,
    ) -> None:
        with pytest.raises(ValueError, match="保留名称"):
            ops.validate_filename("CON.txt")

    def test_sanitize_course_segment(self, ops: FileOps) -> None:
        assert ops.sanitize_path_segment("计算机/网络", "未分类") == "计算机-网络"
        assert ops.sanitize_path_segment("..", "未分类") == "未分类"
