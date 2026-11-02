"""Exercise the real private worker against a loopback provider only."""

import importlib
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from filemate.llm_client import LLMConfig
from filemate.runtime_governance import default_scope


@pytest.fixture
def provider():
    calls, mode = [], ['success']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            code = int(mode[0]) if mode[0] in {'401', '429'} else 200
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                if mode[0] == 'dribble':
                    for _ in range(200):
                        self.wfile.write(b' ')
                        self.wfile.flush()
                        time.sleep(0.05)
                else:
                    text = 'not json' if mode[0] == 'bad_json' else '{"ok":true}'
                    self.wfile.write(json.dumps({'choices': [{'message': {'content': text}}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}}).encode())
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, calls, mode
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def runner():
    assert importlib.util.find_spec('filemate.llm_client.bounded_call'), '缺少可回收LLM工作进程'
    return importlib.import_module('filemate.llm_client.bounded_call').BoundedLLMRunner()


@pytest.mark.parametrize('mode_name', ['success', '401', '429', 'bad_json'])
def test_worker_uses_one_call_same_scope_and_safe_failure(provider, monkeypatch, mode_name):
    server, calls, mode = provider
    mode[0] = mode_name
    process_records = []
    original = subprocess.Popen
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        process_records.append((process, args[0], kwargs['env']))
        return process
    monkeypatch.setattr(subprocess, 'Popen', capture)
    secret = 'synthetic-private-key-never-real'
    config = LLMConfig(provider='openai_compatible', api_key=secret,
        model='synthetic-model', base_url=f'http://127.0.0.1:{server.server_port}')
    scope = default_scope()
    result = runner().run(config, scope, prompt='合成测试', messages=[{'role': 'user', 'content': '合成'}],
        schema={'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False},
        deadline=time.monotonic()+10, cancelled=lambda: False)
    assert len(calls) == 1 and calls[0]['max_tokens'] == 3500
    if mode_name == 'success':
        assert result['output'] == {'ok': True} and result['usage']['total_tokens'] == 13
    else:
        assert result['error_code'] == {'401': 'provider_unavailable', '429': 'quota_exceeded', 'bad_json': 'invalid_output'}[mode_name]
    assert len(process_records) == 1
    process, argv, env = process_records[0]
    assert process.poll() is not None and secret not in repr(argv) and secret not in repr(env)
    assert 'LLM_API_KEY' not in env and 'DEEPSEEK_API_KEY' not in env
    with scope.store._connection() as conn:
        rows = conn.execute('SELECT owner_hash,operation,status FROM ai_attempts').fetchall()
    assert len(rows) == 1 and rows[0]['owner_hash'] == scope.owner_hash
    assert rows[0]['operation'] == scope.operation


def test_worker_deadline_kills_dribbling_provider(provider, monkeypatch):
    server, calls, mode = provider
    mode[0] = 'dribble'
    processes = []
    original = subprocess.Popen
    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        processes.append(result)
        return result
    monkeypatch.setattr(subprocess, 'Popen', capture)
    config = LLMConfig(provider='openai_compatible', api_key='synthetic-only', model='synthetic-model',
        base_url=f'http://127.0.0.1:{server.server_port}')
    started = time.monotonic()
    result = runner().run(config, default_scope(), prompt='合成', messages=[], schema={'type': 'object'},
        deadline=started+3, cancelled=lambda: False)
    assert result['error_code'] == 'timeout'
    assert time.monotonic()-started < 5 and len(calls) == 1
    assert len(processes) == 1 and processes[0].poll() is not None


def test_worker_cancel_reaps_its_process(provider, monkeypatch):
    server, calls, mode = provider
    mode[0] = 'dribble'
    processes = []
    original = subprocess.Popen
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', capture)
    config = LLMConfig(provider='openai_compatible', api_key='synthetic-only', model='synthetic-model',
        base_url=f'http://127.0.0.1:{server.server_port}')
    result = runner().run(config, default_scope(), prompt='合成', messages=[], schema={'type': 'object'},
        deadline=time.monotonic()+10, cancelled=lambda: bool(calls))
    assert result['error_code'] == 'cancelled' and len(calls) == 1
    assert processes[0].poll() is not None
