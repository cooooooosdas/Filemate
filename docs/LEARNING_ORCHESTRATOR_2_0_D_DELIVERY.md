# 学习教练 D 级工程验收候选

2026-11-10 最新结果见[试行版收尾与迁移](TRIAL_RELEASE_CLOSEOUT_2026-11-10.md)。用户已验收 D，干净 Linux CI 通过 2191 后端、444 前端，当前 Windows 真实编译流程复测通过。下方保留原批次记录，实际生产切换、供应商复测及容量 P2 按最新记录继续办理。

> 2026-11-07 收口：最终源码 `9ffe47d`、统一门禁、独立只读审阅（无 P0/P1）及发布包 `FileMate-20261107-trial-d-final.zip` 已完成，详见 [最终收口报告](TRIAL_INTEGRATION_D_FINAL_DELIVERY_2026-11-07.md)。本报告下述「待收口项」的状态以该报告第「待收口项状态」表为准；生产部署与 D 开关仍须用户验收后执行。

2026-11-06 本地验收补充。阶段结论为 CONDITIONAL PASS。用户已确认完整设计及九项实施计划，当前继续执行任务 9。最终独立审阅、阶段用户确认及生产启用仍按原计划办理。

## 源码与运行边界

本轮工作树为 `codex/trial-integration-20261106`，起点提交 `8e7710a518a7ed6d7175d320473ec707f85a740d`。任务 1—8 已提交至 `89de3ec`，此前任务 9 工具与兼容性候选已由 `de1ba77` 保存。当前验收修改以最终 diff 与每份结果中的 `critical_source_sha256` 为准。

线上 Web 仍为 `185f7b3`，API 为 `fdf6f40`。业务 schema36、治理 schema3。本轮复用 Artifact、StudyPlan、来源绑定及治理账本，数据库迁移保持版本 36。

新建建议与确认要求服务端同时设置 `FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=1`、`FILEMATE_ENABLE_LEARNING_COACH=1`。前端入口受 `VITE_ENABLE_LEARNING_COACH=true` 控制。默认值分别为 0、0、false，生产 D、独立音视频保持现役配置。开关关闭后仍可查询历史请求、回执、已保存日期、取消及受保护撤销。

## 四目标与原功能执行

本轮使用独占合成目录，创建考试、竞赛、求职及能力训练四类目标。能力训练目标的截止日期为 28 天后，本次采纳的是受限短期计划。

每条流程实际执行读取所选证据、本地规则、单次授权的合成模型补充、分钟编辑、联合预览、确认、原键重放、原功能写入、回读及开始训练后的撤销冲突。候选阶段 StudyPlan 数量保持原值，确认只新增一份分日期计划，重放新增计划数为 0。

- 考试流程通过原 `ReviewRepository.submit` 保存新独立作答，按 attempt_id 回读原答，重放没有新增作答。
- 竞赛流程根据已保存计划中的 `rehearse_interview` 目标，通过原 `CoachRepository.submit` 保存新的回答版本。新旧 attempt_id 不同，旧回答及旧反馈运行记录的指纹保留，重放没有新增版本。
- 求职流程执行上述原生面试重答，并按已保存 `practice_problem` 目标创建新代码提交，经过原 `programming.service.execute` 执行隔离编译与判题。当前 Windows AppContainer／MSVC 实测为 AC，6／6 测试点通过，旧提交保持原样。
- 能力训练流程按真实题目身份与版本创建新代码提交，经同一现役隔离执行器取得 AC，6／6 测试点通过。新的提交 ID 与原始合成 CE 记录分离，重复创建请求没有增加提交。

四目标历史损害计数均为 0。保存学习日完成状态仍使用原 `set_study_plan_day`，属于用户自报计划进度。具体训练结果以原模块记录为准。

上下文中的既有反馈与 CE 判题证据明确标为合成记录。模型解释采用无网络的 `synthetic_runner`。本轮新增代码提交的 AC 来自真实隔离执行器，结果分别记录 `context_compiler_evidence` 与 `compiler_execution`。模型供应商实测另行收口。

沙箱故障注入时，原生提交保留 `failed`／`SYSTEM_ERROR`，报告列出 `programming_sandbox_unavailable` 依赖并返回 CONDITIONAL PASS。原始提交继续可读。

## D1—D8 对照

- D1 已接通有依据教练、预算与短任务方案，四目标服务层流程及原领域写入见本轮 journey 结果。当前 UI 的四目标联合操作矩阵仍须最终收口。
- D2 规则路径、严格增强校验、真实失败状态与规则回退已有实现。任务 3 的回环 Provider／私有子进程证据，以及本轮缺配置 HTTP 回退分别保留其适用范围。真实供应商及治理 usage 验收仍待补充。
- D3 五种意图由现役规则测试覆盖，包括预算、考试、错因、未来日期及下一步。未来日以真实 as_of 为证据截止，上海跨日采用显式注入时钟验证。
- D4 固定工作流复用持久认领、受限模型运行、联合预览、原子确认及回执。当前 runtime 验证事务失败整体回滚、恢复轮换权限、旧撤销令牌失效、D 关闭后原流程可用。
- D5 用户显式选择面试与反馈项，当前实际重答新增原模块回答版本并保存旧回答／旧反馈。模型参考分与课程掌握统计分离。
- D6 读取已确认图谱依据与有效来源，跨课与来源有效性由现役 context／output／privacy 测试约束。当前性能夹具同时包含节点与关系，八场返回的语义 ID 摘要稳定。
- D7 复用原独立作答、已确认错因、复习周期及原任务身份。当前真实作答与重放回读通过，旧记录指纹保留。
- D8 同一证据与预算分别比较 rule、model_explanation、manual_edit 三条件。四目标共 12 条结果的工程违规计数均为 0，实际编辑数为 0／0／1，`learning_improvement` 为 null。

