"""感知层测试。TODO(汤新阳)"""
from __future__ import annotations

from pathlib import Path

import pytest

from filemate.perception.file_parser import FileParser


# ──────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────

@pytest.fixture()
def parser() -> FileParser:
    return FileParser()


def _fake_docx_parser():
    """构造一个假 Word 解析器模块。"""
    mod = types.ModuleType("docx")
    mod.Document = MagicMock
    return mod


# ──────────────────────────────────────────────
#  FileParser 契约
# ──────────────────────────────────────────────

class TestFileParserContract:
    """验证 FileParser.parse() 输出格式符合契约。"""

    def test_missing_file(self, parser: FileParser, tmp_path: Path) -> None:
        result = parser.parse(tmp_path / "nope.docx")
        assert "raw_text" in result
        assert "metadata" in result
        assert "error" in result
        assert result["raw_text"] == ""

    def test_not_a_file(self, parser: FileParser, tmp_path: Path) -> None:
        result = parser.parse(tmp_path)
        assert "error" in result

    def test_unsupported_suffix(self, parser: FileParser, tmp_path: Path) -> None:
        p = tmp_path / "archive.zip"
        p.write_bytes(b"PK\x03\x04")
        result = parser.parse(p)
        assert "error" in result
        assert "zip" in result["error"]

    def test_empty_file(self, parser: FileParser, tmp_path: Path) -> None:
        p = tmp_path / "empty.docx"
        p.write_bytes(b"")
        result = parser.parse(p)
        assert result["raw_text"] == ""
        assert result.get("note") == "空文件"

    def test_metadata_fields(self, parser: FileParser, tmp_path: Path) -> None:
        p = tmp_path / "doc.docx"
        p.write_bytes(b"PK\x03\x04")  # 假装是 docx
        result = parser.parse(p)
        meta = result["metadata"]
        assert "filename" in meta
        assert meta["filename"] == "doc.docx"
        assert meta["suffix"] == "docx"
        assert meta["size_bytes"] == 4

    def test_truncation(self, parser: FileParser, tmp_path: Path) -> None:
        """超过 _MAX_CHARS 的文本应被截断。"""

        class _FakeParser:
            """返回超长文本的假解析器。"""
            def parse(self, path):
                return {"raw_text": "字" * 600_000, "metadata": {"suffix": "txt"}}

        # 临时注册假解析器
        from filemate.perception import parsers as parsers_mod
        parsers_mod._REGISTRY["txt"] = _FakeParser
        try:
            p = tmp_path / "huge.txt"
            p.write_text("ignored")  # 假文件
            result = parser.parse(p)
            assert len(result["raw_text"]) <= 500_000
        finally:
            del parsers_mod._REGISTRY["txt"]


# ──────────────────────────────────────────────
#  解析器注册
# ──────────────────────────────────────────────

class TestParserRegistry:
    def test_docx_registered(self) -> None:
        from filemate.perception.parsers import get_parser
        inst = get_parser("docx")
        assert type(inst).__name__ == "WordParser"

    def test_pdf_registered(self) -> None:
        from filemate.perception.parsers import get_parser
        inst = get_parser("pdf")
        assert type(inst).__name__ == "PDFParser"

    def test_pptx_registered(self) -> None:
        from filemate.perception.parsers import get_parser
        inst = get_parser("pptx")
        assert type(inst).__name__ == "PPTParser"

    def test_unknown_raises(self) -> None:
        from filemate.perception.parsers import get_parser
        with pytest.raises(ValueError, match="不支持的格式"):
            get_parser("xyz")
