# FileMate 试行版整合实施计划

> **For agentic workers** REQUIRED SUB-SKILL 使用executing-plans按任务实施。用户要求两线并行，D专项与品牌小项分别委派，跨模块合同及最终集成由主实施者负责，最终一次独立审阅。

**Goal** 整合可追溯的目标阶段、本周复盘与试用反馈，完成既有D级验收并发布试行版。

**Architecture** 复用Artifact、现役租户存储、学习证据、原子操作与D教练，新增薄HTTP路由和按需界面。现有目标及任务仍由原功能维护。

**Tech Stack** Vue3、TypeScript、FastAPI、Python、SQLite。

**Spec** `docs/superpowers/specs/2026-11-06-trial-integration-design.md`。

## Global Constraints

- 保留原23份测试的指纹与两个用户项目已有修改。
- 新代码写在隔离worktree的新分支`codex/trial-integration-20261106`，临时证据在`D:/FileMate-Project/_working/final-trial-20261106`。
- 本周统计采用上海自然周、原任务当前状态、显式范围、去重与有界读取。
- 本轮记录使用Artifact与现役data_actions，复用个人备份、删除和恢复。新建默认关闭，允许历史记录管理。
- 初始gzip上限143360B，正文17px、动作44px，保留四主题。

## Review Focus

1. 周末、跨年、上海零点及跨课程同名任务，周统计必须归入正确范围与日期。
2. 同一任务跨日重复安排、旧引用失效及D新任务，完成计数必须可追溯且不重复。
3. 响应丢失、双击、双标签与同键异正文，保存与删除只执行一次，恢复只读。
4. 备份恢复、来源删除、账号切换和迟到响应，旧记录正文与授权不串空间。
5. 折叠导航、四主题与窄屏，LOGO及按需面板清晰，关闭后焦点返回入口。

## Task 1 本周复盘只读合同

**Files** 新增`filemate/study/trial/{__init__,models,weekly}.py`、`filemate/tests/trial/test_weekly.py`。

**Interfaces** `WeeklyReader(storage, clock=utc_now).read(scope: ScopeRequest) -> WeeklySnapshot`，在一次read_snapshot中调用resolve_scope/SnapshotReader/project_tasks，最多读取7条稳定日期Artifact。WeeklySnapshot含scope、week_start/week_end、study_date、as_of、revision、summary、items与coverage。

- [ ] 先写上海跨周/跨年、同范围去重、其他课程排除、无计划、失效引用、D计划与最大200项的回归测试，运行观察失败。
- [ ] 实现有界只读聚合，预计时长独立标记。当前来源失败时返回可读错误，损坏单日记录记coverage。
- [ ] 运行`python -m pytest filemate/tests/trial/test_weekly.py -q`，要求全部通过。提交`feat(review): 增加按范围读取的本周安排复盘`。

## Task 2 复盘与试用反馈持久化及API

**Files** 新增`filemate/study/trial/{records,api}.py`、`filemate/tests/trial/test_records.py`与`test_api.py`，修改`server.py`及API/环境变量文档。

**Interfaces** Records提供save_reflection、save_feedback、find_request、list、detail、delete_preview、delete_confirm。路由前缀`/api/trial`，能力GET、周POST`/weekly/context`、保存POST`/reflections`及`/feedback`、恢复GET`/requests/{request_key}`、列表GET`/records`、详情GET`/records/{id}`、删除POST`/records/{id}/delete-preview`和`/delete-confirm`。响应沿用success/data/error、no-store。分页只接收固定query。DecisionRoute适配允许所需GET分页参数。

- [ ] 写同键重放/冲突、删除后原键410、删除不退还10条日限额、失败回滚、跨账号、默认关闭、历史读删、严格JSON/字段长度、删除恢复令牌及摘要不含正文测试，运行失败。
- [ ] 复用repository.atomic/put/load及data_actions，复盘先复核revision。记录与无正文请求墓碑同事务提交/删除，墓碑参加备份恢复。记录的ID、类型和请求键均有界，按类型索引查询。注册router使用当前_storage代理，治理与租户中间件覆盖全部路径。
- [ ] CoachInput与前端类型增加可空reflection_id，context核对该复盘的范围并绑定摘要，repository依赖元信息与privacy.KINDS/_matches加入reflection。删除预览列出影响，确认调用现役依赖清理。回归测试证明教练副本与派生正文随显式复盘删除清除，无正文去重仍保留。
- [ ] 运行`python -m pytest filemate/tests/trial -q`和相关个人备份测试，Ruff通过。提交`feat(trial): 保存复盘与可管理的试用反馈`。

