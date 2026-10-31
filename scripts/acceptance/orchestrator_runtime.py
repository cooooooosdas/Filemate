"""Synthetic runtime proofs, read-only probes and honest old-engine SQL subsets."""

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
from pathlib import Path

from filemate.course_graph.repository import CourseGraphRepository
from filemate.execution import data_actions
from filemate.execution.storage import SQLiteStorage
from filemate.study.orchestrator.commands import OrchestratorCommands
from filemate.study.orchestrator.models import (
    ConfirmRequest,
    PreviewRequest,
    ScheduleOptions,
    ScopeRequest,
    UndoConfirmRequest,
)
from filemate.study.orchestrator.snapshot import SnapshotReader

ENGINE_SHA256 = '1570d755540a59e371df012865325cb7b498c8d0373fdcfea31f6900f458191d'


def probe(db: Path) -> dict:
    if not db.is_file():
        raise FileNotFoundError('explicit_database_required')
    with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.execute('PRAGMA query_only=ON')
        try:
            json1 = conn.execute("SELECT json_valid('{}')").fetchone()[0] == 1
        except sqlite3.Error:
            json1 = False
        options = [r[0] for r in conn.execute('PRAGMA compile_options')]
        limit = next((int(v.split('=')[1]) for v in options if v.startswith('MAX_VARIABLE_NUMBER=')), 999)
        names = [list(r) for r in conn.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','index') ORDER BY type,name")]
        version = conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        return {'mode': 'probe_only', 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                'platform': platform.system(), 'json1': json1, 'variable_limit': limit, 'schema_version': version,
                'objects': names, 'release': os.getenv('FILEMATE_RELEASE_ID', 'unidentified'), 'rows_exported': 0}


def domain_fingerprints(store) -> dict:
    conn = store._conn()
    result = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if name in ('data_action_previews', 'data_action_audit'):
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        columns = len(conn.execute('PRAGMA table_info(' + quoted + ')').fetchall())
        sql = 'SELECT * FROM ' + quoted
        params = ()
        if name == 'artifacts':
            sql += ' WHERE artifact_type NOT IN (?,?)'
            params = ('learning_orchestration_day', 'learning_orchestration_operation')
        sql += ' ORDER BY ' + ','.join(str(i + 1) for i in range(columns))
        result[name] = data_actions.digest([tuple(r) for r in conn.execute(sql, params)])
    return result


def seed(root: Path, count=1):
    root.mkdir(parents=True, exist_ok=True)
    db = root / 'synthetic.db'
    if db.exists():
        raise FileExistsError('synthetic_database_already_exists')
    store = SQLiteStorage(db)
    store.init_schema()
    sources = [store.save_source(original_name=n, source_path='synthetic.txt') for n in ('原创合成数据结构', '原创合成线性代数')]
    courses = CourseGraphRepository(store)
    ids = []
    for i, sid in enumerate(sources):
        course = courses.create_course(str(i), f'synthetic-runtime-course-{i}')
        courses.attach_sources(course['course_id'], [sid], None, course['revision'])
        ids.append(course['course_id'])
    goal = store.save_artifact(source_id=sources[0], artifact_type='reverse_goal_plan', content={
        'title': '合成复习', 'deadline': '2026-12-31', 'goal_type': 'exam',
        'tasks': [{'task_id': 'review-source', 'title': '复习资料', 'status': 'pending'}]})
    question = {'question_type': 'choice', 'stem': '原创合成题', 'options': ['甲', '乙'], 'answer': 'A'}
    for source_index, source in enumerate(sources):
        questions = [question | {'stem': f'原创合成题 {i}'} for i in range(count)]
        aid = store.save_artifact(source_id=source, artifact_type='questions', content=questions)
        store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer='B', is_correct=False, score=0, feedback='合成回归')
        conn = store._conn()
        row = dict(conn.execute('SELECT * FROM wrong_questions WHERE artifact_id=?', (aid,)).fetchone())
        conn.execute('DELETE FROM wrong_questions WHERE artifact_id=?', (aid,))
        rows = []
        for i, q in enumerate(questions):
            item = row | {'wrong_id': f'synthetic-{source_index}-{i:06}', 'question_index': i,
                          'question': json.dumps(q, ensure_ascii=False), 'next_review_at': '2020-01-01T00:00:00+00:00',
                          'scheduler_version': 'review-interval-v2', 'schedule_status': 'active', 'learning_status': 'needs_review',
                          'error_count': (2 if source_index else 1)}
            rows.append(tuple(item.values()))
        conn.executemany('INSERT INTO wrong_questions (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', rows)
        conn.commit()
    return store, ScopeRequest(goal_id=goal, course_id=ids[0], source_ids=[sources[0]])


