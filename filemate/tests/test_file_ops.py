"""文件操作测试。TODO(徐书和 + 胡希)"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from filemate.execution.file_ops import FileOps, OpResult


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
        assert src.exists()  # 源文件仍在
        assert dst.exists()

    def test_copy_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.copy(tmp / "missing.txt", tmp / "dst.txt")
        assert not res.success
        assert "不存在" in res.error


class TestDelete:
    def test_delete_basic(self, ops: FileOps, tmp: Path) -> None:
        p = tmp / "remove_me.txt"
        p.write_text("x")
        res = ops.delete(p)
        assert res.success
        assert not p.exists()

    def test_delete_missing(self, ops: FileOps, tmp: Path) -> None:
        res = ops.delete(tmp / "gone.txt")
        assert not res.success


class TestIsSupported:
    def test_supported(self, ops: FileOps) -> None:
        assert ops.is_supported("a.docx")
        assert ops.is_supported("b.pdf")
        assert ops.is_supported("c.pptx")

    def test_unsupported(self, ops: FileOps) -> None:
        assert not ops.is_supported("a.zip")
        assert not ops.is_supported("b.mp4")