## Task 3 目标阶段与复盘到教练界面

**Files** 新增`web/src/{types/trial,services/trial-api,today/goal-roadmap}.ts`，`components/today/WeeklyReflection.vue`、对应测试。修改`components/LearningPath.vue`、`components/today/TodayWorkspace.vue`、api.ts懒加载出口及环境声明。

**Interfaces** TrialClient与任务2逐一路由对应。goal-roadmap按原task_id/route输出阶段和逾期统计，未知任务进入其他行动。WeeklyReflection接收scope/identity，事件close及coach，coach事件仅携带已经保存的用户反思。TodayWorkspace.openCoach允许可选问题文本，其余输入来源沿用当前草稿。

- [ ] 为阶段覆盖、空任务、旧日期、保存前定位符、恢复GET-only、身份切换、409重读保留输入写测试并运行失败。
- [ ] 实现目标阶段展示与按需复盘，保存成功后才可带入D，导航与关闭有焦点和未保存提示，正文不进浏览器持久存储。
- [ ] 前端测试、vue-tsc与原bundle门禁通过。浏览器验证7日安排、已保存记录、模型零自动调用和原草稿保留。提交`feat(learning): 连接目标阶段与本周复盘教练流程`。

## Task 4 试用反馈界面与导航品牌

**Files** 新增`components/TrialFeedback.vue`，修改PreferenceContent.vue关于入口、Growth.vue入口。品牌独立子任务仅修改Logo.vue、App.vue品牌样式、必要原始派生SVG及小测试。

- [ ] 反馈展示核对预览、确认保存、历史摘要、按需详情、导出与删除预览，恢复沿用任务3请求定位语义。
- [ ] 品牌先验证当前白底与小副标题的实际问题，使用原标志矢量透明派生版，导航调用navigation变体。
- [ ] 确认长中文、四主题、320/390/1024/1440宽度、键盘与网络失败。新反馈单独统计，原匿名相关性口径保持现状。提交`feat(experience): 完善试用反馈与导航品牌呈现`。

## Task 5 D级专项验收并行线

**Files** 既有D计划Task9的工具/测试、`docs/LEARNING_ORCHESTRATOR_2_0_D_DELIVERY.md`。

- [ ] 补齐四目标在确认后进入原模块作答/面试/真实隔离编译、重读及旧历史保护，以失败回归再修复证明。
- [ ] 执行journey、双profile runtime、8规模performance和三条件合成评测，记录真实P2及上游依赖。
- [ ] 在服务器独占临时目录验证实际Python3.11/SQLite3.26、强制无JSON1、迁移/恢复与容量。单次上游验证采用独立合成账号，授权摘录最小化，记录usage并清理。
- [ ] 合并两线后D1—D8映射统一报告，交付既有E真实实验协议，阶段工程结果与真人收益分别表述。

## Task 6 统一门禁、独立审阅与试行发布

- [ ] 执行`scripts/verify.ps1 -IsolateFrontend`和干净Linux CI，保留原Windows日志，保护原23份测试。
- [ ] 实机浏览器验证任务3—4、D四场景、响应丢失/关闭开关/故障恢复、四主题和冷加载预算。只派一次全新只读最终审阅，作者修复重要问题并重跑受影响门禁。
- [ ] 更新交付、API、试用协议与最新索引，按独立原子发布流程备份并部署匹配Web/API，开启经工程验收的D与本轮试用开关，核验版本/健康/真实流程与回滚条件。
- [ ] 提供新ZIP、SHA256及源码/产物manifest，保留旧包。报告说明未覆盖设备、真实样本及尚存P2，供试用、创业申报和研究成果使用。

## 计划自审

本周读取→revision绑定→记录保存→前端恢复共享同一合同。D线修改验收工具，品牌线修改Logo/App品牌样式，主线修改trial/Today/Goal与反馈，不交叉写文件。最终门禁在全部代码合并后执行。用户本轮要求并行完成并发布，先前D计划及当前方向已经确认，新整合实施内容随本设计供用户核对。
