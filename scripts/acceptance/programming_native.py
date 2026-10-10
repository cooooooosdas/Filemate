"""用原创输入验证真实 C++ 评测与 Windows 隔离边界。"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from filemate.programming.judge import WindowsCppJudge
from filemate.programming.problems import PROBLEMS
from filemate.programming.service import status
from filemate.programming.toolchain import prepare_toolchain
from filemate.programming.toolchain import compiler_environment
from filemate.programming.windows_sandbox import run_isolated


def main() -> int:
    """保留各场景证据并以退出码报告验收失败。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="_working/v2-3/native")
    parser.add_argument("--security-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = Path(args.out).resolve()
    if not out.is_relative_to(root / "_working"):
        raise ValueError("验收输出必须位于项目 _working")
    out.mkdir(parents=True, exist_ok=True)
    prepare_toolchain()
    assert status(force=True)["ready"], "完整隔离自检未通过"
    judge = WindowsCppJudge()
    solutions = json.loads((Path(__file__).parent / "fixtures/cpp_solutions.json").read_text(encoding="utf-8"))
    results = []

    def check(name, run):
        print("RUN", name, flush=True)
        started = time.monotonic()
        try:
            evidence = run()
            results.append({"name": name, "kind": "real_windows_sandbox", "passed": True,
                            "elapsed_seconds": round(time.monotonic() - started, 2), "evidence": evidence})
            print("PASS", name, flush=True)
        except Exception as exc:
            results.append({"name": name, "kind": "real_windows_sandbox", "passed": False,
                            "error": f"{type(exc).__name__}: {exc}"})
            print("FAIL", name, str(exc), flush=True)
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    def evaluate(code, problem, verdict):
        result = judge.judge(code, problem, threading.Event(), lambda _: None)
        assert result["verdict"] == verdict, result
        if verdict != "CE":
            assert len(result["tests"]) == len(problem["tests"])
        if verdict == "AC":
            assert result["passed"] == result["total"] and result["score"] == 100
        return result

    codes = {
        "WA": '#include <iostream>\nint main(){std::cout<<"WRONG";}',
        "TLE": 'int main(){volatile unsigned long long i=0;for(;;)++i;}',
        "RE": '#include <cstdlib>\nint main(){std::abort();}',
        "CE": 'int main( { missing syntax',
        "MLE": '#include <cstdlib>\nint main(){void* p=malloc(512UL*1024*1024);return p?0:1;}',
    }
    for problem in ([] if args.security_only else PROBLEMS):
        for verdict in ["AC", "WA", "TLE", "MLE", "RE", "CE"]:
            code = solutions[problem["id"]] if verdict == "AC" else codes[verdict]
            check(problem["id"] + " " + verdict,
                  lambda c=code, p=problem, v=verdict: evaluate(c, p, v))

    probe = {"tests": [{"name": "隔离探针", "input": "", "expected": "DENIED"}],
             "time_limit_ms": 1000, "memory_limit_mb": 256}
    private = out / "host-private.h"
    private.write_text("#error FILEMATE_SYNTHETIC_CANARY_MUST_NOT_LEAK\n", encoding="utf-8")
    escaped = json.dumps(private.as_posix())
    write_target = out / "forbidden-write.txt"
    os.environ["FILEMATE_SANDBOX_CANARY"] = "synthetic-secret-never-in-child"
    filesystem = ('#include <iostream>\n#include <fstream>\n#include <cstdlib>\n'
                  f'int main(){{std::ifstream r({escaped});std::ofstream w({json.dumps(write_target.as_posix())});'
                  'bool blocked=!r.good()&&!w.good()&&std::getenv("FILEMATE_SANDBOX_CANARY")==nullptr;'
                  'std::cout<<(blocked?"DENIED":"LEAK");}')
    check("runtime denies private host read/write and inherited environment",
          lambda: evaluate(filesystem, probe, "AC"))
    assert not write_target.exists()

    def compile_include():
        result = evaluate(f'#include {escaped}\nint main(){{}}', probe, "CE")
        assert "FILEMATE_SYNTHETIC_CANARY" not in result["compile_log"]
        assert "C1083" in result["compile_log"]
        return result
    check("compiler cannot include private host files", compile_include)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    network = ('#include <winsock2.h>\n#include <iostream>\n#pragma comment(lib,"ws2_32.lib")\n'
               'int main(){WSADATA w;int init=WSAStartup(MAKEWORD(2,2),&w);std::cout<<"init="<<init<<std::endl;'
               'SOCKET s=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);u_long nonblocking=1;ioctlsocket(s,FIONBIO,&nonblocking);'
               f'sockaddr_in a{{}};a.sin_family=AF_INET;a.sin_port=htons({port});a.sin_addr.s_addr=htonl(0x7f000001);'
               'int rc=connect(s,(sockaddr*)&a,sizeof(a));int e=WSAGetLastError();'
               'std::cout<<"rc="<<rc<<" error="<<e<<std::endl;'
               'fd_set f;FD_ZERO(&f);FD_SET(s,&f);timeval wait{0,300000};int connected=0;'
               'if(rc==0)connected=1;else if(e==WSAEWOULDBLOCK&&select(0,0,&f,0,&wait)>0){int err=0,len=sizeof(err);'
               'getsockopt(s,SOL_SOCKET,SO_ERROR,(char*)&err,&len);if(err==0)connected=1;}'
               'std::cout<<"connected="<<connected;closesocket(s);WSACleanup();}')
    def network_denial():
        result = judge.judge(network, probe, threading.Event(), lambda _: None)
        actual = result["tests"][0]["actual"]
        assert "rc=-1 error=" in actual and actual.endswith("connected=0"), result
        # LPAC 也可在创建 socket 时阻止 Winsock 提供程序初始化；不能误称已发起连接。
        result["network_probe"] = actual
        return result
    check("loopback TCP connection cannot be established", network_denial)
    def compiler_network_denial():
        with tempfile.TemporaryDirectory(prefix="network-", dir=judge.root.parent / "cpp-runs") as folder:
            work = Path(folder)
            compiled = judge._compile(network, work, threading.Event())
            assert compiled.exit_code == 0
            result = run_isolated(work / "main.exe", [], work,
                                  environment=compiler_environment(judge.root, work),
                                  least_privileged=False, timeout=5)
            assert result.exit_code == 0 and "rc=-1 error=" in result.stdout and result.stdout.endswith("connected=0"), result
            return {"stdout": result.stdout, "elapsed_ms": result.elapsed_ms,
                    "kind": "same_no_capability_appcontainer_as_compiler"}
    check("compiler AppContainer denies a real Winsock connection", compiler_network_denial)
    listener.close()
    child = ('#include <windows.h>\n#include <iostream>\nint main(){wchar_t path[32768];'
             'GetModuleFileNameW(0,path,32768);STARTUPINFOW s{};s.cb=sizeof(s);PROCESS_INFORMATION p{};'
             'bool ok=CreateProcessW(path,nullptr,0,0,FALSE,CREATE_NO_WINDOW,0,0,&s,&p);'
             'if(ok){TerminateProcess(p.hProcess,0);CloseHandle(p.hThread);CloseHandle(p.hProcess);}'
             'std::cout<<(ok?"LEAK":"DENIED");}')
    check("child process creation denied", lambda: evaluate(child, probe, "AC"))
    memory = '#include <new>\nint main(){auto p=new char[512*1024*1024];p[0]=1;return p[0]-1;}'
    check("memory cap reports kernel-confirmed 512MB allocation violation", lambda: evaluate(memory, probe, "MLE"))
    output = '#include <iostream>\nint main(){for(;;)std::cout<<"012345678901234567890123456789";}'
    def output_cap():
        result = evaluate(output, probe, "RE")
        assert result["tests"][0]["reason"] == "output_limit"
        assert len(result["tests"][0]["actual"].encode()) <= 65536
        return result
    check("stdout flood stopped and captured output bounded", output_cap)
    disk = '#include <fstream>\n#include <string>\nint main(){std::ofstream f("flood",std::ios::binary);std::string s(65536,\'x\');for(;;){f.write(s.data(),s.size());f.flush();}}'
    def disk_cap():
        result = evaluate(disk, probe, "RE")
        assert result["tests"][0]["reason"] == "file_output_limit"
        return result
    check("filesystem write flood stopped by job I/O guard", disk_cap)
    def cancellation():
        signal = threading.Event()
        def progress(result):
            signal.set()
        result = judge.judge(codes["TLE"], probe, signal, progress)
        assert result["verdict"] == "CANCELLED"
        assert result["tests"] == []
        return result
    check("cancellation stops before executing testpoints", cancellation)
    os.environ.pop("FILEMATE_SANDBOX_CANARY", None)
    summary = {"passed": sum(item["passed"] for item in results), "total": len(results),
               "kind": "synthetic_regression_with_real_compiler_and_sandbox", "results": results}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {summary['passed']}/{summary['total']}", flush=True)
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
