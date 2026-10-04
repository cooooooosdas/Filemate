"""激活已校验的判题代理代码与固定镜像，不赋予 Web 进程 Docker 权限。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

BASE = Path("/opt/filemate-judge")


def main() -> None:
    """先输出可检查计划，只有显式 activate 才修改系统服务。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if os.geteuid() != 0 or not source.is_relative_to(BASE / "releases") or source == BASE / "releases":
        raise SystemExit("需要 root 与独立的判题代码 release 目录")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        raise SystemExit("镜像必须为本地 sha256 内容ID")
    for item in [source, *source.rglob("*")]:
        if item.is_symlink() or item.stat().st_uid != 0 or item.stat().st_mode & 0o022:
            raise SystemExit("代理代码必须由 root 所有，禁止组写入或符号链接")
    unit = source / "scripts/judge/filemate-judge.service"
    if not unit.is_file() or not (source / "filemate/programming/linux_broker.py").is_file():
        raise SystemExit("代理包不完整")
    image = json.loads(subprocess.check_output(["/usr/bin/docker", "image", "inspect", args.image]))[0]
    if image["Id"] != args.image:
        raise SystemExit("镜像未安装")
    runtimes = json.loads(subprocess.check_output(["/usr/bin/docker", "info", "--format", "{{json .Runtimes}}"] ))
    if runtimes.get("filemate-runsc", {}).get("path") != str(BASE / "runsc"):
        raise SystemExit("专用 gVisor runtime 未配置")
    print(json.dumps({"source": str(source), "image": args.image, "runtime": "filemate-runsc",
                      "socket": "/run/filemate-judge/judge.sock", "concurrency": 1, "activate": args.activate}))
    if not args.activate:
        return
    environment = Path("/etc/filemate-judge.env")
    environment.write_text("FILEMATE_JUDGE_IMAGE=" + args.image + "\n", encoding="utf-8")
    environment.chmod(0o600)
    (BASE / "current.next").symlink_to(source, target_is_directory=True)
    (BASE / "current.next").replace(BASE / "current")
    shutil.copyfile(unit, "/etc/systemd/system/filemate-judge.service")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "filemate-judge.service"], check=True)
    subprocess.run(["systemctl", "restart", "filemate-judge.service"], check=True)


if __name__ == "__main__":
    main()
