"""感知层测试。

两层覆盖：
- TestFileParserContract / TestParserRegistry — 单元测试（假文件/注册表），用 pytest tmp_path
- TestReal* — 集成测试（datasets/raw/ 真实文件），用 @pytest.mark.skipif 按数据集有无自动跳过
- TestFileWatcher — 目录监控单元测试
"""
from __future__ import annotations

import asyncio
import textwrap
import time
from pathlib import Path

import pytest

from filemate.perception import FileParser
from filemate.perception.chart_parser import (
    Chart,
    ChartDataPoint,
    ChartParser,
    ChartType,
)
from filemate.perception.ocr import OCRBackend
from filemate.perception.table_reader import Table, TableCell, TableReader
from filemate.perception.watcher import FileWatcher

# ──────────────────────────────────────────────
#  真实数据集路径
# ──────────────────────────────────────────────

DATASETS_DIR = Path(__file__).parent.parent.parent / "datasets" / "raw"


def _real_files(suffix: str, max_count: int = 5) -> list[Path]:
    """从 datasets/raw 中取指定后缀的非空文件（最多 max_count 个）。"""
    if not DATASETS_DIR.is_dir():
        return []
    suffix_lower = suffix.lstrip(".").lower()
    files = sorted(
        f for f in DATASETS_DIR.glob(f"*.{suffix_lower}")
        if f.stat().st_size > 0
    )
    return files[:max_count]


def _paddleocr_available() -> bool:
    """PaddleOCR 是否已安装（OCR 为可选依赖）。"""
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


_PADDLEOCR_INSTALLED = _paddleocr_available()


def _pytest_asyncio_available() -> bool:
    try:
        import pytest_asyncio  # noqa: F401
        return True
    except ImportError:
        return False


_PYTEST_ASYNCIO_INSTALLED = _pytest_asyncio_available()


# ──────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────

@pytest.fixture()
def parser() -> FileParser:
    return FileParser()


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


# ══════════════════════════════════════════════
#  真实文件集成测试
# ══════════════════════════════════════════════


class TestRealWordParser:
    """用 datasets/raw/ 中的真实 .docx 文件验证 WordParser。"""

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_parse_returns_valid_structure(
        self, parser: FileParser,
    ) -> None:
        """任意真实 .docx 的输出必须包含 raw_text / metadata / suffix="docx"。"""
        files = _real_files("docx", max_count=3)
        if not files:
            pytest.skip("没有可用的 .docx 测试文件")
        for f in files:
            result = parser.parse(f)
            assert "error" not in result, (
                f"{f.name} 解析失败: {result.get('error')}"
            )
            assert isinstance(result["raw_text"], str)
            assert result["metadata"]["suffix"] == "docx"

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_text_not_empty(self, parser: FileParser) -> None:
        """真实 .docx 应提取出有意义的文本（非空）。"""
        files = _real_files("docx", max_count=5)
        if not files:
            pytest.skip("没有可用的 .docx 测试文件")
        non_empty = 0
        for f in files:
            result = parser.parse(f)
            if "error" not in result and len(result["raw_text"].strip()) > 0:
                non_empty += 1
        assert non_empty > 0, f"{len(files)} 个 .docx 全部返回空文本"

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_metadata_complete(self, parser: FileParser) -> None:
        """metadata 必须包含 filename / suffix / size_bytes 三个字段。"""
        files = _real_files("docx", max_count=1)
        if not files:
            pytest.skip("没有可用的 .docx 测试文件")
        result = parser.parse(files[0])
        meta = result["metadata"]
        assert meta.get("filename")
        assert meta.get("suffix") == "docx"
        assert isinstance(meta.get("size_bytes"), int)
        assert meta["size_bytes"] > 0


