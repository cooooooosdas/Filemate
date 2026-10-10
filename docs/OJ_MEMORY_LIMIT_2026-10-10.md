# 判题内存超限识别修复

本卡处理用户FEATURE07.3中的MLE缺口，沿用现有编译器、题库、Artifact和判题代理。没有数据库迁移，也没有用模型代替程序正确性。2026-10-10当前为候选验证，网站是否更新须以随后发布回执和 `/release.json` 为准；先前 `ae9623cb` 仍是上一轮已上线版本。

## 触发与修复

旧版将沙箱的 `memory_limit` 和普通异常一起归为RE。Linux代理已有Docker `OOMKilled` 证据却未输出独立MLE；Windows只设置Job内存上限，没有读取内核超限通知。新版本使用受信任资源证据识别MLE，并同步逐点判定、错题投影、每周统计、岗位证据和前端有效状态，避免MLE结果被漏计或导致本地复盘字典异常。

Windows在恢复挂起进程前，把Job与专用I/O完成端口关联。只采用本Job的 `JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT` / `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT`；学生不继承端口。取消/输出限制及CPU超时继续保持其原状态，端口与Job在所有退出路径释放。通知未到达不能证明未超限，未知原因仍保守显示RE，不由 `std::bad_alloc` 或学生stderr推断MLE。参见[Microsoft完成端口合同](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_associate_completion_port)及[Job通知交付边界](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。

Linux继续固定gVisor镜像、无网络、只读根目录、单学生进程、CPU/输出/文件限制。声明的学生地址空间预算仍默认256MiB；运行器每约2ms读取 `/proc/<pid>/statm` 的首个数字，保存观察到的地址空间峰值，超预算则由父进程终止并报告 `memory_limit`。硬地址空间上限额外保留16MiB检测余量，不能称完全等同于原RLIMIT_AS。容器RAM/swap上限为学生预算+128MiB运行时预算，默认384MiB、禁止额外swap，供共享cgroup的gVisor Sentry及临时文件使用。代理并发仍为1，最大容器预算等同于既有编译容器384MiB，不开放客户端自定资源。`limits`明确报告memory_mb、container_memory_mb及address_hard_limit_mb，不能把总容器预算说成学生上限。内存读数连续不可用约20ms时失败关闭，短暂进程退出空计数不冒充基础设施失败。父进程证据、seccomp与原始日志防伪规则保持；Docker报告OOMKilled也为MLE依据。

现役gVisor未提供所需VmPeak值，首次地址预留案例被误标AC，原失败保留；改用无进程名/用户文本的statm数字。初次过严空计数处理又使短暂退出被误判为环境失败，保留该失败并增加有界重试。全题库又出现共享cgroup提前OOM和容器清理超时，保留该失败，增加上述明确运行时预算及“清理超时/异常也隔离停止”的保护；清理异常路径仍关闭客户端进程和管道，不能继续创建任务。核对发生超时的自有候选容器已不存在，没有删除其他容器。计数是沙箱观察值；[gVisor说明内部内存统计为近似](https://gvisor.dev/docs/architecture_guide/resources/)，不将RSS、地址空间、Job提交内存混为同一指标。`tests[].peak_address_bytes` 为新增可选字段，旧记录和旧镜像缺失时保持0/未观测；原 `peak_memory_bytes` 不填造假的预算值。

512MiB分配因硬上限返回null，但没有可靠超限观察时仍为RE；退出码137、打印“内存不足”或bad_alloc也不能单独证明MLE。原RE历史不重写，新版六状态的真实证据需分别核验。

## 验收与发布门禁

- Windows真实8题×6状态及9隔离探针：57/57通过，包含3简单/3中等/2困难、MLE、原5状态、无网络/宿主文件/子进程、输出/文件限制及取消。不是模型或ProcessResult模拟。
- 单元回归新增清理异常路径后66通过、1个仅Linux分支在Windows跳过；其中模拟ProcessResult的测试只证明判定与持久链合同，不冒充原生执行。第一次新测试误用了不存在的withdraw操作，改为现役undo/restore后通过。
- Linux最终候选E真实64/64通过，包含8题×6状态、地址预留超限/64MiB正常分配、伪造错误文字/运行器末行、文件/进程/网络、输出、取消和清理。原固定旧镜像首次内存案例仍为RE；新候选依次保留构建和观测失败。旧基础镜像按本地SHA验证，断网重编译运行器，不下载新依赖。当前镜像`sha256:69d6644ba8f5aa4eb5b0ca5c2d0cc81e4fd5a05adb030d0c5ff2467bb2f75e56`，尚未激活线上代理。精简证据见[原生验收](audits/oj-memory-2026-10-10/native-summary.json)。
- 默认 `scripts/verify.ps1 -IsolateFrontend` 完整退出0，952后端通过、20跳过、5排除、3条依赖警告；46前端及类型/构建/体积通过。该轮启动早于最终Linux清理和联合部署补丁，随后补丁另用定向回归、Linux实机及当前提交CI验证，不把952当作后续改动全部覆盖。
- 最后核对发现Docker删除与inspect均失败不能证明容器不存在；改为要求成功的精确名称列表查询且结果为空，否则隔离停止。候选F复用已经验证、runner.c字节相同的E固定镜像，实际64/64全题库复验通过；E的64/64原始快照不改写为F。最终定向112通过、2个Linux平台相关跳过；8ddd5bad的Linux CI 38019934341为970后端通过、18跳过、5排除、3警告，46前端通过，包含联合回退故障测试。随后只补齐前端本周MLE统计显示，仍需取得该显示补丁的类型/构建/当前提交CI。
- `scripts/deploy_existing.py` 增加可选且必须配对的 `--judge-source` / `--judge-image`，阶段预检比较API/代理关键源码字节并检查固定镜像安装计划。激活先维护停写及完整备份恢复演练，随后切换代理/API/网页，隔离自检不通过或安装失败则恢复两项服务的旧代码与原配置。合成回归覆盖两种故障，LinuxCI另验证该平台分支。
- 本卡发布须同时更新API与判题代理，避免旧API本地复盘不认识MLE。原代理/镜像/配置保留用于代码回滚，数据不降级、旧RE不重新归类；保留旧数据不会将历史RE自动改成MLE。
- 初次预部署在字节校验处拒绝Windows CRLF工作副本与Git LF包混用，尚未停写或切换。保留失败目录与日志，改为API/代理均取同一Git规范化包，并在固定镜像中重新编译LF运行器，与已验收E运行器实际cmp逐字节相同；未把源码换行相同说成原始字节相同。第二份独立目录预检、锁定依赖安装、pip check、临时数据库API及保留260个旧hash资源通过，保持未激活；最终发布以回执为准。

原始完整需求及剩余缺口见[FEATURE07–13账本](FEATURE_07_13_REQUIREMENTS_LEDGER.md)。本卡通过不表示下一题推荐、其他语言、跨次面试记忆、简历PDF/DOCX、完整学期复盘、预算等也完成。
