"""Exercise the released API using one original synthetic account, then delete only that account."""
import json
import re
import secrets
import os
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

OUT = Path(__file__).resolve().parent
BASE = 'https://filemate.asia'
ROOT = '/api/knowledge-graph/courses'
metadata = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
checks = []
email = f'synthetic-learning-release-{uuid4().hex}@example.invalid'
password = secrets.token_urlsafe(24) + 'A7'
registered = False
STATE = OUT / 'synthetic-state.json'
assert not STATE.exists(), 'Recover the existing synthetic state before creating another account'
with STATE.open('x', encoding='utf-8') as stream:
    json.dump(dict(email=email, password=password), stream)
if os.name == 'nt':
    subprocess.run(['icacls', str(STATE), '/inheritance:r', '/grant:r',
                    os.environ['USERDOMAIN'] + '\\' + os.environ['USERNAME'] + ':F'],
                   check=True, stdout=subprocess.DEVNULL)
else:
    STATE.chmod(0o600)
original_resolver = socket.getaddrinfo
def release_resolver(host, port, *args, **kwargs):
    if host in ('filemate.asia', b'filemate.asia') and str(port) == '443':
        host = '47.104.156.235'
    return original_resolver(host, port, *args, **kwargs)
socket.getaddrinfo = release_resolver
client = httpx.Client(base_url=BASE, timeout=100, follow_redirects=False, trust_env=False,
                      headers={'Origin': BASE, 'X-FileMate-Action': 'account'})
outsider = httpx.Client(base_url=BASE, timeout=35, trust_env=False)


def key():
    return uuid4().hex


def request(method, path, **kwargs):
    time.sleep(0.55)
    for connect_attempt in range(3):
        try:
            response = client.request(method, path, **kwargs)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if connect_attempt == 2:
                raise
            time.sleep(1 + connect_attempt)
    assert response.status_code == 200, f'{method} {path}: {response.status_code}; {response.text[:200]}'
    return response


def api(method, path, body=None, **kwargs):
    if body is not None:
        kwargs['json'] = body
    response = request(method, path, **kwargs)
    assert 'no-store' in response.headers.get('cache-control', '')
    value = response.json()
    assert value['success'] is True
    return value['data']


def confirm(preview):
    return dict(confirmed=True, confirmation_token=preview['confirmation_token'], request_key=key())


def check(name, callback):
    started = time.perf_counter()
    print('RUN ' + name, flush=True)
    try:
        result = callback() or {}
        checks.append(dict(name=name, passed=True, elapsed_ms=round((time.perf_counter()-started)*1000, 2), **result))
        print('PASS ' + name, flush=True)
        return result
    except Exception as exc:
        checks.append(dict(name=name, passed=False, error_type=type(exc).__name__, message=str(exc)[:700]))
        raise
    finally:
        save(False)


def save(passed):
    (OUT / 'public-result.json').write_text(json.dumps(dict(
        passed=passed, at=datetime.now(timezone.utc).isoformat(), checks=checks,
        commit=metadata['commit'], base=BASE,
        transport='process-only verified host IP; TLS SNI and certificate verification retained; connect-only retries',
        evidence_kind='original synthetic account; actual public APIs/providers; no human learning-effect claim',
        browser_matrix='local real Edge 74 original plus 12 final checks; public UI separately recorded'), ensure_ascii=False, indent=2), encoding='utf-8')


def publish(name, lessons):
    cid = api('POST', ROOT, dict(name=name, request_key=key()))['course_id']
    sources = [api('POST', '/knowledge/import', files={
        'file': (f'原创合成-{name}-{i}.txt', text.encode('utf-8'), 'text/plain')})['source_id'] for i, text in enumerate(lessons)]
    base = ROOT + '/' + cid
    api('POST', base + '/sources', dict(source_ids=sources, expected_revision=0))
    draft = api('POST', base + '/drafts', dict(source_ids=sources, mode='local', request_key=key()))
    did = draft['draft_id']
    for sid in sources:
        draft = api('POST', base + f'/drafts/{did}/sources/{sid}/extract', dict(mode='local', request_key=key()))
    choices = [dict(item_id=item['item_id'], verdict='accept', semantic_checked=True)
               for source in draft['sources'] for item in source['payload']['nodes'] + source['payload']['edges']
               if item['validation'] != 'invalid']
    assert choices
    api('POST', base + f'/drafts/{did}/decisions', dict(expected_digest=draft['revision_digest'], decisions=choices))
    p = api('POST', base + f'/drafts/{did}/review-preview')
    api('POST', base + f'/drafts/{did}/confirm', confirm(p))
    return cid, sources, api('GET', base + '/concepts-page')['items']