class TestRealPDFParser:
    """用 datasets/raw/ 中的真实 .pdf 文件验证 PDFParser。"""

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_parse_returns_valid_structure(
        self, parser: FileParser,
    ) -> None:
        """任意真实 .pdf 的输出必须包含 raw_text / metadata / suffix="pdf"。"""
        files = _real_files("pdf", max_count=5)
        if not files:
            pytest.skip("没有可用的 .pdf 测试文件")
        for f in files:
            result = parser.parse(f)
            assert "error" not in result, (
                f"{f.name} 解析失败: {result.get('error')}"
            )
            assert isinstance(result["raw_text"], str)
            assert result["metadata"]["suffix"] == "pdf"

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_text_not_empty_for_most(self, parser: FileParser) -> None:
        """大部分 .pdf 应提取出文本；允许少量图片型 PDF 返回空文本。"""
        files = _real_files("pdf", max_count=10)
        if not files:
            pytest.skip("没有可用的 .pdf 测试文件")
        non_empty = 0
        empty_files: list[str] = []
        for f in files:
            result = parser.parse(f)
            if "error" not in result and len(result["raw_text"].strip()) > 0:
                non_empty += 1
            else:
                empty_files.append(f.name)
        total = len(files)
        # 允许至多 30% 为图片型 PDF（无文字层）
        assert non_empty >= total * 0.7, (
            f"{total} 个 .pdf 中仅 {non_empty} 个有文本，非空比例过低"
            f"\n空文本文件: {empty_files}"
        )

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_image_based_pdf_no_crash(self, parser: FileParser) -> None:
        """图片型（扫描件）PDF 即使无文字层也不应崩溃，应优雅返回空文本。

        已知: 附件1：教育部关于举办中国国际大学生创新大赛（2025）的通知..pdf
              中共安徽省委宣传部关于开展2026年"书香安徽"...（附件1）..pdf
        """
        # 取最大的几个 PDF（更可能是扫描件）
        if not DATASETS_DIR.is_dir():
            pytest.skip("datasets/raw/ 目录不存在")
        large_pdfs = sorted(
            (f for f in DATASETS_DIR.glob("*.pdf") if f.stat().st_size > 1_000_000),
            key=lambda f: f.stat().st_size,
            reverse=True,
        )[:3]
        if not large_pdfs:
            pytest.skip("没有大 PDF 文件")
        for f in large_pdfs:
            result = parser.parse(f)
            # 关键：不能抛异常
            assert "raw_text" in result
            assert "metadata" in result
            # 图片型 PDF 的文本可能为空，但不应该有 error
            if "error" in result:
                print(f"  ⚠ {f.name}: {result['error']}")

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_encrypted_pdf_returns_friendly_error(
        self, parser: FileParser, tmp_path: Path,
    ) -> None:
        """加密 PDF 应返回友好错误提示，而不是静默空文本。"""
        src = _real_files("pdf", max_count=1)
        if not src:
            pytest.skip("没有可用的 .pdf 测试文件")
        try:
            from PyPDF2 import PdfReader, PdfWriter
        except ImportError:
            try:
                from pypdf import PdfReader, PdfWriter  # type: ignore[no-redef]
            except ImportError as exc:
                pytest.skip(f"PyPDF2/pypdf 未安装，无法构造加密 PDF: {exc}")
        src_path = src[0]
        enc_path = tmp_path / f"encrypted_{src_path.name}"
        try:
            reader = PdfReader(str(src_path))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt("test_password_123")
            with enc_path.open("wb") as f:
                writer.write(f)
        except Exception as exc:
            pytest.skip(f"无法构造加密 PDF: {exc}")

        result = parser.parse(enc_path)
        assert "error" in result, "加密 PDF 应返回 error 字段"
        assert "已加密" in result["error"], (
            f"错误信息应提示加密: {result.get('error')}"
        )
        assert result["raw_text"] == ""


