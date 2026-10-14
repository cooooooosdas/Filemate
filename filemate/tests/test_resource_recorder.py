"""主机证据的解析与隐私边界。"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'resource_recorder', Path(__file__).parents[2] / 'scripts/ops/resource_recorder.py',
)
recorder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recorder)


@pytest.fixture
def fake_proc(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, 'PROC', tmp_path)
    monkeypatch.setattr(recorder.os, 'sysconf', lambda name: 4096 if name == 'SC_PAGE_SIZE' else 100, raising=False)
    (tmp_path / 'meminfo').write_text('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n')
    (tmp_path / 'vmstat').write_text('oom_kill 0\npswpin 5\nnr_free_pages 20\n')
    (tmp_path / 'stat').write_text('cpu 1 2 3 4\n')
    (tmp_path / 'loadavg').write_text('1 2 3 1/100 42\n')
    (tmp_path / 'uptime').write_text('10.5 20\n')
    (tmp_path / 'sys/kernel/random').mkdir(parents=True)
    (tmp_path / 'sys/kernel/random/boot_id').write_text('test-boot\n')
    return tmp_path


def add_process(root, pid, ticks=125, start=9):
    entry = root / str(pid)
    entry.mkdir(exist_ok=True)
    fields = ['S', '1'] + ['0'] * 20
    fields[11], fields[12], fields[17], fields[19], fields[21] = str(ticks), '5', '3', str(start), '20'
    (entry / 'stat').write_text(f'{pid} (worker (name)) ' + ' '.join(fields))
    (entry / 'cmdline').write_text('password=DO_NOT_RECORD')
    (entry / 'environ').write_text('API_KEY=DO_NOT_RECORD')


def test_snapshot_handles_pid_reuse_and_does_not_read_secrets(fake_proc):
    add_process(fake_proc, 42)
    sample, current = recorder.snapshot({(42, 9): 30}, 2)
    assert sample['processes'][0]['cpu_percent'] == 50
    assert sample['processes'][0]['rss_bytes'] == 20 * 4096
    assert sample['processes'][0]['name'] == 'worker (name)'
    assert current == {(42, 9): 130}
    assert sample['memory']['MemAvailable'] == 1024 * 1024
    assert 'DO_NOT_RECORD' not in json.dumps(sample)
    add_process(fake_proc, 42, start=10)
    reused, _ = recorder.snapshot(current, 2)
    assert reused['processes'][0]['cpu_percent'] is None


def test_rotation_retains_only_three_files(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, 'MAX_BYTES', 1)
    for index in range(8):
        recorder.append({'sample': index}, tmp_path)
    assert len(list(tmp_path.iterdir())) == 3
    values = [json.loads(path.read_text())['sample'] for path in tmp_path.iterdir()]
    assert sorted(values) == [5, 6, 7]


@pytest.mark.skipif(os.name != 'posix', reason='实际 /proc 仅适用于 Linux')
def test_actual_linux_proc_is_readable():
    sample, current = recorder.snapshot({}, 1)
    assert current and sample['memory']['MemTotal'] > 0
