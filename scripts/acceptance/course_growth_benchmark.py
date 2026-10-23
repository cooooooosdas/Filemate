"""Measure synthetic D/E growth workloads over owned localhost HTTP, without real users."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

import httpx
import psutil

from filemate.course_graph.learning_evidence import read_learning_projection
from filemate.course_graph.question_links import question_digest
from filemate.execution.storage import SQLiteStorage
from scripts.acceptance.course_workspace_benchmark import prepare


def prepare_growth(output_root: Path, sizes: list[int], *, attempts: int = 10000) -> dict:
    """Build exact bounded workloads only in a new absolute output directory."""
    if type(attempts) is not int or not 1 <= attempts <= 100000:
        raise ValueError('attempts must be an integer in 1..100000')
    result = prepare(output_root, sizes)
    result.update(dense_attempts=attempts, fixture_kind='constructed graph plus actual-schema dense quiz records; not model quality')
    result['flags']['FILEMATE_ENABLE_GRAPH_ASSISTANT'] = True
    for case in result['cases']:
        store = SQLiteStorage(Path(case['database']))
        try:
            sid, cid, nid = case['source_id'], case['course_id'], case['focus_id']
            question = {'question_type': 'fill', 'stem': '合成引用：____', 'answer': '合成引文'}
            aid = store.save_artifact(artifact_type='questions', source_id=sid, content=[question])
            stamp = datetime.now(timezone.utc).isoformat()
            with store._conn() as conn:
                conn.execute('''INSERT INTO kg_question_links(link_id,course_id,concept_id,artifact_id,
                    source_id,question_index,question_digest,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?,?)''',
                    (uuid4().hex, cid, nid, aid, sid, question_digest(question), stamp, stamp))
                conn.executemany('''INSERT INTO quiz_attempts(attempt_id,artifact_id,source_id,question_index,
                    user_answer,is_correct,score,feedback,created_at) VALUES(?,?,?,0,?,1,1,?,?)''',
                    [(f'synthetic-attempt-{i}', aid, sid, '合成引文', '合成工程负载', stamp) for i in range(attempts)])
            case['total_attempts'] = attempts
            case['schema_version'] = store.get_schema_version()
            statements = []
            with store.read_snapshot() as read:
                read._conn().set_trace_callback(statements.append)
                projection = read_learning_projection(read, cid, now=datetime.now(timezone.utc))
            case['projection_sql_statements'] = len(statements)
            case['focus_attempt_count'] = projection['nodes'][nid]['counts']['attempts']
            assert case['focus_attempt_count'] == attempts
            assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
        finally:
            store.close()
    return result


def measure_samples(action, count=6):
    """Keep every timing and failure; six calls do not estimate a percentile."""
    records = []
    for _ in range(count):
        start = time.perf_counter()
        try:
            value = action()
            records.append({'ok': True, 'ms': round((time.perf_counter() - start) * 1000, 3),
                            'payload_bytes': len(json.dumps(value, ensure_ascii=False).encode('utf-8'))})
        except Exception as exc:  # noqa: BLE001 -- 失败样本同样记录，不剔除或伪装成成功。
            records.append({'ok': False, 'ms': round((time.perf_counter() - start) * 1000, 3),
                            'error_type': type(exc).__name__})
    return {'first': records[0], 'hot': records[1:],
            'hot_gate_passed': all(r['ok'] and r['ms'] <= 2000 for r in records[1:]) and records[0]['ok']}


def measure_growth(result: dict, root: Path) -> None:
    """Start and terminate only subprocesses owned by this benchmark."""
    for case in result['cases']:
        database = Path(case['database'])
        cid, nid = case['course_id'], case['focus_id']
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        env.update(FILEMATE_DATA_DIR=str(database.parent), FILEMATE_DB_PATH=str(database),
                   FILEMATE_ENABLE_COURSE_GRAPH='1', FILEMATE_ENABLE_GRAPH_ASSISTANT='1',
                   FILEMATE_IDENTITY_MODE='local', PYTHONUTF8='1')
        stop, rss = Event(), []
        with (database.parent / 'http.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', str(port)],
                env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            def record_memory(stop=stop, rss=rss, process=process):
                while not stop.wait(.05):
                    try:
                        parent = psutil.Process(process.pid)
                        rss.append(sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)] if p.is_running()))
                    except psutil.NoSuchProcess:
                        return
            sampler = Thread(target=record_memory, daemon=True)
            sampler.start()
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30, trust_env=False) as client:
                    deadline = time.monotonic() + 30
                    while True:
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError('owned benchmark server did not start')
                        time.sleep(.1)
                    base = f'/api/knowledge-graph/courses/{cid}'
                    def call(path, body=None, *, base=base, client=client):
                        response = client.get(base + path) if body is None else client.post(base + path, json=body)
                        response.raise_for_status()
                        return response.json()['data']
                    options = {'goal': '合成性能测试', 'concept_ids': [nid], 'days': 3, 'daily_minutes': 20}
                    case['http'] = {
                        'learning_nodes': measure_samples(partial(call, '/learning/nodes')),
                        'learning_detail': measure_samples(partial(call, f'/concepts/{nid}/learning')),
                        'path_preview': measure_samples(partial(call, '/learning/path/preview', options)),
                        'workspace': measure_samples(partial(call, '/workspace')),
                    }
                    preview = call('/learning/path/preview', options)
                    command = options | {'confirmed': True, 'confirmation_token': preview['confirmation_token'], 'request_key': uuid4().hex}
                    jobs = [partial(call, f'/concepts/{nid}/learning') for _ in range(4)] + [
                        partial(call, '/learning/path/confirm', command) for _ in range(2)]
                    with ThreadPoolExecutor(max_workers=6) as pool:
                        case['concurrent'] = list(pool.map(lambda action: measure_samples(action, count=1)['first'], jobs))
                    store = SQLiteStorage(database)
                    try:
                        case['plan_count_after_duplicate_confirm'] = store._conn().execute('SELECT COUNT(*) FROM study_plans').fetchone()[0]
                        case['foreign_key_errors'] = len(store._conn().execute('PRAGMA foreign_key_check').fetchall())
                    finally:
                        store.close()
                    case['http_hot_gate_passed'] = all(v['hot_gate_passed'] for v in case['http'].values())
                    case['concurrency_passed'] = (all(r['ok'] for r in case['concurrent'])
                        and case['plan_count_after_duplicate_confirm'] == 1 and case['foreign_key_errors'] == 0)
            finally:
                stop.set(); sampler.join(timeout=1)
                owned = psutil.Process(process.pid)
                descendants = owned.children(recursive=True)
                for child in reversed(descendants):
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
        case['process_rss_sampled_max_bytes'] = max(rss) if rss else None
        case['rss_note'] = '50ms samples of owned process tree summed RSS include startup; shared pages may be double counted; may miss short peaks; not browser heap'
        case['database_bytes'] = database.stat().st_size
        wal = Path(str(database) + '-wal')
        case['wal_bytes_after_server_exit'] = wal.stat().st_size if wal.exists() else 0
        (root / 'benchmark.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--sizes', type=int, nargs='+', default=[100, 1000, 10000])
    parser.add_argument('--attempts', type=int, default=10000)
    args = parser.parse_args()
    result = prepare_growth(args.output_root, args.sizes, attempts=args.attempts)
    measure_growth(result, args.output_root)
    passed = all(c['http_hot_gate_passed'] and c['concurrency_passed'] for c in result['cases'])
    print(json.dumps({'synthetic': True, 'passed': passed, 'report': str(args.output_root / 'benchmark.json')}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