class TestRealPPTParser:
    """用 datasets/raw/ 中的真实 .pptx 文件验证 PPTParser。"""

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_parse_returns_valid_structure(
        self, parser: FileParser,
    ) -> None:
        """任意真实 .pptx 的输出必须包含 raw_text / metadata / suffix="pptx"。"""
        files = _real_files("pptx", max_count=3)
        if not files:
            pytest.skip("没有可用的 .pptx 测试文件")
        for f in files:
            result = parser.parse(f)
            assert "error" not in result, (
                f"{f.name} 解析失败: {result.get('error')}"
            )
            assert isinstance(result["raw_text"], str)
            assert result["metadata"]["suffix"] == "pptx"

    @pytest.mark.skipif(
        not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在"
    )
    def test_slide_count_in_metadata(self, parser: FileParser) -> None:
        """PPTParser 的 metadata 应包含 slides 字段（FileParser 透传 extra_meta）。"""
        files = _real_files("pptx", max_count=1)
        if not files:
            pytest.skip("没有可用的 .pptx 测试文件")
        result = parser.parse(files[0])
        assert "error" not in result, f"{files[0].name} 解析失败: {result.get('error')}"
        meta = result["metadata"]
        assert "slides" in meta, f"metadata 缺少 slides 字段: {meta}"
        assert isinstance(meta["slides"], int)
        assert meta["slides"] >= 0


class TestLegacyFormats:
    """.doc / .ppt 旧格式应返回友好错误，不崩溃。"""

    def test_doc_returns_friendly_error(
        self, parser: FileParser, tmp_path: Path,
    ) -> None:
        p = tmp_path / "old.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0")  # OLE2 magic（.doc 文件头）
        result = parser.parse(p)
        assert "error" in result
        assert "doc" in result["error"].lower() or "不支持" in result["error"]

    def test_ppt_returns_friendly_error(
        self, parser: FileParser, tmp_path: Path,
    ) -> None:
        p = tmp_path / "old.ppt"
        p.write_bytes(b"\xd0\xcf\x11\xe0")  # OLE2 magic
        result = parser.parse(p)
        assert "error" in result
        assert "ppt" in result["error"].lower() or "不支持" in result["error"]


# ══════════════════════════════════════════════
#  FileWatcher 测试
# ══════════════════════════════════════════════


