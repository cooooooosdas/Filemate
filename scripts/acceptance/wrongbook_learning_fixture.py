"""Provide isolated original data and a loopback-only synthetic model for D acceptance."""
import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from filemate.accounts import AccountStore, validate_password
from filemate.course_graph.repository import CourseGraphRepository
from filemate.execution.storage import SQLiteStorage
from scripts.acceptance.wrongbook_workspace_fixture import seed


def prepare(root: Path, password: str) -> dict:
    """Refuse existing roots and generate no real student records."""
    if not root.is_absolute() or root.exists():
        raise ValueError('synthetic_root_must_be_new_absolute_path')
    validate_password(password)
    root.mkdir(parents=True, exist_ok=False)
    (root/'.synthetic-wrongbook').touch()
    store = SQLiteStorage(root/'accounts.db')
    store.init_schema()
    store.close()
    accounts = AccountStore(root/'accounts.db')
    users = []
    for count in (100, 0):
        workspace = f'u_{uuid4().hex}'
        email = f'learning-{count}@example.invalid'
        accounts.register(email, password, f'D级合成账户{count}', workspace, False)
        data = seed(root/'users'/workspace/'filemate.db', count)
        if count:
            db = SQLiteStorage(root/'users'/workspace/'filemate.db')
            db.init_schema()
            repo = CourseGraphRepository(db)
            cid = repo.create_course('另一门课程：数据库', 'synthetic_second_course')['course_id']
            sid = db.save_source(original_name='原创数据库课程', source_path='synthetic-other.txt', raw_text='事务提供原子性、一致性、隔离性、持久性。')
            repo.attach_sources(cid, [sid], None, 0)
            data['other_course_id'] = cid
            db.close()
        users.append({'email': email, 'workspace': workspace, **data})
    result = {'synthetic': True, 'data_root': str(root), 'users': users,
        'notice': '原创合成工程测试，不代表外部模型质量或真人学习效果；凭据不写报告。'}
    (root/'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def serve_provider(root: Path, port: int):
    """Serve fixed scenarios exclusively on loopback with a synthetic-root guard."""
    if not (root/'.synthetic-wrongbook').is_file():
        raise ValueError('missing_synthetic_marker')
    state = {'mode': 'success', 'calls': 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, data, code=200):
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def do_GET(self):
            self.reply(state)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/__mode':
                mode = body.get('mode')
                if mode not in {'success', 'long', '401', '429', 'bad_json', 'no_refs', 'false_refs', 'dribble'}:
                    self.reply({'error': 'unknown_mode'}, 400)
                    return
                state['mode'] = mode
                self.reply(state)
                return
            state['calls'] += 1
            mode = state['mode']
            if mode in {'401', '429'}:
                self.reply({'error': 'synthetic-only-provider-failure'}, int(mode))
                return
            context = json.loads(next(m['content'] for m in body['messages'] if m['role'] == 'user'))
            output = {'kind': 'insufficient_evidence', 'possible_causes': [], 'uncertainties': ['单次回答不足以确定稳定错因。'],
                'smallest_action': '遮住参考再解释一次栈的顺序。', 'targeted_practice_suggestion': '独立重答后核对资料。',
                'schedule_suggestion': '保留原排期，是否新增任务由你确认。', 'reasons': ['只使用真实输入，不推断掌握率。']}
            if context['source_evidence']:
                cause = {'cause_code': 'concept_gap', 'hypothesis': '可能混淆了栈与队列，请用原文核对。',
                    'answer_evidence_refs': [{'attempt_id': context['attempt']['attempt_id'], 'quote': context['attempt']['user_answer'][:200]}],
                    'source_evidence_refs': [context['source_evidence'][0]['evidence_id']]}
                output.update(kind='supported_hypotheses', possible_causes=[cause])
                if mode == 'no_refs':
                    cause['source_evidence_refs'] = []
                elif mode == 'false_refs':
                    cause['source_evidence_refs'] = ['fabricated-source']
                elif mode == 'long':
                    cause['hypothesis'] = '需要结合原回答及资料继续核对。'*25
            text = 'not json' if mode == 'bad_json' else json.dumps(output, ensure_ascii=False)
            try:
                if mode == 'dribble':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    for _ in range(500):
                        self.wfile.write(b' ')
                        self.wfile.flush()
                        time.sleep(.05)
                else:
                    self.reply({'choices': [{'message': {'content': text}}],
                        'usage': {'prompt_tokens': 30, 'completion_tokens': 20, 'total_tokens': 50}})
            except OSError:
                pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--provider-port', type=int)
    args = parser.parse_args()
    if args.provider_port:
        serve_provider(args.data_root, args.provider_port)
    else:
        prepare(args.data_root, os.environ.get('FILEMATE_AUDIT_PASSWORD', ''))
