"""Regression coverage for document resource exhaustion and event-loop starvation."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from contextvars import ContextVar
from pathlib import Path

import pytest

from filemate.perception import FileParser
from filemate.perception import bounded_parse as boundary
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_real_office_and_pdf_enrichment(tmp_path: Path) -> None:
    from docx import Document
    from reportlab.pdfgen.canvas import Canvas

    doc = Document()
    doc.add_paragraph('Synthetic lecture: stacks are last-in first-out.')
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'Stack'
    table.cell(0, 1).text = 'LIFO'
    path = tmp_path / 'lecture.docx'
    doc.save(path)
    result = FileParser().parse_enriched(path)
    assert not result.get('error'), result.get('error')
    assert 'LIFO' in result['raw_text'] and result['metadata']['tables'] == 1
    path = tmp_path / 'lecture.pdf'
    canvas = Canvas(str(path))
    for index in range(30):
        canvas.drawString(40, 700, f'Synthetic page {index}: stack lecture')
        canvas.showPage()
    canvas.save()
    result = FileParser().parse_enriched(path)
    assert not result.get('error'), result.get('error')
    assert result['metadata']['text_pages'] == 30


def test_long_pdf_preserves_text_and_marks_optional_structure_limit(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / 'long.pdf'
    canvas = Canvas(str(path))
    for _ in range(51):
        canvas.drawString(40, 700, 'Synthetic lecture')
        canvas.showPage()
    canvas.save()
    result = FileParser().parse_enriched(path)
    assert not result.get('error')
    assert result['metadata']['text_pages'] == 51
    assert result['metadata']['enrichment_incomplete'] is True
    assert result['note']


def test_large_page_count_rejected_before_ai(tmp_path: Path) -> None:
    from PyPDF2 import PdfWriter

    path = tmp_path / 'oversized.pdf'
    writer = PdfWriter()
    for _ in range(501):
        writer.add_blank_page(width=100, height=100)
    with path.open('wb') as output:
        writer.write(output)
    result = FileParser().parse_enriched(path)
    assert '500' in result['error'] and not result['raw_text']


@pytest.mark.parametrize('reason', ['timeout', 'memory'])
def test_worker_is_killed_reaped_and_slot_reusable(tmp_path, monkeypatch, reason):
    original = subprocess.Popen
    processes = []
    monkeypatch.setenv('LLM_API_KEY', 'private-test-credential')

    def launch(command, **kwargs):
        assert not any('lecture' in arg for arg in command)
        assert 'LLM_API_KEY' not in kwargs['env']
        body = 'import sys,time;sys.stdin.buffer.read();time.sleep(60)'
        process = original([sys.executable, '-c', body], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(boundary.subprocess, 'Popen', launch)
    monkeypatch.setattr(boundary, 'WALL_SECONDS', 0.15 if reason == 'timeout' else 5)
    if reason == 'memory':
        monkeypatch.setattr(boundary, 'MEMORY_BYTES', 1024)
    path = tmp_path / 'lecture.pdf'
    path.write_bytes(b'bad')
    start = time.monotonic()
    result = FileParser().parse(path)
    assert result['error'] and time.monotonic() - start < 6
    assert processes[0].poll() is not None
    assert boundary._SLOT.acquire(blocking=False)
    boundary._SLOT.release()


def test_busy_worker_returns_without_creating_another(tmp_path):
    path = tmp_path / 'lecture.pdf'
    path.write_bytes(b'bad')
    assert boundary._SLOT.acquire(blocking=False)
    try:
        result = FileParser().parse(path)
        assert '稍后' in result['error']
    finally:
        boundary._SLOT.release()


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux worker address-space limit')
def test_compressed_pdf_expansion_cannot_kill_parent(tmp_path):
    import zlib

    from PyPDF2 import PdfWriter
    from PyPDF2.generic import DictionaryObject, EncodedStreamObject, NameObject

    path = tmp_path / 'expansion.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    page = writer.pages[0]
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject()})
    compressor = zlib.compressobj()
    blocks = [compressor.compress(b' ' * (1024 * 1024)) for _ in range(400)]
    stream = EncodedStreamObject()
    stream._data = b''.join(blocks) + compressor.flush()
    stream[NameObject('/Filter')] = NameObject('/FlateDecode')
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)
    result = FileParser().parse(path)
    assert result.get('error')
    assert os.getpid() > 0


def test_processing_stage_keeps_loop_responsive_and_request_context(tmp_path, monkeypatch):
    import main

    scope = ContextVar('synthetic_request_scope', default='missing')
    monkeypatch.setenv('LLM_API_KEY', 'sk-test')
    entered = asyncio.Event()

    def stage(session):
        assert scope.get() == 'tenant-test'
        time.sleep(0.2)
        return session

    monkeypatch.setattr(main, '_make_stages', lambda *a, **k: [stage])

    async def scenario():
        scope.set('tenant-test')
        task = asyncio.create_task(main.process_single('synthetic.txt', db_path=str(tmp_path / 'x.db')))
        await asyncio.sleep(0.05)
        assert not task.done()
        entered.set()
        await task

    asyncio.run(scenario())
    assert entered.is_set()


def test_process_timeout_does_not_block_health(server_module, monkeypatch):  # noqa: F811
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    import main

    module, _ = server_module
    original = subprocess.Popen
    monkeypatch.setattr(main, 'LLMClient', lambda config: object())
    monkeypatch.setattr(boundary, 'WALL_SECONDS', 0.8)

    def launch(command, **kwargs):
        return original([sys.executable, '-c',
                         'import sys,time;sys.stdin.buffer.read();time.sleep(60)'], **kwargs)

    monkeypatch.setattr(boundary.subprocess, 'Popen', launch)
    with TestClient(module.app) as client, ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, '/process',
                                  files={'file': ('synthetic.pdf', b'%PDF-synthetic')})
        time.sleep(0.15)
        assert not pending.done()
        start = time.monotonic()
        response = client.get('/api/health')
        assert response.status_code == 200
        assert time.monotonic() - start < 0.6
        result = pending.result(timeout=8)
    assert result.status_code == 200
    assert result.json()['success'] is False
    assert '解析超时' in result.json()['error']
    assert result.json()['data']['status'] == 'failed'
