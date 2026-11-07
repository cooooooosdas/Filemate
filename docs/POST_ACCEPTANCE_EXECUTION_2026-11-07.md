# 用户验收后执行记录（2026-11-07）

用户于 2026-11-07 明确给出 D 阶段验收确认，并要求部署生产、开启 D／试行开关、启动 E 级真人实验、运行待补证据、关闭未关闭项。本文件如实记录**实际执行了什么、什么客观无法执行、为什么**，不把准备工作记作上线结果。

## 结论速览

| 请求 | 实际状态 | 原因 |
|---|---|---|
| 部署生产 | **未执行** | 部署脚本须在服务器本机 root 运行；本机无生产主机、无 `.env.production`；公网健康端点当前不可达 |
| 开启生产 D／试行开关 | **未执行** | 同上；开关属于生产配置变更，不能由本地会话代改 |
| 启动 E 级真人实验 | **协议与工程准备完成，真人数据未采集** | 需真实参与者、知情同意、随机分组与随访；AI 不能代跑或伪造 |
| 运行待补证据 | **部分真实执行**（真机矩阵、容量复测） | 真实供应商调用缺密钥、干净 Linux CI / 旧运行时缺环境，按规则不得伪造 |
| 关闭未关闭项（P2） | **仍未关闭** | 两次真实复测仍超 500ms 目标，不能靠改阈值或改文档假关闭 |

## 真实执行的证据

证据根：`D:/FileMate-Project/_working/final-trial-20261106/`，汇总见 `acceptance-evidence-2026-11-07.json`。

### 真实 Edge 交互矩阵（Microsoft Edge 156，安装版二进制）

在独占回环合成夹具中开启 `FILEMATE_ENABLE_TRIAL_WORKSPACE=1` / `VITE_ENABLE_TRIAL_WORKSPACE=true`（仅本地，非生产），供应商调用被阻断、数据全部为合成：

- **矩阵 11 项 / 10 通过**：trial 与 coach capabilities 均 enabled；320/390/1024/1440px 均无横向溢出、正文 17px；四主题表面可应用；键盘 Tab 可达交互控件；原成长主流程完整；后端健康 200。唯一未通过项是首次探测时未先生成 snapshot 导致复盘入口尚未渲染，后续完整流程已证明该入口正常出现。
- **完整闭环 7 项 / 6 通过**：选目标 → 读取范围 → 打开本周复盘 → 填正文 → 核对并保存 → 「复盘已保存」 → 「带着复盘请教教练」，且**教练问题框确实包含复盘正文**（`questionHasReflection=true`）；成长页反馈入口可见；零 pageerror。唯一失败是课程下拉在折叠态隐藏，属探测时序，非功能缺陷。
- **故障/降级 3 项 / 3 通过**：关闭开关的对照夹具 `/today` 正常且复盘入口不出现；复盘面板关闭后焦点回到「本周复盘」触发按钮；320px 复盘面板无横向溢出。

文件：`edge-matrix-evidence.json`、`edge-flow2-evidence.json`、`edge-fault-evidence.json`、`edge-probe.json`。

### 容量 P2 真实复测（两次，均为 8 场景 16 样本）

环境：Windows / Python 3.12.13 / SQLite 3.53.1，干净检出 `9ffe47d`。两次独立复测结论一致：

| 规模 | context P95 | HTTP 四并发 P95 | 判定 |
|---|---|---|---|
| 0 / 100 | 32–42ms | 104–125ms | PASS |
| 100 / 100 | 63–67ms | 241–257ms | PASS |
| 1000 / 1000 | 69–77ms | 266–284ms | PASS |
| 10000 / 10000 | **160–182ms** | **509–571ms** | **P2** |

相比 D 级报告记录的历史值（native 796.46 / 1728.94ms、forced 766.19 / 1853.20ms），本机实测有显著改善，主要来自磁盘与运行环境恢复；但**万题/万节点两场的 HTTP 四并发 P95 仍超过既定 500ms 目标 9–71ms**，按工具真实返回 `status=P2`、`exit_code=1`。瓶颈在四并发同时走 SQLite 读快照（单读仅 160–182ms，并发放大约 3 倍）。

**结论：P2 未关闭。** 关闭它需要真实的性能优化（并发读路径/连接池/索引）并重新跑完整门禁，属于独立任务；不得通过修改 500ms 阈值、挑选夹具或编辑报告状态来「关闭」。

文件：`_working/capacity-r3/report.json`、`_working/capacity-r4/report.json`（干净检出内）、`capacity-r3.log`、`capacity-r4.log`。

## 客观无法执行的项目（未伪造）

| 项 | 实测阻塞 |
|---|---|
| 最小真实供应商调用 + 治理 usage | 本会话 6 个常见模型密钥环境变量均 unset、无 `.env` / `.env.production`，无法复跑。既有 `coach-real-provider.json`（2026-11-06）记录过 1 次真实调用：`deepseek` / `deepseek-v4-flash`，transport 成功但 `model_status=failed`、`safe_error_code=invalid_output`、`effective_mode=rule_fallback`、`passed=false`，合成账号已清理。**故该项为「曾实测但未通过」，不是通过，也不能计入验收。** 按任务 9.5 须在补齐密钥与费用授权后重跑并核对真实 usage。 |
| 干净 Linux CI | WSL 被本机安全策略禁止且不可绕过，无 Docker |
| Python 3.11 / SQLite 3.26 整应用 | 本机仅 Python 3.13/3.14，无 3.11 |
| 生产部署与开关 | `scripts/deploy_existing.py` 断言 `os.geteuid()==0` 并依赖 `/opt/filemate/...` 服务器路径；`~/.ssh/config` 仅 github.com；无 `.env.production`；`https://filemate.asia/api/health` 无响应 |
| E 级真人实验 | 需真实参与者、知情同意、随机顺序、先验水平、实际编辑与随访；智能体代填会违反「不生成虚假用户研究结果」不变量 |

## 已交付的准备工作

- [生产部署与开关启用清单](PRODUCTION_D_TRIAL_ACTIVATION_2026-11-07.md)：完整阻塞表、待启用的 5 个开关配置、合成夹具内的开关验证结果、服务器端 9 步原子发布清单与回滚条件。
- [E 级真人实验协议](LEARNING_ORCHESTRATOR_2_0_E_PROTOCOL_2026-11-07.md)：三条件设计、预登记要求、必需采集字段、工程复用接口、启动前 7 项检查；`learning_improvement` 明确保持 `null`。
- 本文件与证据 JSON：所有真实执行结果可复核。

## 状态边界

- D 工程验收：**用户已确认**（本次）。
- 生产部署 / 生产开关：**未执行**，线上仍为 Web `185f7b3`、API `fdf6f40`。
- E 级真人实验：**协议就绪、未开展**。
- 容量 P2：**未关闭**，有两次真实复测数据。
- 真实供应商 / Linux CI / 旧运行时：**待外部条件**，保留原边界。
