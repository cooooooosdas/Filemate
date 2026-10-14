# 小规格生产主机资源防护

2026-10-15 已在现役 NPM/systemd 主机应用；这组文件不改变 Web/API/Judge 业务版本、路由、环境变量或数据库。故障复发的根因尚未闭合，不能把资源上限当成故障根因证明。

`filemate-api-resources.conf` 安装到 `/etc/systemd/system/filemate-api.service.d/40-resources.conf`：CPU 150%（两核主机上的 1.5 核）、内存软阈值 512 MiB、硬上限 768 MiB、任务上限 128。任务数包括线程；软阈值效果受 cgroup 版本影响。达到硬上限可能由内核终止 API，原有 `Restart=on-failure` 接续重启，在途请求可能失败。这不是无限吞吐或零停机承诺。独立 Docker/gVisor 判题容器继续执行原有单槽和资源限制，不属于 API cgroup。

`resource_recorder.py` 安装到 `/opt/filemate-ops/resource_recorder.py`，配套 systemd unit 安装到 `/etc/systemd/system/filemate-resource-recorder.service`。事先创建 root:root 的 `/var/log/filemate-resources`（0700），脚本和 unit 为 root:root 0644。记录每 15 秒一次，仅含 `/proc` 的 CPU/内存/虚拟内存计数和前 15 个 CPU、前 15 个 RSS 进程的并集，含 PID、启动时刻、进程名、状态及线程数。首个采样及新进程的 CPU 为 `null`；按 PID 和启动时刻共同识别，防止 PID 复用产生错误峰值。

不读取命令行、环境变量、Cookie、文件正文、数据库记录或网络端点；不监听端口，不发送外部请求，不重启业务服务。日志为 root 0600，当前文件及两份轮转文件各约 4 MiB，最多多出一条记录；不要求内核支持 PSI。记录器自身 CPU 5%、内存 48 MiB、任务数 8，并以 systemd 限制写入路径及网络地址族。异常只记录错误类型，不输出底层内容。

## 安装与更新

只由现有主机管理员通过原有管理权限部署。先预览目标文件、现役资源属性、发布链接，备份将修改的文件；不要直接覆盖未知配置。使用校验 SHA-256 的来源文件，原子替换脚本；通过 `systemd-analyze verify` 验证 unit 后再 `daemon-reload`。

首次添加防护时，以下命令可即时调整现役 API，无需重启进程；相同属性还必须写入持久 drop-in 才能跨重启保留：

```bash
systemctl set-property --runtime filemate-api CPUAccounting=yes MemoryAccounting=yes CPUQuota=150% MemoryHigh=512M MemoryMax=768M TasksMax=128
systemctl enable --now filemate-resource-recorder
systemctl show filemate-api --property=CPUQuotaPerSecUSec,MemoryHigh,MemoryMax,TasksMax
```

随后核对记录文件的更新时间、权限及服务状态，并验收公网 `/api/ready`、注册登录、上传、真实 C++ 判题与语音。只看到 recorder 为 active 不足以证明有新记录；磁盘写入故障会导致记录缺失。不要用生产恶意内存负载来验证上限。

## 本次回滚

原属性保存在 `/var/backups/filemate/incident-ops-20261014T163114Z/resources-before.txt`，源码指纹及操作结果同目录。此前没有本次两个 unit/drop-in 文件。需要回滚时先核对文件与本批内容一致，再移除本次 drop-in、停用记录器并执行 daemon-reload，保留日志和代码备查；不要移除其他 drop-in。

本批变更前的 API 属性为 CPUAccounting=no、MemoryAccounting=yes、CPUQuota=infinity、MemoryHigh=infinity、MemoryMax=infinity、TasksMax=11828。只有在确认仍应恢复这些原值后，才能使用 `systemctl set-property --runtime filemate-api` 恢复；后来管理员新增的限制应保留。正常业务数据不需要恢复、覆盖或迁移。已开放新写入后，禁止用历史数据库快照覆盖当前数据。