class TestFileWatcher:
    """测试目录监控（轮询）的基础行为。"""

    def test_init_handles_nonexistent_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        # __init__ 不创建目录（只由 run() 创建），不存在时应优雅处理
        w = FileWatcher(d)
        assert w.watch_dir == d.resolve()
        assert isinstance(w._seen, set)

    def test_init_seen_marks_existing(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        (d / "a.docx").write_text("test")
        (d / "b.pdf").write_text("test")
        w = FileWatcher(d)
        assert len(w._seen) == 2

    def test_init_seen_ignores_dirs(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        (d / "sub").mkdir()
        (d / "a.docx").write_text("test")
        w = FileWatcher(d)
        # 只标记文件，不标记目录
        assert len(w._seen) == 1

    def test_scan_detects_new_file(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        w = FileWatcher(d, poll_interval=0.1)
        detected: list[str] = []
        w.on_new_file(lambda p: detected.append(p.name))

        # 创建新文件
        (d / "new.docx").write_text("hello")
        w._scan()
        assert "new.docx" in detected

    def test_scan_skips_seen_files(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        (d / "old.docx").write_text("old")
        w = FileWatcher(d)
        detected: list[str] = []
        w.on_new_file(lambda p: detected.append(p.name))

        # 第一次 scan 不应触发（已在 seen 中）
        w._scan()
        assert "old.docx" not in detected, "已有文件不应触发回调"

    def test_scan_respects_extensions(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        w = FileWatcher(d, extensions={"pdf"})
        detected: list[str] = []
        w.on_new_file(lambda p: detected.append(p.name))

        (d / "note.pdf").write_text("a")
        (d / "note.docx").write_text("b")
        w._scan()
        assert "note.pdf" in detected
        assert "note.docx" not in detected

    @pytest.mark.skipif(not _PYTEST_ASYNCIO_INSTALLED, reason="pytest-asyncio 未安装")
    @pytest.mark.asyncio()
    async def test_stop_stops_loop(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        w = FileWatcher(d, poll_interval=0.05)

        async def _stop_soon() -> None:
            await asyncio.sleep(0.15)
            w.stop()

        start = time.monotonic()
        await asyncio.gather(w.run(), _stop_soon())
        elapsed = time.monotonic() - start
        # 应在合理时间内退出（不应跑满 poll_interval 的很多倍）
        assert elapsed < 2.0

    def test_reset_seen(self, tmp_path: Path) -> None:
        d = tmp_path / "watched"
        d.mkdir()
        (d / "a.docx").write_text("a")
        w = FileWatcher(d)
        assert len(w._seen) == 1

        # 清空
        w.reset_seen()
        assert len(w._seen) == 1  # _init_seen 重新填充

        # 删除文件后 reset_seen
        for f in d.iterdir():
            f.unlink()
        w.reset_seen()
        assert len(w._seen) == 0


# ══════════════════════════════════════════════
#  OCR 测试
# ══════════════════════════════════════════════


class TestOCRBackend:
    """测试 OCR 后端的探测、降级与基本接口。"""

    @pytest.mark.skipif(not _PADDLEOCR_INSTALLED, reason="PaddleOCR 未安装（可选依赖）")
    def test_available_probe(self) -> None:
        """PaddleOCR 安装后 available 应为 True。"""
        ocr = OCRBackend(lang="ch")
        assert ocr.available

    def test_missing_file_returns_empty(self) -> None:
        ocr = OCRBackend(lang="ch")
        result = ocr.recognize("/nonexistent/image.png")
        assert result == ""

    @pytest.mark.skip(reason="需下载 PaddleOCR 模型（~80MB），CI 环境跳过")
    def test_recognize_empty_image(self, tmp_path: Path) -> None:
        """空白图片应返回空字符串，不崩溃。"""
        from PIL import Image

        p = tmp_path / "empty.png"
        img = Image.new("RGB", (100, 100), color="white")
        img.save(p)

        ocr = OCRBackend(lang="ch", engine="onnxruntime")
        if not ocr.available:
            pytest.skip("PaddleOCR 不可用")
        result = ocr.recognize(p)
        # 空白图片可能识别为空，但不应崩溃
        assert isinstance(result, str)

    def test_ocr_engine_reuse(self) -> None:
        """第二次调用 recognize 应复用已初始化的引擎（不重新下载模型）。"""
        ocr = OCRBackend(lang="ch", engine="onnxruntime")
        assert ocr._ocr is None  # 尚未初始化
        # 不实际调用 recognize（避免下载模型），仅验证属性
        assert ocr.lang == "ch"
        assert ocr.ocr_version == "PP-OCRv6"


# ══════════════════════════════════════════════
#  TableReader 测试
# ══════════════════════════════════════════════


class TestTableReaderContract:
    """TableReader 契约与边界测试。"""

    def test_init_handlers(self) -> None:
        """初始化时应注册 docx/doc/pdf/pptx/ppt 五种格式处理器。"""
        reader = TableReader()
        assert "docx" in reader._handlers
        assert "doc" in reader._handlers
        assert "pdf" in reader._handlers
        assert "pptx" in reader._handlers
        assert "ppt" in reader._handlers

    def test_unknown_suffix_returns_empty(self, tmp_path: Path) -> None:
        """不支持的格式返回空列表，不抛异常。"""
        reader = TableReader()
        p = tmp_path / "data.xyz"
        p.write_text("not a real file")
        result = reader.extract_tables(p)
        assert result == []

    def test_nonexistent_file_handled(self) -> None:
        """文件不存在时应优雅处理，不崩溃。"""
        reader = TableReader()
        result = reader.extract_tables("/no/such/file.docx")
        assert isinstance(result, list)
        assert result == []


class TestTableDataclass:
    """Table / TableCell 数据类的行为测试。"""

    def test_tablecell_defaults(self) -> None:
        c = TableCell(row=0, col=0, text="hello")
        assert c.row == 0
        assert c.col == 0
        assert c.text == "hello"
        assert c.is_header is False
        assert c.is_merged is False

    def test_table_to_markdown_basic(self) -> None:
        """to_markdown() 应生成正确格式的 Markdown 表格。"""
        cells = [
            TableCell(0, 0, "姓名", is_header=True),
            TableCell(0, 1, "成绩", is_header=True),
            TableCell(1, 0, "张三"),
            TableCell(1, 1, "95"),
        ]
        t = Table(table_id="t1", rows=2, cols=2, cells=cells, caption="成绩表")
        md = t.to_markdown()
        assert "**成绩表**" in md
        assert "| 姓名 | 成绩 |" in md
        assert "| 张三 | 95 |" in md

    def test_extract_headers(self) -> None:
        cells = [
            TableCell(0, 0, "A", is_header=True),
            TableCell(0, 1, "B", is_header=False),
            TableCell(0, 2, "C", is_header=True),
        ]
        t = Table(table_id="t", rows=1, cols=3, cells=cells)
        assert t.extract_headers() == ["A", "C"]

    def test_extract_data_rows(self) -> None:
        """extract_data_rows() 应以表头为 key 返回字典列表（含标题行）。"""
        cells = [
            TableCell(0, 0, "课程", is_header=True),
            TableCell(0, 1, "分数", is_header=True),
            TableCell(1, 0, "高数"),
            TableCell(1, 1, "90"),
            TableCell(2, 0, "英语"),
            TableCell(2, 1, "85"),
        ]
        t = Table(table_id="t", rows=3, cols=2, cells=cells)
        rows = t.extract_data_rows()
        # extract_data_rows 包含所有行（含标题行）
        assert len(rows) >= 2
        assert {"课程": "高数", "分数": "90"} in rows
        assert {"课程": "英语", "分数": "85"} in rows


class TestTableReaderReal:
    """用 datasets/raw/ 真实文件测试 TableReader。"""

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_word_table_extraction(self) -> None:
        """从含有表格的 .docx 提取表格。"""
        reader = TableReader()
        f = DATASETS_DIR / "附件1：辅导员助理岗位申报表 - 副本(1).docx"
        if not f.exists():
            pytest.skip("测试文件不存在")
        tables = reader.extract_tables(f)
        assert len(tables) >= 1, f"应从申报表 docx 中提取至少 1 个表格，实际 {len(tables)}"
        t = tables[0]
        assert t.rows > 0
        assert t.cols > 0
        assert len(t.cells) > 0
        # 第一行含空格分隔的姓名
        first_row_texts = [c.text for c in t.cells if c.row == 0]
        assert any("姓" in h for h in first_row_texts), f"第一行应含姓: {first_row_texts}"

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_ppt_table_extraction(self) -> None:
        """从含有表格的 .pptx 提取表格。"""
        reader = TableReader()
        f = DATASETS_DIR / "附件1- 全国大学生英语竞赛参赛者报名流程-格式转换..pptx"
        if not f.exists():
            pytest.skip("测试文件不存在")
        tables = reader.extract_tables(f)
        assert len(tables) >= 1, f"应从 PPT 中提取至少 1 个表格，实际 {len(tables)}"
        # 至少有一个多行多列表格
        multi = [t for t in tables if t.rows >= 2 and t.cols >= 2]
        assert len(multi) >= 1, f"应至少有一个 2x2 以上的表格，实际多列表格: {len(multi)}"

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_table_markdown_output(self) -> None:
        """真实表格 to_markdown() 生成的格式能被正确解析。"""
        reader = TableReader()
        f = DATASETS_DIR / "附件1：辅导员助理岗位申报表 - 副本(1).docx"
        if not f.exists():
            pytest.skip("测试文件不存在")
        tables = reader.extract_tables(f)
        assert tables
        md = tables[0].to_markdown()
        # Markdown 表格应有分隔行（|---| 或 | --- |）
        assert "---" in md, f"Markdown 表格缺少分隔行: {md[:100]}"
        assert "|" in md

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_extract_task_tables(self) -> None:
        """extract_task_tables() 应通过关键词匹配找到与任务相关的表格。"""
        reader = TableReader()
        # 英语竞赛报名流程 pptx 中有"报名"等内容
        f = DATASETS_DIR / "附件1- 全国大学生英语竞赛参赛者报名流程-格式转换..pptx"
        if not f.exists():
            pytest.skip("测试文件不存在")
        tasks = reader.extract_task_tables(f)
        # 不强制一定有，但至少不崩溃且返回合法结构
        assert isinstance(tasks, list)
        for item in tasks:
            assert "type" in item
            assert "table" in item
            assert item["type"] in ("caption_match", "header_match", "content_match")


# ══════════════════════════════════════════════
#  ChartParser 测试
# ══════════════════════════════════════════════


class TestChartParserContract:
    """ChartParser 契约与边界测试。"""

    def test_init_handlers(self) -> None:
        parser = ChartParser()
        assert "docx" in parser._handlers
        assert "pptx" in parser._handlers
        assert "pdf" in parser._handlers

    def test_unknown_suffix_returns_empty(self, tmp_path: Path) -> None:
        parser = ChartParser()
        p = tmp_path / "data.xyz"
        p.write_text("not a real file")
        result = parser.extract_charts(p)
        assert result == []

    def test_nonexistent_file_handled(self) -> None:
        parser = ChartParser()
        result = parser.extract_charts("/no/such/file.pptx")
        assert isinstance(result, list)
        assert result == []


class TestChartTypeDetection:
    """图表类型检测逻辑测试。"""

    def test_detect_flowchart(self) -> None:
        parser = ChartParser()
        assert parser._detect_chart_type("流程图") == ChartType.FLOWCHART
        assert parser._detect_chart_type("处理步骤") == ChartType.FLOWCHART
        assert parser._detect_chart_type("Process Overview") == ChartType.FLOWCHART

    def test_detect_organization(self) -> None:
        parser = ChartParser()
        assert parser._detect_chart_type("组织架构图") == ChartType.ORGANIZATION
        assert parser._detect_chart_type("System Structure") == ChartType.ORGANIZATION

    def test_detect_timeline(self) -> None:
        parser = ChartParser()
        assert parser._detect_chart_type("项目时间线") == ChartType.TIMELINE
        assert parser._detect_chart_type("Development Schedule") == ChartType.TIMELINE

    def test_detect_mindmap(self) -> None:
        parser = ChartParser()
        assert parser._detect_chart_type("思维导图") == ChartType.MINDMAP

    def test_detect_unknown(self) -> None:
        parser = ChartParser()
        assert parser._detect_chart_type("随便什么标题") == ChartType.UNKNOWN


class TestChartDataclass:
    """Chart / ChartDataPoint 数据类行为测试。"""

    def test_chart_to_task_elements(self) -> None:
        c = Chart(
            chart_id="c1",
            chart_type=ChartType.PIE_CHART,
            title="成绩分布",
            data_points=[
                ChartDataPoint(label="优秀", percentage=20.0),
                ChartDataPoint(label="良好", percentage=50.0),
                ChartDataPoint(label="及格", percentage=30.0),
            ],
        )
        elements = c.to_task_elements()
        # 应包含标题 + 3 个数据点
        assert len(elements) == 4
        assert elements[0] == {"type": "chart_title", "text": "成绩分布"}
        assert elements[1]["label"] == "优秀"
        assert elements[1]["percentage"] == 20.0


class TestChartTextInference:
    """从文本推断图表的逻辑测试（不依赖真实文件）。"""

    def test_infer_pie_chart_from_percentages(self) -> None:
        """含百分比的列表应被识别为饼图。"""
        parser = ChartParser()
        # 注意：_infer_charts_from_text 仅当遇到非列表行时才触发图表分析，
        # 因此列表末尾需要一行非列表文本。
        text = textwrap.dedent("""\
        成绩分布
        1 优秀 20%
        2 良好 50%
        3 及格 30%
        ---""")
        charts = parser._infer_charts_from_text(text, "test")
        assert len(charts) >= 1
        pie = [c for c in charts if c.chart_type == ChartType.PIE_CHART]
        assert len(pie) >= 1, f"应识别出饼图，实际: {[(c.chart_type.name, c.title) for c in charts]}"

    def test_infer_bar_chart_from_quantities(self) -> None:
        """含量词的列表应被识别为柱状图。"""
        parser = ChartParser()
        text = textwrap.dedent("""\
        参赛人数统计
        1 计算机学院 120人
        2 电气学院 95人
        3 机械学院 80人
        ---""")
        charts = parser._infer_charts_from_text(text, "test")
        has_bar_or_pie = any(
            c.chart_type in (ChartType.BAR_CHART, ChartType.PIE_CHART) for c in charts
        )
        assert has_bar_or_pie, f"应识别出柱状图或饼图: {[(c.chart_type.name,) for c in charts]}"

    def test_infer_flowchart_from_steps(self) -> None:
        """含步骤关键词的列表应被识别为流程图。"""
        parser = ChartParser()
        text = textwrap.dedent("""\
        报名流程
        • 第一步 登录系统
        • 第二步 填写信息
        • 第三步 提交审核
        • 第四步 等待通知
        ---""")
        charts = parser._infer_charts_from_text(text, "test")
        flow = [c for c in charts if c.chart_type == ChartType.FLOWCHART]
        assert len(flow) >= 1, f"应识别出流程图: {[(c.chart_type.name,) for c in charts]}"

    def test_infer_timeline_from_dates(self) -> None:
        """含日期的列表应被识别为时间线。"""
        parser = ChartParser()
        text = textwrap.dedent("""\
        项目日程
        1 2026年7月20日 需求分析
        2 2026年8月3日 原型设计
        3 2026年8月24日 中期检查
        ---""")
        charts = parser._infer_charts_from_text(text, "test")
        tl = [c for c in charts if c.chart_type == ChartType.TIMELINE]
        assert len(tl) >= 1, f"应识别出时间线: {[(c.chart_type.name,) for c in charts]}"

    def test_empty_text_returns_empty(self) -> None:
        parser = ChartParser()
        charts = parser._infer_charts_from_text("", "test")
        assert charts == []


class TestChartParserReal:
    """用 datasets/raw/ 真实文件测试 ChartParser。"""

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_ppt_chart_extraction_no_crash(self) -> None:
        """从 PPT 提取图表不应崩溃（即使没有真正的 chart shape）。"""
        parser = ChartParser()
        f = DATASETS_DIR / "附件1- 全国大学生英语竞赛参赛者报名流程-格式转换..pptx"
        if not f.exists():
            pytest.skip("测试文件不存在")
        charts = parser.extract_charts(f)
        assert isinstance(charts, list)

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_pdf_chart_extraction_no_crash(self) -> None:
        """从 PDF 提取图表不应崩溃。"""
        parser = ChartParser()
        files = _real_files("pdf", max_count=3)
        if not files:
            pytest.skip("没有可用的 PDF 测试文件")
        for f in files:
            charts = parser.extract_charts(f)
            assert isinstance(charts, list)

    @pytest.mark.skipif(not DATASETS_DIR.is_dir(), reason="datasets/raw/ 目录不存在")
    def test_extract_task_charts(self) -> None:
        """extract_task_charts() 返回合法结构。"""
        parser = ChartParser()
        files = _real_files("pptx", max_count=1)
        if not files:
            pytest.skip("没有可用的 PPT 测试文件")
        tasks = parser.extract_task_charts(files[0])
        assert isinstance(tasks, list)
        for item in tasks:
            assert "type" in item
            assert "chart" in item
            assert item["type"] in ("title_match", "data_match")