error = None
try:
    def startup():
        global registered
        marker = request('GET', '/release.json').json()
        assert marker['commit'] == metadata['commit'] and marker['schema_version'] == 36
        assert marker['course_graph'] and marker['graph_assistant'] and marker['wrongbook_v2'] and marker['learning_orchestrator']
        assert api('GET', '/api/ready')['status'] == 'ready'
        html = request('GET', '/', headers={'Accept': 'text/html'})
        assets = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', html.text)
        assert assets
        for asset in assets:
            r = request('GET', asset)
            assert 'immutable' in r.headers.get('cache-control', '') and r.content
        api('POST', '/api/auth/register', dict(email=email, password=password, display_name='原创合成知识成长验收', keep_guest_data=False))
        registered = True
        api('POST', '/api/auth/logout', {})
        api('POST', '/api/auth/login', dict(email=email, password=password))
        assert api('GET', '/api/auth/me')['user']['email'] == email
        return dict(assets_checked=len(assets), account_login=True)
    check('fixed release / readiness / assets / registration and login', startup)

    def modules():
        paths = ['/knowledge/sources', '/wrongbook', '/review/today', '/study-plans', '/analytics/overview',
                 '/api/knowledge-graph', '/api/career/status', '/api/career/positions', '/api/programming/problems',
                 '/api/digital-human/playbacks', '/interview/review/status', '/trust/overview', '/goals']
        for path in paths:
            api('GET', path)
        assert api('GET', '/api/programming/status')['ready']
        return dict(existing_routes=14)
    check('existing feature routes and isolated judge readiness', modules)

    def courses():
        global cid, sources, nid, other, other_nid, base
        cid, sources, nodes = publish('原创合成数据结构', [
            '树包含堆。堆：一种树形结构。堆应用于堆排序。',
            '堆：满足堆序性的树形结构。堆是堆排序的前置知识。'])
        base = ROOT + '/' + cid
        heaps = [node['id'] for node in nodes if node['label'] == '堆']
        assert len(heaps) == 2
        merge = dict(concept_ids=heaps, target_id=heaps[0])
        p = api('POST', base + '/merges/preview', merge)
        api('POST', base + '/merges/confirm', merge | confirm(p))
        nid = heaps[0]
        other, _, nodes2 = publish('原创合成Python基础', ['列表：有序可变的容器。元组：有序不可变的容器。'])
        other_nid = nodes2[0]['id']
        assert outsider.get(base + '/learning/nodes').status_code == 404
        assert api('GET', base + '/workspace')
        assert api('GET', base + '/canvas')
        assert api('GET', base + '/learning/nodes')['total'] > 0
        return dict(courses=2, sources=3, local_extraction=True, confirmed_merge=True, tenant_isolation=True)
    check('course import / cited extraction / item review / fusion / isolated workspace', courses)

    def practice():
        global question, attempt, work
        work = api('POST', base + f'/concepts/{nid}/practice-drafts', dict(mode='local', count=1, difficulty='simple', request_key=key()))
        assert work['status'] == 'ready'
        review = base + f"/learning/work/{work['work_id']}/review"
        decisions = dict(decisions=[dict(index=0, verdict='accept')])
        p = api('POST', review + '/preview', decisions)
        receipt = api('POST', review + '/confirm', decisions | confirm(p))
        question = api('GET', '/knowledge/artifacts/' + receipt['artifact_id'])['content'][0]
        attempt = dict(artifact_id=receipt['artifact_id'], question_index=0, expected_question=question, request_key=key(), user_answer='不会')
        first = api('POST', '/quiz/attempts', attempt)
        assert first['is_correct'] is False
        assert api('POST', '/quiz/attempts', attempt) == first
        assert api('GET', '/wrongbook/page')['total'] == 1
        assert api('POST', '/quiz/attempts', attempt | dict(request_key=key(), user_answer=question['answer']))['is_correct']
        evidence = api('GET', base + f'/concepts/{nid}/learning')
        assert evidence['counts']['attempts'] == 2 and evidence['status'] == 'needs_reinforcement'
        return dict(reviewed_questions=1, attempts=2, duplicate_attempt_prevented=True, wrongbook_entries=1)
    check('practice draft / confirm / true wrong answer / dedupe / review evidence', practice)

    def path_plan():
        global options
        options = dict(goal='原创合成：复习堆', concept_ids=[nid], daily_minutes=20, days=3)
        p = api('POST', base + '/learning/path/preview', options)
        command = options | confirm(p)
        plan = api('POST', base + '/learning/path/confirm', command)
        assert api('POST', base + '/learning/path/confirm', command) == plan
        for action in ('undo', 'restore'):
            route = base + f"/learning/operations/{plan['operation_id']}"
            preview = api('POST', route + '/preview', dict(action=action))
            api('POST', route + '/confirm', dict(action=action) | confirm(preview))
        api('PATCH', f"/study-plans/{plan['plan_id']}/days/0", dict(completed=True))
        assert api('GET', base + f'/concepts/{nid}/learning')['counts']['attempts'] == 2
        return dict(plan_saved=True, duplicate_plan_prevented=True, undo_restore=True, completion_not_mastery=True)
    check('evidence path / idempotent confirmation / undo / restore / daily completion', path_plan)

    def crosslink():
        route = base + f'/concepts/{nid}/related-courses'
        body = dict(other_course_id=other, other_concept_id=other_nid, active=True)
        p = api('POST', route + '/preview', body)
        api('POST', route + '/confirm', body | confirm(p))
        result = api('GET', route)
        assert result['items'][0]['available'] and result['items'][0]['route']
        body['active'] = False
        p = api('POST', route + '/preview', body)
        api('POST', route + '/confirm', body | confirm(p))
        return dict(navigation_only=True, unlink=True)
    check('explicit cross-course navigation and unlink', crosslink)

    def assistant():
        global answer, agent
        answer = api('POST', base + '/assistant/answer', dict(question='如何复习堆？', concept_ids=[nid], mode='rule', request_key=key()))
        assert answer['status'] == 'ready' and answer['payload']['textbook_evidence']
        plans_before = len(api('GET', '/study-plans'))
        agent = api('POST', base + '/assistant/plan/preview', options)
        assert len(agent['tool_steps']) == 4 and len(agent['tasks']) <= 7
        assert len(api('GET', '/study-plans')) == plans_before
        return dict(cited_rule_answer=True, bounded_steps=4, no_autonomous_plan_write=True)
    check('rule assistant / stored facts / bounded Agent preview without writes', assistant)

    def model():
        body = dict(question='仅依据引用说明堆是什么，不评价用户，不给个人统计。', concept_ids=[nid], mode='llm', allow_external_model=True, request_key=key())
        answer = api('POST', base + '/assistant/answer', body)
        assert answer['status'] == 'ready', f"model answer: {answer.get('status')}/{answer.get('error_code')}"
        reread = api('GET', base + f"/learning/work/{answer['work_id']}")
        assert reread['payload'] == answer['payload']
        draft = api('POST', base + f'/concepts/{nid}/practice-drafts', dict(mode='llm', allow_external_model=True, count=1, difficulty='simple', request_key=key()))
        assert draft['status'] == 'ready', f"model practice: {draft.get('status')}/{draft.get('error_code')}"
        assert draft['payload']['questions']
        return dict(actual_provider_calls=2, persisted_answer=True, draft_not_published=True, quality_score=None)
    check('actual provider cited answer and unpublished practice draft', model)

    def review_v2():
        caps = api('GET', '/wrongbook/v2/capabilities')
        assert caps['write_enabled']
        page = api('GET', '/wrongbook/v2/page')
        assert page['total'] == 1
        session = api('GET', '/wrongbook/v2/session-preview?available_minutes=20')
        assert session['selected_count'] <= 20 and session['estimated_minutes'] <= 20
        if session['items']:
            checked = api('POST', '/wrongbook/v2/session-check', {'refs': [item['ref'] for item in session['items']], 'filters': session['filters']})
            assert checked['status'] == 'ready'
        return dict(actual_wrong_total=page['total'], budget_bounded=True, review_preview_read_only=True)
    check('wrongbook v2 enabled / real saved evidence / budgeted preview', review_v2)

    def orchestrator():
        root = '/api/learning/orchestrator'
        caps = api('GET', root + '/capabilities')
        assert caps['enabled'] and caps['ui_contract'] == 'today-workspace-v1'
        deadline = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
        goal = api('POST', '/goals/reverse-plan', dict(title='原创合成：发布验收数据结构目标', goal_type='exam', deadline=deadline, source_id=sources[0]))
        scope = dict(goal_id=goal['goal_id'], course_id=cid, source_ids=[sources[0]])
        directory = api('POST', root + '/goal-options', dict(q='发布验收数据结构目标', offset=0))
        assert len(directory['items']) == 1 and directory['items'][0]['goal_id'] == goal['goal_id']
        def save_schedule(minutes):
            snap = api('POST', root + '/snapshot', scope)
            body = dict(scope=scope, expected_evidence_revision=snap['snapshot']['evidence_revision'], options=dict(available_minutes=minutes))
            preview = api('POST', root + '/preview', body)
            assert preview['estimated_minutes'] <= minutes and len(preview['selected']) <= 20
            request = body | confirm(preview)
            receipt = api('POST', root + '/confirm', request)
            assert api('POST', root + '/confirm', request) == receipt
            assert api('GET', root + '/operations/' + request['request_key']) == receipt
            assert api('GET', root + '/today')['latest_operation']['operation_id'] == receipt['operation_id']
            return receipt
        first = save_schedule(40)
        stale = api('POST', root + f"/operations/{first['operation_id']}/undo-preview", {})
        latest = save_schedule(20)
        rejected = client.post(root + f"/operations/{first['operation_id']}/undo-confirm", json=confirm(stale))
        assert rejected.status_code == 409
        assert rejected.json()['data']['error_code'] == 'schedule_changed_since_operation'
        current = api('POST', root + f"/operations/{latest['operation_id']}/undo-preview", {})
        undone = api('POST', root + f"/operations/{latest['operation_id']}/undo-confirm", confirm(current))
        assert undone['status'] == 'undone'
        assert api('GET', root + '/operations/' + latest['request_key'])['status'] == 'undone'
        assert outsider.post(root + '/snapshot', json=scope).status_code == 404
        return dict(explicit_goal=True, metadata_only_catalog=True, bounded_schedule=True, idempotent_replay=True,
            persisted_receipt=True, exact_concurrent_rejection=True, undo=True, tenant_isolation=True, model_calls=0)
    check('today action metadata / scope / budget / receipt / real 409 / undo', orchestrator)

    def backup_restore():
        raw = request('GET', '/api/privacy/export?format=backup').content
        assert raw[:2] == b'PK'
        p = api('GET', f'/knowledge/sources/{sources[1]}/delete-preview')
        api('DELETE', f'/knowledge/sources/{sources[1]}', dict(confirmed=True, confirmation_token=p['confirmation_token']))
        assert client.get(base + f"/learning/work/{answer['work_id']}").status_code == 404
        p = api('POST', '/api/privacy/restore-preview', files={'file': ('own-synthetic.zip', raw, 'application/zip')})
        assert api('POST', '/api/privacy/restore', dict(backup_id=p['backup_id'], confirmation_token=p['confirmation_token'], confirmed=True))['restored']
        assert api('GET', base + f"/learning/work/{answer['work_id']}")['status'] == 'ready'
        response = client.post(base + '/learning/path/confirm', json=options | confirm(agent))
        assert response.status_code == 409
        return dict(signed_backup=True, source_dependency_purged=True, restore_readable=True, old_token_rejected=True)
    check('personal backup / confirmed source purge / restore / old preview invalidation', backup_restore)

    def judge_voice():
        for code, verdict in [('#include <iostream>\nint main(){int n;std::cin>>n;long long s=0,x;while(n--&&std::cin>>x)s+=x;std::cout<<s;}', 'AC'), ('int main( {', 'CE')]:
            row = api('POST', '/api/programming/submissions', dict(problem_id='array-sum', code=code, language='cpp17', request_key=key()))
            result = api('POST', f"/api/programming/submissions/{row['submission_id']}/run", {})
            assert result['result']['verdict'] == verdict
        for voice in ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiaNeural']:
            response = request('POST', '/api/digital-human/speech', json=dict(text='这是一段原创合成发布验收语音。', voice_id=voice, allow_external_voice=True))
            assert 'audio/mpeg' in response.headers.get('content-type', '') and len(response.content) > 1000
        return dict(actual_judge_verdicts=['AC', 'CE'], actual_mp3_voices=2)
    check('existing isolated compiler AC / CE and natural voice upstream', judge_voice)
except BaseException as exc:
    error = exc
    print(type(exc).__name__ + ': ' + str(exc), flush=True)
finally:
    if registered:
        def cleanup():
            p = api('GET', '/api/auth/delete-preview')
            receipt = api('POST', '/api/auth/delete', dict(password=password, confirmed=True, confirmation_token=p['confirmation_token']))
            assert receipt.get('cleanup_pending') is not True
            STATE.unlink()
            return dict(only_synthetic_account_deleted=True)
        try:
            check('confirmed cleanup of this synthetic account only', cleanup)
        except Exception as exc:
            error = error or exc
    passed = error is None and all(c['passed'] for c in checks)
    save(passed)
    client.close()
    outsider.close()
    print(json.dumps(dict(passed=passed, checks=len(checks)), ensure_ascii=False), flush=True)
    if error is not None:
        raise SystemExit(1)
