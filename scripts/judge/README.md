# Linux C++17 判题部署

Linux 网站通过独立 root 判题代理与 gVisor `runsc` 执行 C++。Web 的 `filemate` 用户仅能访问 `/run/filemate-judge/judge.sock`，不加入 Docker 组，也不获得 Docker socket。代理只接受内置题目ID及100 KB以内的代码，不能接受命令、路径、镜像、测试点或资源配置。

部署前按照[gVisor官方安装文档](https://gvisor.dev/docs/user_guide/install/)下载官方 release 并校验 SHA512，将完整运行时（runsc及同目录gvisor-bin配套文件）安装在 `/opt/filemate-judge/`；在 Docker 中增加 `filemate-runsc`（`--platform=systrap`），保留其他配置及默认 runtime。Docker 支持[通过 HUP 重载 runtimes](https://docs.docker.com/reference/cli/dockerd/#configuration-reload-behavior)，无需重启现有网站容器。

用本目录的 Dockerfile 和 runner.c 构建镜像；基础镜像固定内容摘要，GCC固定版本。将镜像的本地 `sha256:` ID传给安装器，判题时禁止拉取镜像，不使用可变标签。代理代码包包含 `filemate/__init__.py`、`filemate/programming/` 与本目录，放在 `/opt/filemate-judge/releases/<release>`，全部 root 所有，禁止组写入和符号链接。

```bash
python3.11 scripts/judge/install.py --source /opt/filemate-judge/releases/<release> --image sha256:<image-id>
python3.11 scripts/judge/install.py --source /opt/filemate-judge/releases/<release> --image sha256:<image-id> --activate
```

API也变更判定合同（如新增MLE）时，先将同提交代理放到独立root目录，再用 `scripts/deploy_existing.py stage/activate` 的 `--judge-source /opt/filemate-judge/releases/<release> --judge-image sha256:<image-id>` 联合发布。阶段预检检查API/代理关键代码字节相同及安装计划；激活先维护停写、完整数据备份/恢复演练，随后切换代理、API和静态文件。隔离自检不通过或安装失败时，维护期间恢复两项服务的旧代码与原配置；不以旧数据库覆盖新写入。仅更新API时可以不传这两个参数。不要在旧API运行时单独切换新增判定的代理。

安装后以 `filemate` 用户查询 `/api/programming/status`，必须真实自检通过：非root身份、不能读取宿主配置、不能修改镜像根目录、网络与派生进程调用被拒绝。自检缓存10分钟，失败关闭评测；不退回原生 Docker 或宿主进程。可通过 `FILEMATE_JUDGE_SOCKET` 配置客户端 socket 路径；代理地址固定在专用 `/run/filemate-judge/` 中。

编译容器384 MB、单CPU、30秒编译上限；编译文件使用总量64 MB临时内存盘。测试点由内置题库控制，运行器在容器内计时，排除容器启动开销；默认1秒、256 MB学生地址空间预算，另有16 MB硬保护检测余量；容器内存/禁止swap上限包含128 MB gVisor运行时预算，默认384 MB。单个学生进程（禁止 fork/clone/线程）、64 KB合计输出、16 MB临时文件系统、8 MB单文件上限。镜像只读、能力全部移除、禁止网络与提权；每个测试点独立容器，仅挂载该次二进制。取消或断开代理连接会终止并删除容器；清理失败会关闭代理评测并释放客户端管道，需管理员检查后重启。Docker宿主PID上限64，包含gVisor自身线程；学生的单进程限制另由运行器seccomp执行。代理一次处理一份代码，当前编译/运行最大容器预算同为384 MB，避免小内存服务器同时编译。

编译器和实际测试点决定 AC/WA/CE/TLE/MLE/RE 及得分；AI仅提供用户授权后的参考复盘，原判定、原代码及证据不被模型覆盖。MLE仅来自运行器实际内存观察或Docker OOMKilled，不采用学生打印内容或仅凭退出码137。运行器约2ms观察statm地址空间，超出题目声明预算终止；硬地址空间保护预留16MiB检测余量。连续约20ms无法读取活进程计数则失败关闭，退出过渡允许有界重试；地址空间观察峰值独立保存，旧镜像/旧记录未观测时不造数。RSS为运行器的系统观测值，不作为学习成效指标。完整边界见[内存识别修复](../../docs/OJ_MEMORY_LIMIT_2026-10-10.md)。gVisor与资源限制需要持续维护，不能据此宣称消除全部容器攻击风险。
