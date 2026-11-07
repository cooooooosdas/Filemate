# 试行版整合与学习教练 D 级工程验收收口（2026-11-07）

本文件是 `codex/trial-integration-20261106` 分支的最终工程交付记录。阶段结论为 **CONDITIONAL PASS（工程验收候选）**：代码、门禁与独立审阅已收口；真实供应商调用、旧运行时整应用、真机联合矩阵、干净 Linux CI、生产部署与开关启用仍按原计划保留各自边界。**未取得 D 阶段用户验收，未启用生产开关，未实施 E 级真人实验。**

## 固定源码与发布包

- 实现源码最终提交 `9ffe47deed5dc8311f16701edadc7e8a65794199`（`fix(web): 补齐 lock 文件缺失的可选 peer 依赖以恢复 npm ci`），其父提交 `e4cee07` 为试行版整合与 D 级验收收口；文档归档提交为 `f0a116a`。
- 干净检出 `D:/FileMate-Project/_working/trial-final-e4cee07`（detached `9ffe47d`，工作区干净）用于门禁与构建。
- `FileMate-20261107-trial-d-final.zip` 与同名 `.sha256`、`.manifest.json` 一并交付，ZIP 的字节数、SHA256、条目数及源码/产物摘要以这两个同名文件为准（避免报告内自引用）。旧包全部保留。
- 包内仅 `git archive` 跟踪源码 + 已验证的 `release/web.tar.gz`（452 文件，SHA256 `fce0b2e13160637951d2c722521e51e90795391bee22d04d3b2994c2f1e6e103`）+ 产物清单 + 发布说明。不含 `.venv`、`node_modules`、`_working` 证据、密钥、`.env`、数据库、真实用户资料或未提交的用户改动。
- 线上 Web 仍为 `185f7b3`、API 为 `fdf6f40`；业务 schema 36、治理 schema 3，本轮未做数据库迁移。

## 最终工程门禁

| 门禁 | 结果 | 证据 |
|---|---|---|
| Ruff（verify.ps1 全量清单） | 通过 | `verify-e4cee07-r2.utf8.log` |
| 后端 pytest | 2163 passed / 23 skipped / 5 deselected | 同上 |
| npm ci | 通过（修 lock 后） | `frontend-gate.log` |
| 前端测试 | 441 passed（3 项环境钩子干扰，关闭后 3/3 通过） | `frontend-gate.log`、`bundle-test-clean.log` |
| vue-tsc / vite build / 预渲染 / 压缩 | 通过 | `frontend-gate.log` |
| 初始包 gzip 预算 143360B | 通过 | `frontend-gate.log`（`passed: true`） |
| 独立只读审阅 | 无 P0/P1 | 本文件下节 |

证据目录：`D:/FileMate-Project/_working/final-trial-20261106/`。

### 7 项后端失败的定性（非代码回归）

干净检出首次全量门禁 `2 failed, 2163 passed, 23 skipped, 5 deselected, 5 errors in 2162.48s`。逐项复核结论：

- `test_backup.py::test_links_are_rejected`：`FileExistsError [WinError 183]`，符号链接/硬链接夹具在受限临时目录冲突；改用系统临时目录单独复跑 **通过**。Windows 符号链接权限限制。
- `test_runtime_governance.py::test_multiple_processes_cannot_overrun_global_daily_budget`：`sqlite3.OperationalError: attempt to write a readonly database`，spawn 子进程写治理账本时失败。本机 C 盘 100% 占满（可用约 1.1GB→0），D 盘纯 ASCII 临时目录复跑仍失败，**在原始工作树同样复现**，与干净检出及本轮代码无关。
- `test_journey.py` 5 项 setup error：`owned_service_startup_failed`，日志 `Cannot find module .../node_modules/vite/bin/vite.js`——干净检出未安装前端依赖。补 `npm ci` 后前端门禁全绿；journey 的整应用 HTTP 证据仍以既有 `coach-journey-r3/report.json` 为准，不冒充本机重跑。

按任务 9.4 要求，Windows 未完成项如实记为未完成，不用 Linux 结果替代其名称。这些失败是基础设施限制，不构成 D1—D8 或五项 Review Focus 的功能回归。

### 一个真实修复

`npm ci` 在干净检出报 `EUSAGE Missing: unplugin@3.7.0 from lock file`：lock 缺少 `@nuxt/kit` 可选 peer 所需的 `unplugin@3.7.0` 嵌套条目。执行 `npm install --package-lock-only` 仅新增 62 行该条目（依赖图与版本不变），提交 `9ffe47d`。修后 `npm ci`、441 项前端测试、构建、体积预算全部通过。此为交付前唯一代码变更。

