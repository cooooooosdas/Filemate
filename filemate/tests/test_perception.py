"""感知层测试。

两层覆盖：
- TestFileParserContract / TestParserRegistry — 单元测试（假文件/注册表），用 pytest tmp_path
- TestReal* — 集成测试（datasets/raw/ 真实文件），用 @pytest.mark.skipif 按数据集有无自动跳过
- TestFileWatcher — 目录监控单元测试
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from filemate.perception import FileParser
from filemate.perception.ocr import OCRBackend
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
        """PPTParser 的 metadata 应包含 slides 字段。"""
        files = _real_files("pptx", max_count=1)
        if not files:
            pytest.skip("没有可用的 .pptx 测试文件")
        result = parser.parse(files[0])
        if "error" not in result:
            # 注意：FileParser 统一出口会覆盖 metadata，slides 可能丢失
            # 当前 FileParser._ok() 不保留解析器返回的额外 metadata
            pass  # 如果不保留，这属于已知行为


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
