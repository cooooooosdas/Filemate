"""Measure constructed synthetic graphs in isolated databases over real localhost HTTP."""

import argparse
import importlib.metadata
import json
import os
import platform
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from filemate.course_graph.repository import CourseGraphRepository
from filemate.course_graph.workspace_canvas import get_workspace_canvas
from filemate.course_graph.workspace_models import WorkspaceFilter
from filemate.course_graph.workspace_query import get_workspace, list_workspace_concepts
from filemate.execution.storage import SQLiteStorage


def prepare(output_root: Path, sizes: list[int]) -> dict[str, Any]:
    """Create new synthetic databases and refuse any pre-existing target."""
    if not output_root.is_absolute() or output_root.exists():
        raise ValueError('output-root must be a new absolute directory')
    if not sizes or len(set(sizes)) != len(sizes) or any(n < 1 or n > 10000 for n in sizes):
        raise ValueError('sizes must be distinct integers in 1..10000')
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / '.synthetic-course-workspace').touch()
    result: dict[str, Any] = {
        'synthetic': True, 'fixture_kind': 'constructed performance shape; not extraction quality',
        'measurement_note': 'first sample is first invocation, not an OS cold-cache claim; five hot samples have no P95 claim',
        'machine': {'os': platform.platform(), 'processor': platform.processor(), 'cpus': os.cpu_count(),
                    'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                    'fastapi': importlib.metadata.version('fastapi')},
        'flags': {'FILEMATE_ENABLE_COURSE_GRAPH': True, 'identity_mode': 'local, isolated per case'}, 'cases': [],
    }
    for size in sizes:
        case_root = output_root / str(size)
        case_root.mkdir()
        database = case_root / 'filemate.db'
        store = SQLiteStorage(database)
        store.init_schema()
        try:
            repo = CourseGraphRepository(store)
            cid = repo.create_course(f'合成性能构造-{size}', uuid4().hex)['course_id']
            sid = store.save_source(original_name='synthetic-original.txt', source_path='synthetic.txt', raw_text='合成引文')
            repo.attach_sources(cid, [sid], None, 0)
            revision = store.get_source_revision(sid)
            with store._conn() as conn:
                conn.executemany('INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)',
                                 [(f'n{i:05}', cid, f'概念 {i} C++' if i == size-1 else f'概念 {i}') for i in range(size)])
                conn.executemany('''INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                                 concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'合成引文',0,4)''',
                                 [(f'e{i:05}', cid, sid, revision, f'n{i:05}') for i in range(size)])
                edges = [(f'r{i:05}', cid, f'n{size-1:05}', f'n{i:05}', 'related_to') for i in range(min(size-1, 151))]
                conn.executemany('INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,?)', edges)
                conn.executemany('''INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                                 relation_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'合成引文',0,4)''',
                                 [(f're{i:05}', cid, sid, revision, row[0]) for i, row in enumerate(edges)])
                fk_errors = list(conn.execute('PRAGMA foreign_key_check'))
                total = conn.execute('SELECT count(*) FROM kg_concepts').fetchone()[0]
            result['cases'].append({'total_nodes': total, 'course_id': cid, 'database': str(database),
                                    'source_id': sid, 'focus_id': f'n{size-1:05}', 'foreign_key_errors': len(fk_errors),
                                    'browser': {'measurement_status': 'not_measured', 'first_interactive_ms': None,
                                                'max_long_task_ms': None, 'heap_bytes': None}})
        finally:
            store.close()
    return result


def samples(action: Any) -> dict[str, Any]:
    """Measure one first and five hot calls without hiding a failed call."""
    timings, sizes = [], []
    value = None
    for _ in range(6):
        start = time.perf_counter()
        value = action()
        timings.append(round((time.perf_counter() - start)*1000, 3))
        sizes.append(len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')))
    return {'first_ms': timings[0], 'hot_ms': timings[1:], 'max_hot_ms': max(timings[1:]),
            'serialized_payload_bytes': sizes, 'returned_nodes': len(value.get('nodes', [])),
            'returned_edges': len(value.get('edges', [])), 'total_concepts': value.get('total_concepts', value.get('total'))}


def measure(result: dict[str, Any], root: Path) -> None:
    """Start only owned localhost servers and stop them after each case."""
    for case in result['cases']:
        database, cid, focus = Path(case['database']), case['course_id'], case['focus_id']
        store = SQLiteStorage(database)
        try:
            case['service'] = {
                'workspace': samples(lambda store=store, cid=cid: get_workspace(store, cid)),
                'search': samples(lambda store=store, cid=cid: list_workspace_concepts(store, cid, filters=WorkspaceFilter(), q='C++')),
                'focus': samples(lambda store=store, cid=cid, focus=focus: get_workspace_canvas(store, cid, filters=WorkspaceFilter(), focus=focus)),
            }
        finally:
            store.close()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        env.update(FILEMATE_DATA_DIR=str(database.parent), FILEMATE_DB_PATH=str(database),
                   FILEMATE_ENABLE_COURSE_GRAPH='1', FILEMATE_IDENTITY_MODE='local', PYTHONUTF8='1')
        log_path = database.parent / 'http.log'
        with log_path.open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', str(port)],
                                       env=env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=20) as client:
                    deadline = time.monotonic()+30
                    while True:
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError(f'isolated server did not start; see {log_path}')
                        time.sleep(.1)
                    prefix = f'/api/knowledge-graph/courses/{cid}'
                    def request(path: str, prefix: str = prefix) -> dict:
                        response = client.get(prefix+path)
                        response.raise_for_status()
                        body = response.json()
                        if not body.get('success'):
                            raise RuntimeError('workspace request failed')
                        return body['data']
                    case['http'] = {'workspace': samples(lambda: request('/workspace')),
                                    'search': samples(lambda: request('/concepts-page?q=C%2B%2B')),
                                    'focus': samples(lambda focus=focus: request(f'/canvas?focus={focus}'))}
                    case['http_hot_gate_passed'] = all(v['max_hot_ms'] <= 2000 for v in case['http'].values())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        case['database_bytes'] = database.stat().st_size
        wal = Path(str(database)+'-wal')
        case['wal_bytes'] = wal.stat().st_size if wal.exists() else 0
        case['database_and_wal_bytes'] = case['database_bytes']+case['wal_bytes']
        (root / 'benchmark.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--sizes', type=int, nargs='+', default=[100, 1000, 10000])
    args = parser.parse_args()
    result = prepare(args.output_root, args.sizes)
    measure(result, args.output_root)
    print(json.dumps({'synthetic': True, 'report': str(args.output_root/'benchmark.json'),
                      'http_gates': [case['http_hot_gate_passed'] for case in result['cases']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