## 兼容性、删除与恢复

本轮 native 与 forced-noJSON1 均在 Windows／Python3.12.13／SQLite3.53.1 跑整应用。两组的 schema36、事务回滚、签名备份恢复、恢复 epoch 轮换、历史确认回执、旧撤销权限拒绝、旧来源可读、模型故障回退、数据库故障隔离与恢复、D 关闭后原流程共 10 项检查全部为真。

forced profile 实际拒绝未注册 JSON1 函数 7 次，其中工作负载 6 次。缺少 `json_valid` 时保留连接级严格有限 JSON 标量校验，既有迁移保持原样。该 profile 的真实引擎版本仍为 SQLite3.53.1，Python3.11／SQLite3.26 整应用验收由独立旧运行时证据补充。

任务 8 已有真实 Edge 的来源删除、签名备份导出、预览确认删除、隐私页上传恢复及清除恢复定位符证据，见 [界面进展](LEARNING_COACH_D_UI_PROGRESS.md)。完整最终交互矩阵、恢复与来源清除的当前分支复验仍待最终记录。

## 容量结果

测量固定为 16 个上下文／规则样本及 16 个四并发 HTTP 样本。八场分别使用 0／100、100／100、1000／1000、10000／10000 的错题与节点规模，均执行 native 和 forced-noJSON1 两种 profile。资料范围外另有等量错题，万题场每条到期时间不同。

前六场均满足现役 500ms P95 读取目标。万题／万节点的两场保留 P2。

- native 上下文 P95 为 796.46ms，四并发 HTTP P95 为 1728.94ms。
- forced-noJSON1 上下文 P95 为 766.19ms，四并发 HTTP P95 为 1853.20ms。

八场语义 ID 摘要均稳定，记录覆盖说明、返回数量、截断与响应体积，模型调用数为 0。容量命令按真实 P2 返回退出码 1。Windows 容量结果与此前公开的旧 Linux 万题 P2分别保留，旧 Linux 容量仍须单独验证。

## 本轮证据

独占证据根为 `D:/FileMate-Project/_working/final-trial-20261106`。只有工程夹具、日志及结果进入该目录，未读取生产用户数据。

- `coach-journey-domain-red.log` 保存本轮四目标缺少原领域执行证明的 4 项失败。
- `coach-journey-domain-green2.log` 保存补齐后的 4 项通过。
- `coach-journey-r3/report.json` 保存四目标原模块写入、重放与真实隔离判题结果，退出码 0。
- `coach-runtime-r3/report.json` 保存当前 Windows native／forced 两组运行时检查，退出码 0。
- `coach-performance-r2/report.json` 与同名日志保存 8 场容量及真实退出码。
- `coach-evaluation-static-r3.json` 保存静态 12 条三条件评测结果，PASS／退出码 0。
- `coach-task9-final.log` 保存受影响四类专项的 15 项通过，耗时 35.12 秒。

最终 r3 夹具、journey、runtime 与 evaluation 的关键源码摘要为 `4395281b7c23e71a8776040c1f413f0a650feb9fe7eabe3a8bc7d24492a86eae`。容量 r2 保留自身源码摘要与实际测量时的工具版本。Ruff 与改动差异检查通过。当前分支的统一工程门禁在本次交付收口时补充。此前网页优化的本机 2142 后端／430 前端、干净 Linux 2159 后端／430 前端属于当时源码证据，详见 [网页交付](FINAL_WEB_OPTIMIZATION_DELIVERY_2026-11-05.md)。

## 最小复跑命令

在项目根目录执行，每次使用新的 `_working` 输出名。

```powershell
uv run pytest filemate/tests/orchestrator/coach/test_journey.py filemate/tests/orchestrator/coach/test_runtime.py filemate/tests/orchestrator/coach/test_capacity.py filemate/tests/orchestrator/coach/test_evaluation.py -q
uv run python scripts/acceptance/learning_coach_fixture.py --output _working/learning-coach-d/final-fixture
uv run python scripts/acceptance/learning_coach_journey.py --output _working/learning-coach-d/final-journey
uv run python scripts/acceptance/learning_coach_runtime.py --output _working/learning-coach-d/final-runtime
uv run python scripts/acceptance/learning_coach_performance.py --output _working/learning-coach-d/final-performance --samples 16
uv run python evaluation/evaluate_learning_coach.py --cases evaluation/fixtures/learning_coach_cases.json --output _working/learning-coach-d/final-evaluation.json
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
```

## 待收口项与 E 级交接

1. 固定最终源码并核对 23 份既有用户测试文件哈希，重跑受影响专项及干净 Linux 工程门禁。
2. 补充 Python3.11／SQLite3.26 整应用与容量结果，保留未达标 P2。
3. 在现有授权与凭据条件下运行一次最小真实供应商调用，核对持久化结果、模型／Prompt版本、治理 usage、失败码和合成账号清理。
4. 完成当前分支四目标与任务 8 的真实浏览器联合矩阵，区分实际经过的引擎、尺寸、键盘操作和受控时钟。
5. 按原计划执行一次全实现分支的独立审阅，修复重要发现后固定最终门禁，再申请 D 阶段用户验收。

E 级继续保留真实次日操作、三专项与可信执行回归、多浏览器／桌面与实体设备、恢复及大规模、三条件真实研究协议、最终源码／架构／任务模型／API／操作手册／科研与创新材料。真实研究仍需记录招募与同意、分组和随机顺序、先验水平、目标与证据、模型版本与用量、实际编辑、实际完成和随访结果。当前工程数据中的学习提升字段保持 null。
