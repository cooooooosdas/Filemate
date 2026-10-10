"""Linux 判题代理合同、取消与平台降级回归。"""

from __future__ import annotations

import io
import json
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from filemate.programming import linux_broker, service
from filemate.programming.feedback import local_feedback
from filemate.programming.linux_broker import validate_request
from filemate.programming.linux_docker import DockerCppJudge, container_arguments
from filemate.programming.windows_sandbox import ProcessResult, SandboxUnavailable


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
    assert "--memory=384m" in arguments and "--memory-swap=384m" in arguments
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


@pytest.mark.parametrize("reason,exit_code,stderr,verdict", [
    ("memory_limit", 137, "", "MLE"),
    ("timeout", 137, "", "TLE"),
    ("", 137, "std::bad_alloc memory_limit", "RE"),
    ("", 0, "std::bad_alloc memory_limit", "AC"),
])
def test_linux_judge_distinguishes_resource_evidence_from_student_output(
    tmp_path, monkeypatch, reason, exit_code, stderr, verdict,
):
    monkeypatch.setattr("filemate.programming.linux_docker.JOBS", tmp_path)
    monkeypatch.setattr("filemate.programming.linux_docker.command", lambda *a, **kw: "")
    provider = DockerCppJudge("sha256:" + "a" * 64)

    def run(directory, *, compile_code, **kwargs):
        if compile_code:
            (directory / "main").write_bytes(b"\x7fELFsynthetic_test_binary")
            return ProcessResult(0, "", "", 1, 0)
        return ProcessResult(exit_code, "answer", stderr, 9, 1234, reason)

    monkeypatch.setattr(provider, "_run", run)
    problem = {"tests": [{"name": "memory", "input": "", "expected": "answer"}],
               "time_limit_ms": 1000, "memory_limit_mb": 256}
    result = provider.judge("int main(){}", problem, threading.Event(), lambda _: None)
    assert result["verdict"] == result["tests"][0]["verdict"] == verdict
    assert result["tests"][0]["reason"] == reason
    assert result["passed"] == int(verdict == "AC")


def test_cleanup_timeout_quarantines_provider_and_always_releases_client(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker rm", 10)

    class Client:
        stdin, stdout, stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            assert timeout == 5

    monkeypatch.setattr("filemate.programming.linux_docker.subprocess.run", run)
    provider, process = DockerCppJudge("sha256:" + "a" * 64), Client()
    with pytest.raises(SandboxUnavailable, match="停止接收"):
        provider._cleanup("filemate-judge-synthetic", process)
    assert provider.quarantined and process.killed
    assert all(s.closed for s in (process.stdin, process.stdout, process.stderr))
    with pytest.raises(SandboxUnavailable, match="管理员检查"):
        provider.judge("int main(){}", {}, threading.Event(), lambda _: None)


@pytest.mark.parametrize("exit_code,container_id,unavailable", [
    (1, b"", True), (0, b"synthetic-live-container\n", True), (0, b"", False),
])
def test_failed_removal_requires_successful_absence_evidence(monkeypatch, exit_code, container_id, unavailable):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if arguments[1] == "rm":
            return subprocess.CompletedProcess(arguments, 1)
        assert arguments[1:4] == ["container", "ls", "--all"]
        assert "name=^/filemate-judge-synthetic$" in arguments
        return subprocess.CompletedProcess(arguments, exit_code, stdout=container_id)

    monkeypatch.setattr("filemate.programming.linux_docker.subprocess.run", run)
    provider = DockerCppJudge("sha256:" + "a" * 64)
    if unavailable:
        with pytest.raises(SandboxUnavailable, match="停止接收"):
            provider._cleanup("filemate-judge-synthetic", None)
    else:
        provider._cleanup("filemate-judge-synthetic", None)
    assert provider.quarantined is unavailable and len(calls) == 2
