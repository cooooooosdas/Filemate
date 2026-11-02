"""Real isolated HTTP journey and backup recovery, with no model or production writes."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path

import httpx

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage
from filemate.operations.backup import create_backup, plan_backup, plan_restore, restore_backup
from filemate.operations.personal_backup import PersonalBackup
from filemate.study.orchestrator.commands import OrchestratorCommands
from filemate.study.orchestrator.models import (
    LOCAL_ZONE,
    ConfirmRequest,
    OrchestratorError,
    UndoConfirmRequest,
    utc_now,
)
from filemate.study.orchestrator.repository import OrchestratorRepository

from .orchestrator_runtime import (
    domain_fingerprints,
    output_path,
    seed_protected_evidence,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
API = '/api/learning/orchestrator'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def start(args, env, cwd, log):
    return subprocess.Popen(args, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)


def stop(process, *, shutdown=None):
    if process is not None and process.poll() is None:
        if shutdown:
            url, token = shutdown
            try:
                httpx.post(url, headers={'x-filemate-shutdown-token': token}, timeout=3,
                           trust_env=False).raise_for_status()
                process.wait(timeout=10)
                return
            except (httpx.HTTPError, subprocess.TimeoutExpired):
                pass
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(url, process):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('owned_service_startup_failed; see isolated logs')
        try:
            if httpx.get(url, timeout=1, trust_env=False).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(.15)
    raise TimeoutError('owned_service_startup_timeout')


def restore_safety_state(store):
    conn = store._conn()
    return {
        'coach': {row['interview_id']: dict(row) for row in conn.execute(
            'SELECT interview_id,revision,consent_revision,external_consent,updated_at FROM interview_coach_state')},
        'review': {row['interview_id']: dict(row) for row in conn.execute(
            'SELECT interview_id,revision,input_digest FROM interview_review_state')},
    }


def safety_state_rotated(before, after):
    from datetime import datetime
    if set(before['coach']) != set(after['coach']) or set(before['review']) != set(after['review']):
        return False
    for key, original in before['coach'].items():
        current = after['coach'][key]
        if (current['revision'] != original['revision'] + 1 or current['consent_revision'] != original['consent_revision'] + 1
                or current['external_consent'] != 0 or datetime.fromisoformat(current['updated_at']) < datetime.fromisoformat(original['updated_at'])):
            return False
    return all(after['review'][key]['revision'] == row['revision'] + 1 and after['review'][key]['input_digest'] == ''
               for key, row in before['review'].items())


def run_journey(root: Path):
    if root.exists():
        raise FileExistsError('use_a_new_candidate_directory')
    root.mkdir(parents=True)
    data = root / 'data'
    data.mkdir()
    api_port, web_port = free_port(), free_port()
    if api_port == web_port:
        raise RuntimeError('port_collision_retry_new_candidate')
    shutdown_token = uuid.uuid4().hex
    shutdown = (f'http://127.0.0.1:{api_port}/internal/shutdown', shutdown_token)
    env = dict(os.environ) | {'PYTHONUTF8': '1', 'FILEMATE_ENV': 'development', 'FILEMATE_IDENTITY_MODE': 'local',
        'FILEMATE_DATA_DIR': str(data), 'FILEMATE_DB_PATH': str(data / 'filemate.db'),
        'FILEMATE_UPLOAD_DIR': str(data / 'inbox'), 'FILEMATE_ARCHIVE_DIR': str(data / 'archive'),
        'FILEMATE_ENABLE_LEARNING_ORCHESTRATOR': '1', 'FILEMATE_ENABLE_KNOWLEDGE_GRAPH': '1',
        'FILEMATE_ENABLE_COURSE_GRAPH': '1',
        'FILEMATE_ENABLE_WRONGBOOK_V2': '1', 'VITE_API_URL': f'http://127.0.0.1:{api_port}',
        'FILEMATE_HOST': '127.0.0.1', 'FILEMATE_PORT': str(api_port),
        'FILEMATE_SHUTDOWN_TOKEN': shutdown_token}
    backend_args = [sys.executable, '-m', 'server']
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('node_required_for_real_proxy_verification')
    frontend_args = [node, str(ROOT / 'filemate/web/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(web_port), '--strictPort']
    checks, steps = {}, []
    backend = frontend = None
    with ExitStack() as log_stack:
        try:
            logs = [log_stack.enter_context(open(root / name, 'xb')) for name in ('backend.log', 'frontend.log')]
            backend = start(backend_args, env, ROOT, logs[0])
            wait_ready(f'http://127.0.0.1:{api_port}/api/ready', backend)
            frontend = start(frontend_args, env, ROOT / 'filemate/web', logs[1])
            wait_ready(f'http://127.0.0.1:{web_port}{API}/capabilities', frontend)
            with httpx.Client(base_url=f'http://127.0.0.1:{api_port}', timeout=30, trust_env=False) as client:
                def call(method, path, **kwargs):
                    res = client.request(method, path, **kwargs)
                    res.raise_for_status()
                    body = res.json()
                    if body.get('success') is not True:
                        raise AssertionError('domain_response_failed')
                    steps.append({'method': method, 'path': path.split('?')[0], 'status': res.status_code})
                    return body['data']
                sources, courses, goals = [], [], []
                for i, name in enumerate(('数据结构', '线性代数')):
                    text = f'# 原创合成{name}\n栈遵循后进先出，队列遵循先进先出。此文件仅用于工程回归。课程{i}。'
                    source = call('POST', '/knowledge/import', files={'file': (f'synthetic-{i}.md', text.encode('utf-8'), 'text/markdown')})
                    sid = source['source_id']; sources.append(sid)
                    course = call('POST', '/api/knowledge-graph/courses', json={'name': name, 'request_key': f'synthetic-journey-course-{i}'})
                    courses.append(course['course_id'])
                    call('POST', f"/api/knowledge-graph/courses/{course['course_id']}/sources", json={'source_ids': [sid], 'expected_revision': course['revision']})
                    deadline = (utc_now().astimezone(LOCAL_ZONE).date() + timedelta(days=20)).isoformat()
                    goal = call('POST', '/goals/reverse-plan', json={'title': f'原创合成{name}目标', 'goal_type': 'exam', 'deadline': deadline, 'source_id': sid})
                    goals.append(goal['goal_id'])
                # 原创测试题通过现役仓储准备；真实作答、完成与删除均走原HTTP接口。
                store = SQLiteStorage(data / 'filemate.db')
                question = {'question_type': 'choice', 'stem': '栈的顺序是什么？', 'options': ['后进先出', '先进先出'], 'answer': 'A', 'analysis': '栈后进先出。'}
                artifact = store.save_source_artifact(source_id=sources[0], artifact_type='questions', content=[question], title='原创合成题集', metadata={'synthetic': True})
                store.close()
                call('POST', '/quiz/attempts', json={'artifact_id': artifact['artifact_id'], 'question_index': 0, 'user_answer': 'B', 'expected_question': question})
                scope = {'goal_id': goals[0], 'course_id': courses[0], 'source_ids': [sources[0]]}
                for accept, key in [('application/json', 'proxy_json_accept'), ('text/html', 'proxy_html_accept')]:
                    response = httpx.post(f'http://127.0.0.1:{web_port}{API}/snapshot', json=scope, headers={'Accept': accept}, timeout=30)
                    response.raise_for_status()
                    checks[key] = 'application/json' in response.headers['content-type'] and response.json()['success']

                catalog = call('POST', API + '/goal-options', json={'q': '', 'offset': 0})
                checks['c_goal_options_metadata_only'] = catalog['limit'] == 30 and catalog['total'] == 2 and all(
                    set(row) == {'goal_id', 'title', 'goal_type', 'deadline', 'source_id', 'valid'} for row in catalog['items'])
                new_snapshot = call('POST', API + '/snapshot', json=scope)['snapshot']
                checks['c_snapshot_labels_and_contract_version'] = (
                    call('GET', API + '/capabilities')['ui_contract'] == 'today-workspace-v1'
                    and new_snapshot['facts']['goal']['title'] == '原创合成数据结构目标'
                    and new_snapshot['facts']['sources'][0]['original_name'] == 'synthetic-0.md')

                def arrange(minutes, key, discard_ack=False):
                    snap = call('POST', API + '/snapshot', json=scope)['snapshot']
                    body = {'scope': scope, 'expected_evidence_revision': snap['evidence_revision'], 'options': {'available_minutes': minutes}}
                    preview = call('POST', API + '/preview', json=body)
                    if preview['estimated_minutes'] > minutes or len({t['task_id'] for t in preview['selected']}) != len(preview['selected']):
                        raise AssertionError('budget_or_dedup_failed')
                    request = body | {'confirmation_token': preview['confirmation_token'], 'request_key': key, 'confirmed': True}
                    if discard_ack:
                        with client.stream('POST', API + '/confirm', json=request) as response:
                            response.raise_for_status()
                            steps.append({'method': 'POST', 'path': API + '/confirm', 'status': response.status_code, 'response_body_intentionally_discarded': True})
                        return request, call('GET', API + '/operations/' + key)
                    return request, call('POST', API + '/confirm', json=request)
                store = SQLiteStorage(data / 'filemate.db')
                protected_counts = seed_protected_evidence(store)
                before = domain_fingerprints(store)
                first_request, first = arrange(45, 'synthetic-journey-confirm-1', discard_ack=True)
                checks['lost_ack_original_key_recovered_once'] = first['request_key'] == first_request['request_key'] and store._conn().execute(
                    'SELECT count(*) FROM artifacts WHERE artifact_id=?', (first['operation_id'],)).fetchone()[0] == 1
                assert call('GET', API + '/operations/' + first['request_key']) == first
                assert call('POST', API + '/confirm', json=first_request) == first
                _, second = arrange(15, 'synthetic-journey-confirm-2')
                checks['schedule_commands_preserve_domain_fingerprints'] = before == domain_fingerprints(store)
                from filemate.study.orchestrator.repository import day_id
                conn = store._conn()
                saved = conn.execute('SELECT content FROM artifacts WHERE artifact_id=?', (day_id(second['study_date']),)).fetchone()[0]
                legacy = json.loads(saved)
                legacy.pop('last_operation_id', None)
                try:
                    with conn:
                        conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps(legacy), day_id(second['study_date'])))
                    legacy_day = call('GET', API + '/today')
                    checks['legacy_day_without_pointer_still_readable'] = legacy_day['latest_operation'] is None and legacy_day['scope'] == scope and legacy_day['status'] == 'confirmed'
                finally:
                    with conn:
                        conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (saved, day_id(second['study_date'])))
                store.close()
                call('PATCH', f'/goals/{goals[0]}/tasks/review-source', json={'completed': True})
                completed = call('GET', API + '/today')
                completed_id = f'goal:{goals[0]}:review-source'
                checks['real_domain_completion'] = completed_id in [t['task_id'] for t in completed['completed']]
                undo = call('POST', API + '/operations/' + second['operation_id'] + '/undo-preview', json={})
                call('POST', API + '/operations/' + second['operation_id'] + '/undo-confirm', json={
                    'confirmation_token': undo['confirmation_token'], 'request_key': 'synthetic-journey-undo-1', 'confirmed': True})
                checks['undo_preserves_completion'] = completed_id in [t['task_id'] for t in call('GET', API + '/today')['completed']]
                third_request, third = arrange(45, 'synthetic-journey-confirm-3')
                undo_pending = call('POST', API + '/operations/' + third['operation_id'] + '/undo-preview', json={})
                undo_pending = {'confirmation_token': undo_pending['confirmation_token'], 'request_key': 'synthetic-restored-unused-undo', 'confirmed': True}
                snap = call('POST', API + '/snapshot', json=scope)['snapshot']
                pending = {'scope': scope, 'expected_evidence_revision': snap['evidence_revision'], 'options': {'available_minutes': 10}}
                pending_token = call('POST', API + '/preview', json=pending)['confirmation_token']
                pending |= {'confirmation_token': pending_token, 'request_key': 'synthetic-restore-old-token', 'confirmed': True}
                exported = client.get('/api/privacy/export?format=backup')
                exported.raise_for_status()
                (root / 'personal-synthetic.zip').write_bytes(exported.content)
                # 使用现役宿主关闭合同，等待SQLite正常释放WAL句柄。
                client.post('/internal/shutdown', headers={'x-filemate-shutdown-token': shutdown_token}).raise_for_status()
                backend.wait(timeout=10)
                try:
                    with socket.create_connection(('127.0.0.1', api_port), timeout=1):
                        pass
                    checks['network_outage_preserves_data'] = False
                except OSError:
                    checks['network_outage_preserves_data'] = True
                store = SQLiteStorage(data / 'filemate.db')
                frozen = domain_fingerprints(store)
                frozen_business = domain_fingerprints(store, restored=True)
                frozen_safety = restore_safety_state(store)
                store.close()
                plan = plan_backup(data)
                create_backup(data, root / 'managed-backup', plan['confirmation'], quiesced=True)
                target = root / 'managed-restored'
                restore_plan = plan_restore(root / 'managed-backup', target)
                restore_backup(root / 'managed-backup', target, restore_plan['confirmation'])
                restored = SQLiteStorage(target / 'filemate.db')
                # 全量业务字段相等；仅逐字段验证既定的安全修订提升，而非放宽所有状态。
                checks['managed_restore_fingerprints_match'] = domain_fingerprints(restored, restored=True) == frozen_business
                checks['managed_restore_safety_states_rotated'] = safety_state_rotated(frozen_safety, restore_safety_state(restored))
                restored_commands = OrchestratorCommands(restored)
                rejected = []
                for action in (lambda: restored_commands.confirm(ConfirmRequest(**pending)),
                               lambda: restored_commands.confirm(ConfirmRequest(**third_request)),
                               lambda: restored_commands.confirm_undo(third['operation_id'], UndoConfirmRequest(
                                   confirmation_token=undo_pending['confirmation_token'],
                                   request_key='synthetic-restored-unused-undo',
                                   confirmed=True))):
                    try:
                        action()
                        rejected.append(False)
                    except OrchestratorError:
                        rejected.append(True)
                checks['managed_restore_invalidates_old_tokens'] = all(rejected) and restored._conn().execute(
                    "SELECT count(*) FROM data_action_previews WHERE action IN ('orchestrator_confirm','orchestrator_undo')").fetchone()[0] == 0
                restored.close()
                try:
                    plan_restore(root / 'managed-backup', target)
                    checks['managed_restore_rejects_overwrite'] = False
                except ValueError:
                    checks['managed_restore_rejects_overwrite'] = True
                backend = start(backend_args, env, ROOT, logs[0])
                wait_ready(f'http://127.0.0.1:{api_port}/api/ready', backend)
                restarted_day = call('GET', API + '/today')
                checks['restart_preserves_completion'] = completed_id in [t['task_id'] for t in restarted_day['completed']]
                checks['restart_keeps_verified_day_receipt'] = restarted_day['latest_operation'] == third
                for index in (1, 0):
                    previous = call('GET', API + '/today')
                    preview = call('GET', f'/knowledge/sources/{sources[index]}/delete-preview')
                    call('DELETE', f'/knowledge/sources/{sources[index]}', json={'confirmed': True, 'confirmation_token': preview['confirmation_token']})
                    current = call('GET', API + '/today')
                    checks['unrelated_source_delete_preserves_view' if index else 'affected_source_delete_stales_view'] = current == previous if index else current['status'] == 'stale'
            stop(backend, shutdown=shutdown); backend = None
            personal_root = root / 'personal-restored'
            personal_root.mkdir()
            # 个人备份属于同一签名空间；隔离恢复保留本次合成空间密钥，不绕过验签。
            key_path = personal_root / 'filemate.backup-secret'
            with key_path.open('xb') as handle:
                handle.write((data / 'filemate.backup-secret').read_bytes())
            key_path.chmod(0o600)
            new_store = SQLiteStorage(personal_root / 'filemate.db')
            new_store.init_schema()
            try:
                personal = PersonalBackup(new_store, 'local', personal_root / 'inbox', personal_root / 'archive')
                preview = personal.preview(exported.content)
                personal.restore(preview['backup_id'], preview['confirmation_token'])
                protected_tables = ('interview_turns', 'kg_relations', 'kg_evidence', 'quiz_attempts', 'wrong_questions', 'review_events', 'study_plans')
                restored_fingerprints = domain_fingerprints(new_store)
                checks['personal_restore_preserves_nonempty_feature_records'] = all(restored_fingerprints[name] == frozen[name] for name in protected_tables)
                checks['personal_restore_safety_states_rotated'] = safety_state_rotated(frozen_safety, restore_safety_state(new_store))
                repo = OrchestratorRepository(new_store)
                view = repo.today(utc_now().astimezone(LOCAL_ZONE).date())
                checks['personal_restore_keeps_refs'] = view.scope is not None and view.scope.goal_id == goals[0] and completed_id in [t.task_id for t in view.completed]
                absent = new_store._conn().execute('SELECT 1 FROM data_action_previews WHERE token_hash=?', (digest(pending_token),)).fetchone() is None
                try:
                    OrchestratorCommands(new_store).confirm(ConfirmRequest.model_validate(pending))
                    checks['personal_restore_invalidates_old_tokens'] = False
                except OrchestratorError:
                    checks['personal_restore_invalidates_old_tokens'] = absent
            finally:
                new_store.close()
            return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'synthetic': True,
                    'fixture_setup': 'one original question artifact; domain actions via original HTTP',
                    'checks': checks, 'steps': steps, 'protected_evidence_counts': protected_counts, 'domain_fingerprints_before_decision': before,
                    'domain_fingerprints_at_backup': frozen, 'production_touched': False,
                    'shutdown_mode': 'owned_authenticated_graceful_stop'}
        finally:
            stop(frontend); stop(backend, shutdown=shutdown)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    root = output_path(args.out)
    report = run_journey(root)
    write_json(root / 'result.json', report)
    print(json.dumps({'status': report['status'], 'checks': report['checks']}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
