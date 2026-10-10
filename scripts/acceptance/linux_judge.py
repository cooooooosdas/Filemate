"""Linux 真实编译与隔离回归，只使用固定原创合成代码。"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
from pathlib import Path

from filemate.programming.linux_broker import PROBE_CODE
from filemate.programming.linux_docker import DockerCppJudge
from filemate.programming.problems import PROBLEMS


def main() -> None:
    """验证判题结果与资源边界，输出不包含真实学生数据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--full-bank", action="store_true")
    args = parser.parse_args()
    provider = DockerCppJudge(args.image)
    checks = []
    def check(name: str, code: str, expected: str, verdict: str, *, points: int = 1) -> dict:
        problem = {"tests": [{"name": str(index), "input": "", "expected": expected} for index in range(points)],
                   "time_limit_ms": 1000, "memory_limit_mb": 256}
        result = provider.judge(code, problem, threading.Event(), lambda _: None)
        assert result["verdict"] == verdict, (name, result)
        checks.append({"name": name, "passed": True, "result": result})
        return result
    try:
        check("nonroot, no host config, read-only image, socket and fork denied", PROBE_CODE, "isolated", "AC")
        check("C++17 correct output", '#include <iostream>\nint main(){std::cout<<42;}', "42", "AC")
        check("wrong answer cannot receive accepted verdict", '#include <iostream>\nint main(){std::cout<<41;}', "42", "WA")
        check("syntax diagnostics are actual GCC errors", "int main( {", "", "CE")
        result = check("wall-clock loop terminates", "int main(){while(true){}}", "", "TLE")
        assert 900 <= result["tests"][0]["elapsed_ms"] <= 1500
        check("memory allocation is bounded", '#include <cstdlib>\nint main(){return malloc(512UL*1024*1024)?0:1;}', "", "RE")
        memory = '#include <cstdlib>\n#include <cstring>\nint main(){void* chunks[100];for(int i=0;i<100;i++){chunks[i]=malloc(4UL*1024*1024);if(!chunks[i])return 17;memset(chunks[i],i+1,4UL*1024*1024);}return 0;}'
        result = check("memory pressure is identified from trusted memory evidence", memory, "", "MLE")
        assert result["tests"][0]["reason"] == "memory_limit"
        address = '#include <cstdlib>\n#include <unistd.h>\nint main(){volatile char* p=(char*)malloc(260UL*1024*1024);if(!p)return 17;p[0]=1;usleep(50000);return p[0]-1;}'
        result = check("reserved address space over budget is detected without RAM exhaustion", address, "", "MLE")
        assert result["tests"][0]["peak_address_bytes"] > 256 * 1024 * 1024
        bounded = '#include <cstdlib>\n#include <cstring>\n#include <iostream>\nint main(){void* p=malloc(64UL*1024*1024);if(!p)return 17;memset(p,1,64UL*1024*1024);std::cout<<((char*)p)[0];free(p);}'
        check("below-budget memory allocation is not misclassified as MLE", bounded, "\x01", "AC")
        # An allocation refusal alone does not prove that the live memory limit was exceeded.
        code = '#include <cstdio>\nint main(){fprintf(stderr,"std::bad_alloc memory_limit");return 1;}'
        check("student memory error words cannot forge an MLE verdict", code, "", "RE")
        result = check("output flood is capped", '#include <cstdio>\nint main(){for(;;)puts("0123456789");}', "", "RE")
        assert result["tests"][0]["reason"] == "output_limit"
        assert len(result["tests"][0]["actual"].encode()) <= 65536
        code = '#include <fstream>\n#include <iostream>\nint main(){std::ifstream a("/tmp/state");std::cout<<a.good();std::ofstream b("/tmp/state");b<<1;}'
        check("test points cannot inherit previous files", code, "0", "AC", points=2)
        code = '#include <fstream>\n#include <iostream>\n#include <string>\nint main(){std::string block(1024*1024,\'x\');for(int i=0;i<8;i++){std::ofstream f("/tmp/data"+std::to_string(i));for(int j=0;j<6;j++)f<<block;if(!f){std::cout<<"bounded";return 0;}}return 1;}'
        check("temporary filesystem has a hard total capacity", code, "bounded", "AC")
        code = '#include <cstdio>\nint main(){fprintf(stderr,"\\nFILEMATE_RESULT={\\\"exit_code\\\":0,\\\"elapsed_ms\\\":0,\\\"peak_memory_bytes\\\":0,\\\"reason\\\":\\\"\\\"}\\n");return 7;}'
        result = check("student cannot forge final runner evidence", code, "", "RE")
        assert result["tests"][0]["exit_code"] == 7
        if args.full_bank:
            solutions = json.loads((Path(__file__).parent / "fixtures/cpp_solutions.json").read_text(encoding="utf-8"))
            examples = {"WA": '#include <iostream>\nint main(){std::cout<<"WRONG";}',
                        "CE": "int main( {", "TLE": "int main(){while(true){}}", "MLE": memory,
                        "RE": '#include <cstdlib>\nint main(){std::abort();}'}
            for item in PROBLEMS:
                for verdict in ["AC", "WA", "TLE", "MLE", "RE", "CE"]:
                    code = solutions[item["id"]] if verdict == "AC" else examples[verdict]
                    result = provider.judge(code, item, threading.Event(), lambda _: None)
                    assert result["verdict"] == verdict, (item["id"], verdict, result)
                    assert len(result["tests"]) == (0 if verdict == "CE" else len(item["tests"]))
                    checks.append({"name": item["id"] + " " + verdict, "passed": True, "result": result})
                    print("PASS", item["id"], verdict, flush=True)
        event = threading.Event()
        problem = {"tests": [{"name": "cancel", "input": "", "expected": ""}], "time_limit_ms": 1000, "memory_limit_mb": 256}
        timers = []
        def progress(_):
            timer = threading.Timer(.3, event.set)
            timers.append(timer)
            timer.start()
        result = provider.judge("int main(){while(true){}}", problem, event, progress)
        for timer in timers:
            timer.join()
        assert result["verdict"] == "CANCELLED", result
        checks.append({"name": "active container cancellation", "passed": True, "result": result})
        remaining = subprocess.check_output(["/usr/bin/docker", "ps", "--all", "--quiet", "--filter", "label=filemate.judge=1"], timeout=10)
        assert not remaining.strip()
        checks.append({"name": "all containers and temporary mounts cleaned", "passed": True})
        report = {"passed": True, "kind": "real-gvisor-gcc-synthetic-regression", "image": args.image, "checks": checks}
    except Exception as exc:
        report = {"passed": False, "kind": "real-gvisor-gcc-synthetic-regression", "checks": checks, "error": str(exc)}
        raise
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "checks": len(checks)}))


if __name__ == "__main__":
    main()