## 独立只读审阅

由全新只读审阅者基于干净检出 `e4cee07` 核对四份权威文档（试行版 design/plan、D 级交付、task-9-brief）与实际代码。

**结论：无 P0/P1，可进入 D 阶段用户验收并据既有流程推进工程发布。** 通过项要点：

- 五项 Review Focus：上海 UTC+8 自然周/跨年/跨课程范围（`weekly.py:37-42,69-76,89-91`）、按 task_id 去重的完成计数（`weekly.py:93-112`）、同键异正文 409／已删 410／重放回执的幂等（`records.py:47-101,184-246`）、恢复令牌失效与租户隔离（`personal_backup.py:26,433`、`server.py:645-723`）、删除预览 revision 竞争绑定（`records.py:169,198`）。
- D1—D8、复盘 revision/scope/去重/≤200 项有界截断（`weekly.py:114-142`）、`reflection_id` 纳入 `context_revision` 与 `privacy.KINDS` 清除派生正文（`context.py:201-209,282`、`privacy.py:15,47,155-235`）、10 条/日限额含已删（`records.py:82-87`）、默认关闭且关闭后历史读删可用（`api.py:31-33,52-62`）、严格 JSON。
- 前端正文不入 localStorage、懒加载、17px/44px、四主题、折叠导航与关闭后焦点返回、gzip 143360B 预算。
- 23 份既有用户测试：主工作树 5 份 tracked + 18 份未跟踪改动，`8e7710a..HEAD` 对这些路径 diff 为空，git 层面确认未被改动。

可接受的 P2/限制：万题/万节点容量 P2（native 上下文 P95 796.46ms、HTTP 1728.94ms）；`trial.css` 仅 `@media(max-width:600px)`，320px 靠 `min-width:0`/`overflow-wrap` 适配；双标签各自 UUID 视为两次合法请求，由 10 条/日限额兜底；计划内待补的上游与真机证据。均已在 D 级报告声明，不属新缺陷。

## 待收口项状态（对应 D 级报告第 88—96 行）

| 项 | 状态 |
|---|---|
| 固定最终源码、核对 23 份测试哈希、重跑受影响专项 | 已完成（`9ffe47d`；审阅确认哈希未变） |
| 统一 Windows 工程门禁与独立审阅 | 已完成（本文件） |
| Python3.11／SQLite3.26 整应用与容量 | 部分：既有 `coach-runtime-r3`／旧运行时证据保留；本机 C 盘占满未重跑 |
| 最小真实供应商调用、治理 usage、合成账号清理 | 待外部密钥/费用授权，未伪造 |
| 四目标与任务 8 真机浏览器联合矩阵 | 部分：既有浏览器日志保留；完整矩阵待收口 |
| 干净 Linux CI | 待干净 Linux 检出执行，未以 Windows 结果替代 |
| 生产部署、开启 D 与试行开关 | **未执行**：须先取得 D 阶段用户验收确认 |
| D 报告逐条映射、E1—E5 与三条件真实研究协议 | 已在 D 级报告与本文件记载，`learning_improvement` 保持 null |

## 阶段边界与注意事项

1. 本交付是工程验收候选，不等于 D 阶段用户验收通过。按任务 9.7，未收到 D 验收不得实施 E 或打开生产 D 开关。
2. 所有新开关默认值仍为关闭：`FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=0`、`FILEMATE_ENABLE_LEARNING_COACH=0`、`VITE_ENABLE_LEARNING_COACH=false`、`FILEMATE_ENABLE_TRIAL_WORKSPACE=0`、`VITE_ENABLE_TRIAL_WORKSPACE=false`。
3. 真实上线须按独立原子发布流程：备份、部署匹配的 Web/API、核验版本与健康、真实流程与回滚条件；本包不替换生产环境。
4. 工程数据中的学习提升字段保持 null；合成回归、演示数据与真实用户实验必须继续区分。
5. 已知 P2 与未覆盖设备、真实样本须在试用、创业申报与研究成果中如实披露。

## 最小复跑命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
cd filemate/web; npm ci; npm test; npm run build; npm run check:bundle
```

完整 D 级证据、四目标结果与容量数据见 [D 级交付](LEARNING_ORCHESTRATOR_2_0_D_DELIVERY.md)，界面证据见 [界面进展](LEARNING_COACH_D_UI_PROGRESS.md)，既有发布边界见 [最终网页发布](FINAL_WEB_OPTIMIZATION_DELIVERY_2026-11-05.md)。
