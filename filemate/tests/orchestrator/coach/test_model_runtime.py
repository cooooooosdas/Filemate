# ruff: noqa: F811
"""The real private worker is exercised against an owned loopback provider."""

import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from filemate.llm_client import LLMConfig
from filemate.llm_client.bounded_call import BoundedLLMRunner

from .conftest import coach_module
from .test_requests import request, service, service_case  # noqa: F401


def test_full_upstream_messages_include_schema_inside_64k(coach_context):
    from filemate.study.orchestrator.coach.context import external_payload
    from filemate.study.orchestrator.coach.evidence import fact
    from filemate.study.orchestrator.coach.output import CoachModelOutput
    from filemate.study.orchestrator.coach.prompts import build_model_messages

    facts = [fact("source", str(i), {"i": i}, {"title": "𠀀" * 240}) for i in range(80)]
    coach_context.external_payload = external_payload(
        coach_context.input, coach_context.snapshot, coach_context.projection, facts
    )
    schema = CoachModelOutput.model_json_schema()
    instruction = "请仅返回符合以下 JSON Schema 的内容，不要额外解释：\n" + json.dumps(
        schema, ensure_ascii=False
    )
    full = [{"role": "system", "content": instruction}, *build_model_messages(coach_context)]
    assert len(json.dumps(full, ensure_ascii=False).encode("utf-8")) <= 65536


def test_service_defines_fixed_runtime_limits():
    settings = coach_module("settings")
    assert settings.HARD_TIMEOUT_SECONDS == 60
    assert settings.LEASE_SECONDS == 120
    assert settings.QUOTA_BUCKET == "learning-coach:v1"


@pytest.fixture
def coach_provider():
    calls, mode = [], ["success"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(json.loads(payload))
            code = int(mode[0]) if mode[0] in {"401", "429"} else 200
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                if mode[0] == "dribble":
                    for _ in range(200):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.05)
                else:
                    text = (
                        "bad-json"
                        if mode[0] == "bad_json"
                        else json.dumps({"explanations": [], "task_order": [], "new_actions": []})
                    )
                    if mode[0] == "duplicate":
                        text = (
                            '{"explanations":[],"task_order":[],"new_actions":[],"new_actions":[]}'
                        )
                    self.wfile.write(
                        json.dumps(
                            {
                                "choices": [{"message": {"content": text}}],
                                "usage": {
                                    "prompt_tokens": 20,
                                    "completion_tokens": 5,
                                    "total_tokens": 25,
                                },
                            }
                        ).encode()
                    )
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, calls, mode
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize("mode_name", ["success", "401", "429", "bad_json", "duplicate"])
def test_real_worker_has_bounded_calls_and_safe_failure(
    service_case, coach_provider, monkeypatch, mode_name
):
    server, calls, mode = coach_provider
    mode[0] = mode_name
    processes = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append((process, args, kwargs.get("env")))
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    config = LLMConfig(
        provider="openai_compatible",
        api_key="synthetic-coach-private-key",
        model="synthetic-coach-model",
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    view = service(service_case, config_factory=lambda: config).request(
        request(service_case, mode="llm")
    )
    assert 1 <= len(calls) <= 2 and all(call["max_tokens"] == 3500 for call in calls)
    assert all(
        len(json.dumps(call["messages"], ensure_ascii=False).encode("utf-8")) <= 65536
        for call in calls
    )
    assert processes and all(process.poll() is not None for process, _, _ in processes)
    assert all("synthetic-coach-private-key" not in repr((args, env)) for _, args, env in processes)
    assert view.model_status == ("succeeded" if mode_name == "success" else "failed")
    assert view.effective_mode == ("model" if mode_name == "success" else "rule_fallback")
    from filemate.runtime_governance import default_scope

    with default_scope().store._connection() as conn:
        rows = conn.execute("SELECT operation FROM ai_attempts").fetchall()
    assert len(rows) == len(calls) and all(row["operation"] == "learning.coach" for row in rows)


def test_real_service_deadline_reaps_worker(service_case, coach_provider, monkeypatch):
    server, calls, mode = coach_provider
    mode[0] = "dribble"
    processes, limits = [], []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)

    class ShortDeadline(BoundedLLMRunner):
        def run(self, config, scope, **kwargs):
            limits.append(kwargs["deadline"] - time.monotonic())
            kwargs["deadline"] = min(kwargs["deadline"], time.monotonic() + 3)
            return super().run(config, scope, **kwargs)

    config = LLMConfig(
        provider="openai_compatible",
        api_key="synthetic-only",
        model="synthetic-model",
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    started = time.monotonic()
    view = service(service_case, ShortDeadline(), lambda: config).request(
        request(service_case, mode="llm")
    )
    assert time.monotonic() - started < 6
    assert view.safe_error_code == "timeout" and view.effective_mode == "rule_fallback"
    assert 59 <= limits[0] <= 60 and 1 <= len(calls) <= 2
    assert processes and all(process.poll() is not None for process in processes)


def test_real_service_cancel_reaps_worker_and_never_replays(
    service_case, coach_provider, monkeypatch
):
    server, calls, mode = coach_provider
    mode[0] = "dribble"
    processes = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    config = LLMConfig(
        provider="openai_compatible",
        api_key="synthetic-only",
        model="synthetic-model",
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    api, body = (
        service(service_case, config_factory=lambda: config),
        request(service_case, mode="llm"),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api.request, body)
        deadline = time.monotonic() + 5
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls, "owned provider received no request"
        assert api.cancel(body.request_key).status == "cancelled"
        assert future.result(timeout=7).status == "cancelled"
    assert api.request(body).status == "cancelled"
    assert len(calls) == 1 and processes and all(p.poll() is not None for p in processes)
