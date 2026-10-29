"""Run the ten release scenarios and a quiesced whole-workspace recovery."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from filemate.execution.storage import SQLiteStorage

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8041)
    parser.add_argument('--compatibility', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.data_root.resolve(), args.out.resolve()
    working = (ROOT / '_working').resolve()
    assert root.is_relative_to(working) and out.is_relative_to(working) and not out.exists()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    compatibility = json.loads(args.compatibility.read_text(encoding='utf-8'))
    assert manifest['synthetic'] and (root / '.synthetic-wrongbook').exists()
    assert compatibility['passed'] and compatibility['engine'].startswith('3.26.0')
    password = os.environ['FILEMATE_AUDIT_PASSWORD']
    user = next(u for u in manifest['users'] if not u['wrong_count'])
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    out.mkdir()
    store = SQLiteStorage(root / 'users' / user['workspace'] / 'filemate.db')
    question = store.get_artifact(user['artifact_id'])['content'][0]
    assert not store._conn().execute('SELECT 1 FROM wrong_questions LIMIT 1').fetchone()
    store.close()
    base, origin = f'http://127.0.0.1:{args.port}', 'http://127.0.0.1:5200'
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', FILEMATE_ENV='development', FILEMATE_IDENTITY_MODE='anonymous',
               FILEMATE_IDENTITY_SECRET='', FILEMATE_DATA_DIR=str(root),
               FILEMATE_DB_PATH=str(root / 'filemate.db'), FILEMATE_UPLOAD_DIR=str(root / 'inbox'),
               FILEMATE_ARCHIVE_DIR=str(root / 'archive'), FILEMATE_CORS_ORIGINS=origin,
               FILEMATE_ENABLE_WRONGBOOK_V2='1', FILEMATE_ENABLE_WRONGBOOK_AI='1',
               FILEMATE_ENABLE_COURSE_GRAPH='1', LLM_PROVIDER='openai_compatible',
               LLM_BASE_URL='http://127.0.0.1:1', LLM_MODEL='synthetic-unavailable',
               LLM_API_KEY='synthetic-only-never-real')
    process, log = None, None
    results = []
    client = httpx.Client(base_url=base, headers={'Origin': origin, 'X-FileMate-Action': 'model'},
                          timeout=35)

    def record(name, passed, **evidence):
        results.append({'name': name, 'passed': bool(passed), 'evidence': evidence})
        (out / 'results.json').write_text(json.dumps(
            {'synthetic': True, 'checks': results}, ensure_ascii=False, indent=2), encoding='utf-8')
        if not passed:
            raise AssertionError(name)

    def start(label, data_root):
        nonlocal process, log
        for key, suffix in [('FILEMATE_DATA_DIR', ''), ('FILEMATE_DB_PATH', 'filemate.db'),
                            ('FILEMATE_UPLOAD_DIR', 'inbox'), ('FILEMATE_ARCHIVE_DIR', 'archive')]:
            env[key] = str(data_root / suffix)
        log = (out / (label + '.log')).open('w', encoding='utf-8')
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server:app', '--host',
                                    '127.0.0.1', '--port', str(args.port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            assert process.poll() is None, 'owned API exited'
            try:
                if client.get('/api/health').status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        raise TimeoutError('owned API startup')

    def stop():
        nonlocal process, log
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)
        if log:
            log.close()
        process, log = None, None

    def request(method, path, body=None):
        response = client.request(method, path, json=body)
        assert response.status_code == 200, (path, response.status_code, response.text[:300])
        payload = response.json()
        assert payload['success'], path
        return payload['data']

    def login(who=user):
        response = client.post('/api/auth/login', headers={'X-FileMate-Action': 'account'},
                               json={'email': who['email'], 'password': password, 'remember': False})
        assert response.status_code == 200, 'synthetic account login'

    def answer(value):
        return request('POST', '/wrongbook/v2/attempts', {
            'artifact_id': user['artifact_id'], 'question_index': 0,
            'expected_question': question, 'user_answer': value, 'request_key': uuid.uuid4().hex})

    def backup(command, *arguments, expect_success=True):
        result = subprocess.run([sys.executable, '-m', 'filemate.operations.backup', command,
                                 *(str(value) for value in arguments)], cwd=ROOT, env=env,
                                capture_output=True, encoding='utf-8', timeout=60, check=False)
        assert (result.returncode == 0) is expect_success, (command, result.stdout[:400])
        payload = json.loads(result.stdout)
        label = command + ('' if expect_success else '-repeat-rejected')
        (out / ('cli-' + label + '.json')).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload

    try:
        start('initial', root)
        login()
        first = answer('B')
        wid = first['wrong_id']
        path = '/wrongbook/v2/' + wid
        record('01 wrong answer creates durable independent attempt', first['is_correct'] is False,
               wrong_id=wid, attempt_id=first['attempt_id'])
        detail = request('GET', path)
        source = request('GET', '/knowledge/sources/' + user['source_id'])
        record('02 original answer, question analysis and source remain readable',
               request('GET', path + '/attempts')['items'][0]['user_answer'] == 'B'
               and detail['question']['analysis'] == question['analysis']
               and '原创合成资料' in json.dumps(source, ensure_ascii=False), source_id=user['source_id'])
        request('PATCH', path + '/diagnosis', {
            'request_key': uuid.uuid4().hex, 'expected_revision': detail['revision'],
            'error_causes': ['concept_gap'], 'primary_cause': 'concept_gap',
            'custom_tags': [], 'note': '原创合成：误把队列顺序用于栈。'})
        correct = answer('A')
        record('03 diagnosis and second independent answer persist',
               correct['attempt_id'] != first['attempt_id']
               and request('GET', path)['error_causes'] == ['concept_gap'])
        state = request('GET', path)
        record('04 due correct answer updates conservative rule and date',
               correct['is_correct'] is True and state['learning_status'] == 'provisional'
               and not state['mastered'] and state['next_review_at'] != detail['next_review_at'],
               rule=state['scheduler_version'], status=state['learning_status'],
               next_review_at=state['next_review_at'])
        again = answer('B')
        history = request('GET', path + '/attempts')
        state = request('GET', path)
        record('05 wrong again preserves all attempts and replans',
               history['total'] == 3 and state['learning_status'] == 'needs_review'
               and again['attempt_id'] not in {first['attempt_id'], correct['attempt_id']})
        schedule = {'request_key': uuid.uuid4().hex, 'expected_revision': state['revision'],
                        'action': 'reschedule',
                        'next_review_at': (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()}
        preview = request('POST', path + '/schedule-preview', schedule)
        request('POST', path + '/schedule-confirm', dict(
            **schedule, confirmed=True, confirmation_token=preview['confirmation_token']))
        time.sleep(4)
        today_before = request('GET', '/review/today')
        assert any(row.get('wrong_id') == wid for row in today_before['items'])
        answer('A')
        today_after = request('GET', '/review/today')
        record('06 Today and review state agree after due completion',
               not any(row.get('wrong_id') == wid for row in today_after['items'])
               and request('GET', path)['learning_status'] == 'provisional',
               pending_before=today_before['pending_wrong_count'],
               pending_after=today_after['pending_wrong_count'])
        connections = request('GET', path + '/connections')
        encoded = json.dumps(connections)
        record('07 precise real course and node references exist',
               user['course_id'] in encoded and user['concept_id'] in encoded,
               course_id=user['course_id'], concept_id=user['concept_id'])
        latest = request('GET', path + '/attempts')['items'][0]
        context = request('GET', path + '/learning-context?attempt_id=' + latest['attempt_id'])
        failed = request('POST', path + '/analyses', {
            'attempt_id': latest['attempt_id'], 'request_key': uuid.uuid4().hex,
            'input_digest': context['input_digest'], 'allow_external_model': True})
        record('08 unavailable provider persists failure and leaves base practice usable',
               failed['status'] == 'failed' and request('GET', path + '/attempts')['total'] == 4,
               analysis_status=failed['status'])
        before_restart = request('GET', path + '/attempts')
        stop()
        client.cookies.clear()
        start('restarted', root)
        login()
        after_restart = request('GET', path + '/attempts')
        record('09 process restart and fresh login preserve answers and analysis',
               before_restart == after_restart
               and request('GET', path + '/analyses')['items'][0]['status'] == 'failed')
        record('10 actual SQLite326 reads legacy and current migrated data',
               compatibility['legacy_answer_preserved'] and compatibility['sqlite326_backup_restore'],
               compatibility=str(args.compatibility))
        stop()
        # Fixture metadata is deliberately outside the product's managed backup layout.
        for name in ['manifest.json', '.synthetic-wrongbook']:
            (root / name).rename(out / ('fixture-' + name))
        plan = backup('plan', '--data-dir', root)
        snapshot = out / 'snapshot'
        backup('create', '--data-dir', root, '--out', snapshot,
               '--confirm', plan['confirmation'], '--quiesced')
        verified = backup('verify', '--backup', snapshot)
        restored = out / 'restored'
        recovery = backup('restore-plan', '--backup', snapshot, '--target', restored)
        backup('restore', '--backup', snapshot, '--target', restored,
               '--confirm', recovery['confirmation'])
        record('whole managed backup verifies and restores to a new root',
               bool(verified) and root.exists() and restored.exists())
        backup('create', '--data-dir', root, '--out', snapshot,
               '--confirm', plan['confirmation'], '--quiesced', expect_success=False)
        backup('restore', '--backup', snapshot, '--target', restored,
               '--confirm', recovery['confirmation'], expect_success=False)
        record('backup CLI rejects repeated creation and restore without overwriting', True)
        client.cookies.clear()
        start('restored', restored)
        login()
        restored_history = request('GET', path + '/attempts')
        record('whole recovery preserves wrongbook versions, failed AI and source content',
               restored_history == before_restart
               and request('GET', path + '/analyses')['items'][0]['status'] == 'failed'
               and bool(request('GET', '/knowledge/sources/' + user['source_id'])))
        login(manifest['users'][0])
        record('restored account isolation rejects another account wrong record',
               client.get(path).status_code == 404)
        print(json.dumps({'checks': len(results), 'passed': all(r['passed'] for r in results)}))
    finally:
        stop()
        client.close()


if __name__ == '__main__':
    main()
