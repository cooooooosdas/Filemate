"""记录有界的主机资源证据，不读取用户内容、进程参数或环境变量。"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROC = Path('/proc')
OUTPUT = Path('/var/log/filemate-resources')
MAX_BYTES = 4 * 1024 * 1024


def process_stat(raw: str) -> dict[str, Any]:
    """解析含空格和括号的进程名。"""
    left, right = raw.index('('), raw.rindex(')')
    fields = raw[right + 2:].split()
    return {
        'pid': int(raw[:left]), 'name': raw[left + 1:right][:80],
        'state': fields[0], 'ppid': int(fields[1]),
        'ticks': int(fields[11]) + int(fields[12]),
        'threads': int(fields[17]), 'start': int(fields[19]),
        'rss_bytes': max(0, int(fields[21])) * os.sysconf('SC_PAGE_SIZE'),
    }


def snapshot(previous: dict[tuple[int, int], int], elapsed: float) -> tuple[dict, dict]:
    """只采集系统计数和有界的进程资源排行。"""
    processes, current = [], {}
    hz = os.sysconf('SC_CLK_TCK')
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            item = process_stat((entry / 'stat').read_text())
            key = (item['pid'], item['start'])
            current[key] = item['ticks']
            item['cpu_percent'] = None if key not in previous else round(
                100 * max(0, item['ticks'] - previous.get(key, item['ticks']))
                / hz / max(elapsed, 0.001), 2,
            )
            processes.append(item)
        except (OSError, ValueError, IndexError):
            continue
    memory = {}
    for line in (PROC / 'meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree', 'Dirty', 'Slab', 'SUnreclaim'}:
            memory[key] = int(value.split()[0]) * 1024
    counters = {}
    for line in (PROC / 'vmstat').read_text().splitlines():
        key, value = line.split()
        if key.startswith(('pgscan_', 'pgsteal_', 'allocstall', 'pswp')) or key == 'oom_kill':
            counters[key] = int(value)
    cpus = [(p['pid'], p['start']) for p in sorted(processes, key=lambda p: p['cpu_percent'] or 0, reverse=True)[:15]]
    resident = [(p['pid'], p['start']) for p in sorted(processes, key=lambda p: p['rss_bytes'], reverse=True)[:15]]
    selected = set(cpus + resident)
    sample = {
        'at': datetime.now(timezone.utc).isoformat(),
        'boot': (PROC / 'sys/kernel/random/boot_id').read_text().strip(),
        'uptime': float((PROC / 'uptime').read_text().split()[0]),
        'load': (PROC / 'loadavg').read_text().strip(),
        'cpu': (PROC / 'stat').read_text().splitlines()[0],
        'memory': memory, 'vmstat': counters,
        'processes': [p for p in processes if (p['pid'], p['start']) in selected],
    }
    return sample, current


def append(sample: dict, directory: Path = OUTPUT) -> None:
    """仅保留当前及两份轮转日志，每份最多约四 MiB。"""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / 'resources.jsonl'
    if target.exists() and target.stat().st_size >= MAX_BYTES:
        older = directory / 'resources.jsonl.1'
        if older.exists():
            older.replace(directory / 'resources.jsonl.2')
        target.replace(older)
    with target.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(sample, ensure_ascii=True, separators=(',', ':')) + '\n')


def main() -> None:
    """按固定间隔记录，异常不会重启业务服务。"""
    os.umask(0o077)
    previous, last = {}, time.monotonic()
    while True:
        started = time.monotonic()
        try:
            sample, previous = snapshot(previous, started - last)
            append(sample)
        except (OSError, ValueError) as exc:
            print(f'resource sample unavailable ({type(exc).__name__})', file=sys.stderr, flush=True)
        last = started
        time.sleep(max(1, 15 - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
