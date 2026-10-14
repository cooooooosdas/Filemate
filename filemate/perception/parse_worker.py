"""Private decoder entry point; never runs LLM calls or writes user databases."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """Apply limits before importing document libraries and emit bounded JSON."""
    if sys.platform == 'linux':
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (25, 26))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from filemate.perception.file_parser import FileParser

    request = json.loads(sys.stdin.buffer.read(64 * 1024))
    path = Path(request['path'])
    result = FileParser()._parse_local(path)
    if request.get('enriched') and not result.get('error'):
        result = enrich(path, result)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))


def enrich(path: Path, result: dict) -> dict:
    """Include optional OCR, tables and charts inside the same decoder budget."""
    from filemate.perception.chart_parser import ChartParser
    from filemate.perception.ocr import OCRBackend
    from filemate.perception.table_reader import TableReader

    raw = result['raw_text']
    meta = result['metadata']
    if not raw.strip() and meta.get('suffix') == 'pdf' and meta.get('text_pages', 1) == 0:
        ocr = OCRBackend()
        if ocr.available:
            raw = ocr.recognize(path)
    if meta.get('suffix') == 'pdf' and meta.get('total_pages', 0) > 50:
        meta['enrichment_incomplete'] = True
        result['note'] = '已提取正文；超过50页的PDF未做表格和图表几何提取，请按章节拆分以提取结构'
        result['raw_text'] = raw[:500_000]
        return result
    tables = TableReader().extract_tables(path)
    if tables:
        rendered = [table.to_markdown() for table in tables]
        raw += '\n\n--- 表格数据 ---\n' + '\n\n'.join(text for text in rendered if text)
        meta['tables'] = len(tables)
    charts = ChartParser().extract_charts(path)
    if charts:
        lines = []
        for chart in charts:
            if chart.title:
                lines.append(f'图表: {chart.title}')
            if chart.description:
                lines.append(f'说明: {chart.description}')
            lines.extend(el['text'] for el in chart.to_task_elements() if el.get('text'))
        raw += '\n\n--- 图表数据 ---\n' + '\n'.join(lines)
        meta['charts'] = len(charts)
    if len(raw) > 500_000:
        meta['truncated'] = True
    result['raw_text'] = raw[:500_000]
    return result


if __name__ == '__main__':
    main()