def exercise(store, scope):
    before = domain_fingerprints(store)
    schema = probe(store.db_path)['schema_version']
    snapshot = SnapshotReader(store).read(scope)
    body = PreviewRequest(scope=scope, expected_evidence_revision=snapshot.evidence_revision,
                          options=ScheduleOptions(available_minutes=30))
    commands = OrchestratorCommands(store)
    token = commands.preview(body).confirmation_token
    request = ConfirmRequest(**body.model_dump(), confirmation_token=token, request_key='synthetic-runtime-confirm', confirmed=True)
    receipt = commands.confirm(request)
    if commands.confirm(request) != receipt:
        raise AssertionError('non_idempotent_confirm')
    undo = commands.preview_undo(receipt.operation_id)
    commands.confirm_undo(receipt.operation_id, UndoConfirmRequest(confirmation_token=undo.confirmation_token,
                          request_key='synthetic-runtime-undo', confirmed=True))
    if commands.confirm(request).status != 'undone':
        raise AssertionError('undo_reapplied')
    after = domain_fingerprints(store)
    integrity = store._conn().execute('PRAGMA integrity_check').fetchone()[0]
    fk = list(store._conn().execute('PRAGMA foreign_key_check'))
    status = 'PASS' if before == after and integrity == 'ok' and not fk else 'FAIL'
    return {'mode': 'full_application', 'status': status, 'synthetic': True, 'schema_before': schema,
            'schema_after': probe(store.db_path)['schema_version'], 'integrity': integrity, 'foreign_key_errors': len(fk),
            'domain_fingerprint_unchanged': before == after, 'domain_fingerprints': before,
            'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version}


def self_test(root: Path):
    store, scope = seed(root)
    try:
        return exercise(store, scope)
    finally:
        store.close()


def engine_subset(engine: Path, root: Path):
    if not engine.is_file():
        raise FileNotFoundError('sqlite_engine_missing')
    sha = hashlib.sha256(engine.read_bytes()).hexdigest()
    if sha != ENGINE_SHA256:
        raise ValueError('sqlite_engine_identity_mismatch')
    version = subprocess.run([str(engine.resolve()), '-version'], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if not version.startswith('3.26.0 '):
        raise ValueError('sqlite_engine_version_mismatch')
    store, scope = seed(root)
    copy = root / 'old-engine.db'
    with sqlite3.connect(copy) as target:
        store._conn().backup(target)
    statements = []
    store._conn().set_trace_callback(statements.append)
    try:
        full = exercise(store, scope)
    finally:
        store._conn().set_trace_callback(None)
        store.close()
    mutations = [s for s in statements if s.lstrip().split()[0].upper() in ('BEGIN', 'COMMIT', 'ROLLBACK', 'INSERT', 'UPDATE', 'DELETE')]
    sql = '.bail on\nPRAGMA foreign_keys=ON;\n' + ';\n'.join(mutations) + ";\nPRAGMA integrity_check;\nPRAGMA foreign_key_check;\nSELECT COUNT(*) FROM artifacts WHERE artifact_type LIKE 'learning_orchestration_%';\nSELECT COUNT(*) FROM data_action_audit WHERE action LIKE 'orchestrator_%';\n"
    # 旧Windows CLI用窄字符argv；工作目录由系统Unicode API设定，文件参数保持ASCII。
    run = subprocess.run([str(engine.resolve()), copy.name], cwd=root, input=sql.encode('utf-8'), capture_output=True, timeout=60, check=False)
    passed = run.returncode == 0 and run.stdout.split() == [b'ok', b'3', b'2'] and full['status'] == 'PASS'
    return {'mode': 'cli_sql_subset', 'status': 'PASS' if passed else 'FAIL', 'engine_version': version,
            'engine_sha256': sha, 'mutation_statements_executed': len(mutations), 'python_udf_queries_excluded': True,
            'full_target_application_verified': False, 'error': None if passed else 'old_engine_execution_failed'}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def output_path(raw):
    out = Path(raw).resolve()
    if not out.is_relative_to((Path.cwd() / '_working').resolve()) or out.exists():
        raise ValueError('use_new_project_working_output')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--probe-only', action='store_true')
    mode.add_argument('--self-test', action='store_true')
    parser.add_argument('--sqlite', type=Path)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    out = output_path(args.out)
    if args.probe_only:
        if not args.db:
            parser.error('--db is required for read-only probe')
        report = probe(args.db)
        write_json(out, report)
    else:
        if not args.self_test and not args.sqlite:
            parser.error('--sqlite or --self-test is required')
        out.mkdir(parents=True)
        report = self_test(out) if args.self_test else engine_subset(args.sqlite, out)
        write_json(out / 'result.json', report)
    print(json.dumps({k: v for k, v in report.items() if k in ('mode', 'status', 'sqlite', 'schema_version')}))
    return 0 if report.get('status', 'PASS') == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
