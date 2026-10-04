"""Linux 判题代理合同、取消与平台降级回归。"""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from filemate.programming import linux_broker, service
from filemate.programming.feedback import local_feedback
from filemate.programming.linux_broker import validate_request
from filemate.programming.linux_docker import container_arguments
from filemate.programming.windows_sandbox import SandboxUnavailable


@pytest.mark.parametrize("value", [[], {"operation": "shell", "command": "id"},
                                 {"operation": "health", "image": "attacker"},
                                 {"operation": "judge", "problem_id": "array-sum", "code": " "},
                                 {"operation": "judge", "problem_id": "../secret", "code": "int main(){}"},
                                 {"operation": "judge", "problem_id": "array-sum", "code": "\x00"},
                                 {"operation": "judge", "problem_id": "array-sum", "code": "学" * 33334}])
def test_broker_rejects_commands_paths_unknown_problems_and_oversized_code(value):
    with pytest.raises((ValueError, TypeError)):
        validate_request(value)


def test_request_does_not_accept_caller_chosen_tests_or_resources():
    request = {"operation": "judge", "problem_id": "array-sum", "code": "int main(){}"}
    assert validate_request(request) == request
    with pytest.raises(ValueError):
        validate_request({**request, "tests": [], "memory_mb": 99999})
    image = "sha256:" + "a" * 64
    arguments = container_arguments(image, "filemate-judge-test", Path("/trusted/job"), compile_code=False)
    assert "--network=none" in arguments and "--read-only" in arguments and "--cap-drop=ALL" in arguments
    assert "--memory=256m" in arguments and "--memory-swap=256m" in arguments
    assert arguments[arguments.index("--runtime") + 1] == "filemate-runsc"
    assert arguments[-3:] == ["/usr/local/bin/filemate-runner", "1000", "256"]
    with pytest.raises(SandboxUnavailable):
        container_arguments("gcc:latest", "name", Path("/job"), compile_code=True)


@pytest.mark.parametrize("disconnect", [False, True])
def test_cancel_or_client_disconnect_cancels_job_and_releases_broker_slot(monkeypatch, disconnect):
    started, cancelled = threading.Event(), threading.Event()
    class Provider:
        def judge(self, code, problem, cancel, progress):
            started.set()
            assert cancel.wait(3)
            cancelled.set()
            return {"verdict": "CANCELLED"}
    monkeypatch.setattr(linux_broker, "health", lambda *_: {"ready": True})
    client, server = socket.socketpair()
    assert linux_broker._CLIENTS.acquire(blocking=False)
    worker = threading.Thread(target=linux_broker.serve_client, args=(server, Provider()))
    worker.start()
    client.sendall(json.dumps({"operation": "judge", "problem_id": "array-sum", "code": "int main(){}"}).encode() + b"\n")
    assert started.wait(3)
    if disconnect:
        client.close()
    else:
        client.sendall(b'{"cancel":true}\n')
        assert json.loads(client.makefile("rb").readline())["result"]["verdict"] == "CANCELLED"
        client.close()
    worker.join(3)
    assert cancelled.is_set() and not worker.is_alive()
    assert linux_broker._SLOT.acquire(blocking=False)
    linux_broker._SLOT.release()


def test_missing_linux_broker_disables_judging_without_host_execution(monkeypatch):
    if service.os.name == "nt":
        pytest.skip("仅验证 Linux 平台分支")
    class Absent:
        def health(self):
            raise SandboxUnavailable("sensitive infrastructure exception")
    monkeypatch.setattr(service, "LinuxCppJudge", Absent)
    state = service.status(force=True)
    assert not state["ready"] and not state["network_isolation_ready"] and not state["setup_supported"]
    assert "sensitive" not in json.dumps(state)


def test_gcc_diagnostics_keep_verified_source_line_numbers():
    feedback = local_feedback({"code": "int main(){\n return missing;\n}\n", "problem_id": "array-sum",
                               "result": {"compile_log": "main.cpp:2:9: error: missing was not declared\n"
                                                         "main.cpp:99:1: error: outside source\n", "tests": []}})
    assert [issue["line"] for issue in feedback["issues"]] == [2]
