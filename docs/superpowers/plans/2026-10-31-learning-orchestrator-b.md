# Learning Orchestrator 2.0 · B级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在明确目标范围内读取一致学习证据、投影既有任务、生成可解释且不超预算的候选安排，并通过确认、幂等回执和撤销保存今日安排，保护前三专项历史。

**Architecture:** 在现役FastAPI进程中增加`filemate/study/orchestrator/`。复用现役SQLite、学习空间、Artifact、study_plans、复习与面试记录；TaskView只投影领域状态。确认只保存日安排引用与偏好，不新建任务主表、不改写领域完成记录；用户仍通过原功能执行任务。

**Tech Stack:** 当前Python约束`>=3.10`、FastAPI、Pydantic、SQLite；客户端只增加TypeScript合同。SQL以实际SQLite 3.26兼容验证为底线，不新增依赖、外部服务或模型调用。

**Spec:** [已通过A级方案](../../LEARNING_ORCHESTRATOR_2_0_A_AUDIT.md)及[交付清单](../../LEARNING_ORCHESTRATOR_2_0_A_ACCEPTANCE.md)；原任务书`C:/Users/胡希/.codex/attachments/7841a6a3-3b50-45cd-8996-97b11c136836/pasted-text-1.txt`的B1—B6与阶段规则。

2026-10-31用户明确回复“验收第三版，A级通过，进入B级计划”。第三版本地工程正式验收、第四版A级整体通过；本计划仍须审阅后才实施，不表示B级通过。实施方式建议沿用当前会话逐项执行，结束后一次独立审阅。

## Global Constraints

- “学习记录与学习能力不是同一概念”；无数据显示“待评测”或“证据不足”。面试参考评分不用于课程能力判断，不制造掌握率。
- “该层只能读取与当前目标有关的必要信息”；身份和数据库由现役请求上下文解析，不接受客户端workspace/user/db_path，不默认读取全空间。
- “不允许后台静默覆盖学习安排”；所有正式调整须预览、确认、回执、可撤销；原目标、截止日期、完成记录、知识关系与评分不被决策层改写。
- “相同来源的任务如果已经完成，不应被新生成的计划悄悄恢复成待完成”；投影与计划确认不能创建、重置或代替真实作答。
- 支持多个保存目标；本版每次日安排显式选择一个今日优先目标，其他目标保留。跨目标自动合并预算不是本B级默认行为。
- 规则为主、AI按需；B级模型调用必须为零。今日主入口与可选冲刺已确定，页面实施属于C、模型解释属于D。
- 本计划零迁移，业务schema仍为36；不修改任何已发布迁移。需要新表/列或改变领域合同才能继续时先记录冲突并提交调整，不暗中扩展范围。
- 所有验收输出放新的`_working/orchestrator-b-20261031/`子目录；上述`-1`已存在时保留，重跑递增后缀并记入执行账本，不覆盖旧证据。
- 不改24份用户已有测试。新测试用原创合成数据并标明synthetic；不读写真实学习资料，不执行部署或生产迁移。
- SQL绑定参数、列表先限域后LIMIT；不依赖JSON1、新SQL语法或全图谱投影才能运行。旧SQLite实测、完整目标运行时和本机验证分开报告。
- 新开关`FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=0`默认关闭；关闭停止新快照/预览/确认/撤销，但已保存日安排与回执仍可只读，现有入口继续可用。

## Review Focus

1. 同一资料出现在多门课程、无资料目标、外空间标识：要求显式范围，拒绝越界；测试归任务1。
2. 一次错题出现在多来源、诊断变化、新复习周期、混合计划日：只合并同一真实动作，不吞掉组合任务、不复活完成项；测试归任务2。
3. 上海午夜、同日截止、零分钟、固定项超预算：日期一致、结果确定、超预算明确延期；测试归任务3。
4. 两标签页或两个storage实例并发确认、确认后断网、改body重放、撤销后重试、恢复后旧token：不覆盖新工作或重复应用；测试归任务4和7。
5. 缺JSON1、坏JSON、来源删除、万题但相关题在全库末尾、数据库失败：范围完整性明确、无隐式降级为全空间、局部故障可恢复；测试归任务1、5、6。

## 文件职责与写入边界

| 文件 | 职责 / 所属任务 |
|---|---|
| `filemate/study/orchestrator/models.py` | 严格请求、内部快照、任务/引用、调度及回执合同；任务1—4分别增补所属类型 |
| `snapshot.py`、`snapshot_queries.py`（同目录） | 一个事务内的范围核验、限域读取、计数、版本与证据覆盖；任务1 |
| `task_views.py` | 身份、动作去重、领域状态与精确入口；任务2 |
| `scheduler.py` | 纯规则、预算、手排固定和未安排理由；任务3 |
| `repository.py`、`commands.py` | 仅日安排与操作Artifact、令牌、事务、冲突及撤销；任务4 |
| `api.py`、`settings.py` | 薄路由、请求边界、开关；任务5 |
| `filemate/wrongbook/queries.py` | 增加同快照/多来源读取入口，保持旧查询合同；任务1 |
| `server.py` | 只挂载新路由，不重写旧目标、今日或领域完成接口；任务5 |
| `filemate/execution/storage.py` | 仅对两类新增安排/回执Artifact增加通用保存/编辑保护，不改schema或其他类型行为；任务4 |
| `filemate/web/src/types/orchestrator.ts`、`services/api.ts` | 共享类型和受控API调用，不改页面、导航或主题；任务5 |
| `.env.example`、`filemate/docs/API_SPEC.md`、`scripts/verify.ps1` | 新开关、公开合同与新目录检查；任务5 |
| `filemate/tests/orchestrator/` | 新的隔离fixture与各任务测试；复用既有server/account fixture，不改其定义 |
| `scripts/acceptance/orchestrator_runtime.py`、`orchestrator_performance.py`、`orchestrator_journey.py` | 分别记录实际运行时、容量、B级完整链与恢复；任务6—7 |
| `docs/LEARNING_ORCHESTRATOR_2_0_B_DELIVERY.md`、`docs/audits/learning-orchestrator-b-2026-10-31/` | 本阶段事实、原始证据、剩余限制与用户手册；任务7 |

不在本阶段修改五个业务Vue页面、现役表结构、部署配置、前三专项评分/调度/关系写入算法。旧`/goals/{id}/replan`的覆盖风险不会因本计划自动消失；新决策链不调用它重排，C接入前须落实界面保护。

## 任务间冻结合同

- `Clock = Callable[[], datetime]`返回带时区时间；服务端捕获一次UTC `as_of`，默认自然日为`Asia/Shanghai`，客户端不能指定时钟或未来as_of。
- `ScopeRequest(goal_id: str, course_id: str | None, source_ids: list[str])`：标识1—128字符、最多20个来源、拒绝重复与额外字段。有效goal必须是当前空间`reverse_goal_plan`。指定课程时来源须为该课程活动来源，已有目标来源也须在范围内；不指定课程时仅使用目标单一来源，或无来源目标明确指定的一份来源。无范围的目标只返回目标自身及`needs_scope`，不读取其他课程。
- `EvidenceSnapshot`包含`scope/as_of/study_date/evidence_revision/facts/evidence_refs/coverage`。facts分开保存目标、计划、学期、复习、真实作答、确认图谱、显式关联面试；原始回答不进入公共快照或操作日志。源更新时间未知为null。revision包含有效源、领域状态、证据/关系及当日资格，不因无意义的读取时间变化而变化。
- `TaskView`包含A级14个候选字段，另有`origin_refs/completion_ref/action_key/evidence_refs/route/eligibility`。`status`从真源派生；同名模板不等于同一任务。路线由服务端原始ID编码生成，不能从模型或客户端接收任意URL。
- `ScheduleOptions`：`available_minutes`严格整数0—1440；这是本次剩余可投入时间，不是实际耗时。task_id最多512字符；`item_order/excluded_ids`各最多200个不同的有效task_id，`pinned_ids`最多20个且属于item_order；`minute_overrides`最多200个有效task_id，值为严格整数1—240，标明user_estimate。固定保留相对次序，不强制超预算入选；已完成记录不参与剩余预算，但保留在反馈中。
- `SchedulePreview`返回`scope/study_date/as_of/evidence_revision/rule_version/selected/deferred/completed/coverage/estimated_minutes/changes/confirmation_token/expires_in_seconds`；`selected`最多20项。`deferred`最多100个详情，另给准确计数、截断标记及原因分布；不能把截断当成没有任务。
- `learning-orchestrator-rules-v1`先确定固定项和手排项相对次序，其余按有效到期/明确临近截止、真实错误、已确认依赖、稳定task_id排序；具体可解释排序见任务3。无可信估时项列入`estimate_required`，不以0分钟塞进预算。
- 日安排Artifact类型`learning_orchestration_day`，固定ID由服务端上海日期生成；保存当前优先目标、明确范围、预算、顺序、固定/排除项、选中TaskRef、规则/证据版本和单调revision。它是引用/偏好，不保存另一份任务完成状态。
- 操作Artifact类型`learning_orchestration_operation`，ID为服务端对request_key的SHA-256加命名空间；保存规范命令摘要、前后偏好及回执。只存ID/修订/必要元数据，不复制源文件、题干、回答、模型分数或原文。两类均`source_id=NULL`，读取时重验来源；源删除不能让旧安排继续宣称有依据。
- `ConfirmRequest = PreviewRequest + confirmation_token(64位hex) + request_key(16—80位字母数字/_/-) + confirmed(严格true)`；命令摘要绑定scope、日期、选项、预览结果与day revision。两类新增Artifact必须禁止通用save_artifact/update_artifact覆盖、改类型或编辑；受控仓储仅在本事务中写入。回放前必须比对命令，不依赖`data_actions.check()`对成功token直接返回的宽松行为。
- 新请求体均`extra='forbid'`且严格类型。业务错误404/409/422、准入或有界写入限额429、存储失败503，统一现役JSON envelope与`Cache-Control: no-store`，不暴露SQL、路径、令牌或用户原文。

---

### Task 1: 有明确范围的一致证据快照（B1）

**Files:** Create `filemate/study/orchestrator/{__init__,models,snapshot,snapshot_queries}.py`、`filemate/tests/orchestrator/{conftest,test_snapshot}.py`；Modify `filemate/wrongbook/queries.py`。

**Interfaces:** Consumes当前`SQLiteStorage.read_snapshot()`、来源修订、领域表/Artifact和`ReviewQueries`；Produces `SnapshotReader(storage, *, clock: Clock | None = None).read(scope: ScopeRequest) -> EvidenceSnapshot`及`read_in_transaction(read: SQLiteStorage, scope: ScopeRequest, *, as_of: datetime) -> EvidenceSnapshot`。后者只读传入连接，不新开快照/提交事务。`ReviewQueries.page_in_snapshot(read, filters, *, as_of, source_ids: tuple[str, ...], limit=100, offset=0, eligible_only=False) -> dict`保证先范围过滤再计数/分页；不改变旧course过滤含义。

- [x] Step 1: 写`test_scope_never_reads_other_course`、`test_goal_without_scope_has_no_global_evidence`、`test_scope_membership_and_foreign_ids`、`test_writer_between_tables_cannot_mix_snapshots`、`test_scoped_due_after_global_first_hundred_is_not_hidden`。断言只读前后数据库逐表逻辑摘要相同、题干/回答不进入公开摘要。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_snapshot.py -q`。Expected: 新入口缺失导致FAIL，不能以fixture导入错误充当RED。
- [x] Step 3: 实现上述合同。课程、来源、目标、领域事实在同一事务核验；面试只读显式goal关联与原训练证据，不并入课程评分；未知、历史只读/坏JSON/缺源项标明不可用。查询上限：100个计划、100个复习候选、200条引用、最终投影200项；全量计数与有限详情分开，覆盖不足显式返回；依赖关系未完整核验不能当作“没有前置”，受影响任务blocked/deferred。不靠全空间画像或整图聚合。SQL使用参数绑定，空source_ids绝不能取消WHERE条件。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator/test_snapshot.py filemate/tests/wrongbook/test_workspace_reads.py filemate/tests/wrongbook/test_insights.py filemate/tests/wrongbook/test_priority_capacity_contracts.py -q`。Expected: 全部PASS，旧筛选及真实SQLite只读约束保持。以上三个现有测试文件已按当前仓库核对。
- [x] Step 5: Commit `feat(orchestrator): 增加限域一致学习证据快照`，只暂存本任务文件。

### Task 2: 任务身份、去重与真实状态投影（B2）

**Files:** Create `filemate/study/orchestrator/task_views.py`、`filemate/tests/orchestrator/test_task_views.py`；Modify `models.py`。

**Interfaces:** Consumes任务1 `EvidenceSnapshot`；Produces `project_tasks(snapshot: EvidenceSnapshot) -> TaskProjection`，其中`TaskProjection`有`tasks/completed/unavailable/overlaps/coverage`；每项为TaskView或带原因的原始引用。

- [x] Step 1: 写`test_graph_and_review_plans_project_once`、`test_same_wrong_cycle_one_action_with_all_origins`、`test_diagnosis_does_not_create_cycle`、`test_new_due_cycle_keeps_old_history`、`test_composite_plan_is_not_swallowed_by_one_review`、`test_completion_and_semester_revision_do_not_mint_new_task`、`test_task_routes_resolve_original_resource`。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_task_views.py -q`。Expected: project_tasks缺失或关键断言FAIL。
- [x] Step 3: `plan:{plan_id}:{day_index}`、`goal:{goal_id}:{template_id}`、`semester:{semester_artifact_id}:{task_id}`作为原始身份；图谱与错题增量是已有plan的来源，不能再投影一份。复习身份为`review:{wrong_id}:{digest(规范UTC next_review_at)}:independent_review`；诊断更新不改变周期，人工改期只标原引用superseded，不谎报完成。只在明确同wrong、周期与独立复练动作时合并，并保留全部origin_refs；通用导航任务或复合计划日只标可能重叠。以领域完成记录/实际作答事件区分已执行、待核对与达标，不从勾选生成能力结论。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator/test_snapshot.py filemate/tests/orchestrator/test_task_views.py -q`。Expected: 全部PASS；重复投影不写study_plans、quiz_attempts、review_events或完成字段。
- [x] Step 5: Commit `feat(orchestrator): 统一任务投影与动作去重`。

### Task 3: 规则优先级、预算与用户固定顺序（B3—B4）

**Files:** Create `filemate/study/orchestrator/scheduler.py`、`filemate/tests/orchestrator/test_scheduler.py`；Modify `models.py`。

**Interfaces:** Consumes `EvidenceSnapshot`、`TaskProjection`、`ScheduleOptions`；Produces `build_schedule(snapshot: EvidenceSnapshot, projection: TaskProjection, options: ScheduleOptions) -> ScheduleResult`及常量`RULE_VERSION='learning-orchestrator-rules-v1'`。纯函数，无SQL、当前时钟、随机数或模型调用。

- [x] Step 1: 写`test_same_snapshot_is_deterministic`、`test_zero_minutes_defers_every_pending_task`、`test_pins_and_manual_order_survive_budget_reduction`、`test_overbudget_urgent_task_is_deferred_with_reason`、`test_shanghai_midnight_and_same_day_deadline`、`test_unknown_minutes_and_inactive_refs_are_explicit`、`test_manual_minutes_are_bounded_estimates`、`test_completed_is_never_reopened`，拒绝bool/浮点预算与重复/外来ID。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_scheduler.py -q`。Expected: build_schedule缺失或上述行为FAIL。
- [x] Step 3: 固定/手排序列先保持相对顺序，其余键为`(是否有效到期, 明确截止日, -可信错误次数, 已确认前置层级, task_id)`；日期、次数、关系均附可核对引用，缺失值不得编造。循环依赖标blocked，不猜前置关系。按顺序只纳入可完整放入剩余预算的任务；入选最多20，其余说明budget/limit/excluded/blocked/estimate_required。完成反馈独立于预算，截止日从原目标读取，不改为明天。估时可复用已有duration；目标模板的版本估时为import-source=5、review-source=15、baseline-quiz=20、explain-wrong-aloud=12、build-study-plan=10、baseline-interview=15、review-evidence=5分钟，标明rule_default而非实际耗时；clear-due-wrong是汇总导航，不伪装成单题动作或已完成聚合。用户分钟覆盖优先但仍标明预计；未知模板没有估时则estimate_required。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator -q`。Expected: 全部PASS；三类目标（考试、竞赛、求职）的相同证据规则可复算、零模型调用。
- [x] Step 5: Commit `feat(orchestrator): 增加可解释预算调度规则`。

### Task 4: 日安排确认、幂等恢复与撤销（B5）

**Files:** Create `filemate/study/orchestrator/{repository,commands}.py`、`filemate/tests/orchestrator/test_commands.py`；Modify `models.py`、`filemate/execution/storage.py`（仅新增类型保护）。

**Interfaces:** Consumes任务1—3及现役`data_actions.issue/check/finish`；Produces `OrchestratorCommands(storage, *, clock=None).preview(request: PreviewRequest) -> SchedulePreview`、`confirm(request: ConfirmRequest) -> OperationReceipt`、`preview_undo(operation_id: str) -> UndoPreview`、`confirm_undo(operation_id: str, request: UndoConfirmRequest) -> OperationReceipt`；`OrchestratorRepository(storage).today(study_date: date) -> DayView`及`find_request(request_key: str) -> OperationReceipt | None`。

- [x] Step 1: 写`test_preview_only_persists_token_not_tasks`、`test_confirm_replay_and_changed_body`、`test_two_storage_instances_only_one_revision_wins`、`test_lost_response_recovers_without_second_apply`、`test_undo_preserves_new_completion`、`test_retry_after_undo_never_reapplies`、`test_source_delete_or_midnight_invalidates_preview`、`test_write_failure_rolls_back_artifact_token_and_audit`、`test_reserved_artifacts_cannot_be_edited_or_retyped`。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_commands.py -q`。Expected: commands/repository缺失或原子性断言FAIL。
- [x] Step 3: preview短事务写15分钟绑定令牌；不写领域记录。confirm/undo使用同一数据库连接的`BEGIN IMMEDIATE`，在事务内重读scope、day revision、偏好和证据，再保存日安排、不可变操作Artifact、令牌回执及审计。禁止调用会自行commit的`save_artifact/set_daily_coach_preferences`作为事务内部子步骤。操作键同body回执幂等、异body409；先核对command摘要才走成功token回放。恢复后的旧token不存在即拒绝，不能仅凭操作Artifact重放写入。
  同日仅一个已确认主安排，切目标需展示替换影响；先读旧日期同名偏好作为首次默认值，不回写旧偏好表。旧入口并发改偏好也参与预览摘要。撤销只恢复此前范围/偏好/引用，不能恢复任务旧status；后续编辑冲突时拒绝。原确认撤销后再重试只返回历史回执并明确undone，不重新应用。读取保存安排时重验引用，缺源/改题/换周期标stale并要求重做预览。将新操作和未使用预览分别限制为每空间每天100条，超额429；回放、只读和每个操作至多一次的撤销不消耗新确认额度。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator -q`。Expected: 全部PASS；并发、故障、重试后领域表指纹均未被日安排写入改变。
- [x] Step 5: Commit `feat(orchestrator): 增加可撤销的日安排确认命令`。

### Task 5: 现役认证内的API与客户端合同

**Files:** Create `filemate/study/orchestrator/{api,settings}.py`、`filemate/web/src/types/orchestrator.ts`、`filemate/tests/orchestrator/test_api.py`、`filemate/web/tests/orchestrator-api.test.mjs`；Modify `server.py`、`filemate/web/src/services/api.ts`、`.env.example`、`filemate/docs/API_SPEC.md`、`scripts/verify.ps1`。

**Interfaces:** Consumes任务1—4；Produces `create_router(get_storage: Callable[[], SQLiteStorage]) -> APIRouter`及下表公开合同。server以当前请求空间解析存储，不创建新身份系统。私有`orchestratorRoot`固定为`/api/learning/orchestrator`，客户端函数为`getOrchestratorCapabilities/readOrchestratorSnapshot/previewOrchestratorSchedule/confirmOrchestratorSchedule/getOrchestratorToday/findOrchestratorOperation/previewOrchestratorUndo/confirmOrchestratorUndo`；签名分别使用已定义请求/返回类型；私有`orchestratorResult<T>(response: ApiResponse<T>): T`验证success及非空data。

| Method / `/api/learning/orchestrator`后缀 | Body / 返回与副作用 | 客户端签名（返回Promise） |
|---|---|---|
| GET `/capabilities` | enabled、rule_version、limits；无写入、无数据库路径/密钥 | `getOrchestratorCapabilities(): Promise<OrchestratorCapabilities>` |
| POST `/snapshot` | ScopeRequest → 有界公共证据摘要与TaskProjection；无写入 | `readOrchestratorSnapshot(scope: ScopeRequest): Promise<OrchestratorSnapshot>` |
| POST `/preview` | PreviewRequest(scope, expected_evidence_revision, options) → SchedulePreview；仅确认令牌 | `previewOrchestratorSchedule(request: PreviewRequest): Promise<SchedulePreview>` |
| POST `/confirm` | ConfirmRequest → OperationReceipt；保存日安排/操作/审计 | `confirmOrchestratorSchedule(request: ConfirmRequest): Promise<OperationReceipt>` |
| GET `/today` | 当前上海日DayView；没有确认安排返回not_confirmed，不自动造任务 | `getOrchestratorToday(): Promise<DayView>` |
| GET `/operations/{request_key}` | 原回执或404；不重新执行 | `findOrchestratorOperation(requestKey: string): Promise<OperationReceipt>` |
| POST `/operations/{operation_id}/undo-preview` | 严格空对象 → UndoPreview；仅令牌 | `previewOrchestratorUndo(operationId: string): Promise<UndoPreview>` |
| POST `/operations/{operation_id}/undo-confirm` | token、request_key、confirmed=true → OperationReceipt | `confirmOrchestratorUndo(operationId: string, request: UndoConfirmRequest): Promise<OperationReceipt>` |

- [x] Step 1: 写`test_auth_and_tenant_boundaries`、`test_disabled_keeps_history_readable`、`test_strict_json_and_unknown_or_repeated_query`、`test_stale_scope_409_and_storage_503`、`test_preview_and_operation_quotas_429`、`test_generic_artifact_patch_rejects_reserved_types`、`test_api_prefix_uses_existing_gateway_rules`；客户端测试用现有typescript包AST提取新增8个导出函数及其私有orchestratorResult函数与orchestratorRoot常量，transpile后注入HTTP替身执行函数体；不初始化import.meta.env或全局Axios拦截器。要求原参数完整发送、路径ID编码、读取/写入超时分别15/30秒、失败不上报成功，不以源码关键词匹配代替行为断言。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_api.py -q`及`node --test filemate/web/tests/orchestrator-api.test.mjs`。Expected: 新路由404/函数缺失等目标FAIL；沿用当前Node test runner与TypeScript编译器，不添加测试框架。
- [x] Step 3: 挂载前缀`/api/learning/orchestrator`的薄路由，客户端同前缀；现有Vite、Caddy、Nginx的`/api/`规则已存在，不增第二套转发路径。沿用现役身份/CSRF/origin边界、错误envelope、no-store，拒绝未知或重复查询参数；SQLite故障503保留客户端输入。开关关闭不改变任何旧路由。更新环境示例/API文档与Ruff检查目录，不新增Vue界面或客户端本地伪回执。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator -q`、`node --test filemate/web/tests/orchestrator-api.test.mjs`和`npm --prefix filemate/web run build`。Expected: 全部PASS、类型/构建通过；既有账号、错题、图谱路由合同不变。
- [x] Step 5: Commit `feat(orchestrator): 接通学习决策API与共享类型`。

### Task 6: 旧SQLite、范围容量与故障兼容（B6）

**Files:** Create `scripts/acceptance/orchestrator_runtime.py`、`orchestrator_performance.py`、`filemate/tests/orchestrator/{test_runtime,test_capacity}.py`。

**Interfaces:** Consumes任务1—5；Produces runtime/performance JSON证据。CLI：`uv run python -m scripts.acceptance.orchestrator_runtime --sqlite _working/wrongbook-e-20261029/sqlite3.exe --out _working/orchestrator-b-20261031/runtime-1`；`uv run python -m scripts.acceptance.orchestrator_performance --out _working/orchestrator-b-20261031/performance-1`。runtime另支持`--probe-only --db <明确路径> --out <非已有JSON>`，只以SQLite URI mode=ro记录实际Python/SQLite/JSON1/变量上限/schema、表/索引、release标识，不调用init_schema、不输出行内容或任何凭据。提供`--self-test --out <新的候选目录_working子目录>`，用当前解释器的SQLite模块运行任务1—5的合成快照/调度/确认/重放/撤销，不读生产DB、不依赖pytest。结果区分probe_only、cli_sql_subset和full_application。

- [x] Step 1: 写`test_runtime_probe_cannot_migrate_or_write`、`test_schema36_unchanged_by_schedule`、`test_runtime_cli_rejects_missing_or_wrong_engine`、`test_no_json1_and_malformed_records`、`test_large_scope_reports_counts_without_cross_scope_fallback`。容量数据为100/1000/10000道原创合成错题，并放入另一课程大量排在前面的记录。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_runtime.py filemate/tests/orchestrator/test_capacity.py -q`。Expected: 缺CLI入口或相应兼容性断言FAIL。
- [x] Step 3: 在实际3.26引擎执行本阶段涉及的SQL、确认/重放/撤销SQL事务和完整性检查；本机Python仓储回读只作为另一个证明，不冒称旧Python完整运行。记录34→36升级路径既有迁移行为、业务schema仍36、FK/integrity、无JSON1分支与坏数据处理。新脚本只输出到新的项目_working子目录，拒绝覆盖。
  容量记录冷/暖、四并发、P50/P95/最大值、SQL数量和候选/响应尺寸；暖请求与四并发P95预算500ms，响应≤512KiB，输出候选≤200/选中≤20，计数准确且truncation明确。范围查询在LIMIT前过滤，不因200条限额漏掉范围后方数据而声称完整。超限记录真实P2并修复，不改阈值冒充通过。
  通过现有服务器连接方式只读取得**当时实际生产**探针；使用同一实际服务解释器/SQLite，在隔离候选目录执行本脚本`--self-test`，仅操作自建合成库，不切换生产服务或启动第二个公网服务。CLI旧引擎执行不了Python注册的UDF时明确记为SQL子集证明，不能称为完整应用已兼容。若未取得探针或未在匹配的完整目标运行时完成合成服务验证，保留实际生产兼容待验；禁止以旧发布报告或Windows 3.26替代。其余B工作可继续，但B6完整生产兼容不得标PASS，更不能上线。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator -q`、上述两CLI（旧引擎当前候选路径`_working/wrongbook-e-20261029/sqlite3.exe`，先核对版本与来源SHA；引擎不随源码交付，缺失或版本不符时本项未完成，不能用mock替代运行成功）。Expected: 本地合同/旧引擎/容量全部PASS；生产探针及匹配解释器的隔离self-test另列，仅有版本信息或CLI子集不能完成B6。
- [x] Step 5: Commit `test(orchestrator): 验证旧运行时与限域容量边界`。

### Task 7: B级端到端、备份恢复与阶段交付

**Files:** Create `scripts/acceptance/orchestrator_journey.py`、`filemate/tests/orchestrator/test_journey.py`、`docs/LEARNING_ORCHESTRATOR_2_0_B_DELIVERY.md`与本阶段审计目录；Modify `README.md`、`docs/CURRENT_DELIVERY_INDEX.md`、`docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md`。

**Interfaces:** Consumes任务1—6；Produces完整B级工程候选和可重跑合成证据（API阶段，无新增Vue工作台）；CLI `uv run python -m scripts.acceptance.orchestrator_journey --out _working/orchestrator-b-20261031/journey-1`。运行原有接口完成真实领域写入，新决策层只做安排与依据。

- [x] Step 1: 写`test_goal_to_schedule_to_completion_and_restart`、`test_restore_keeps_references_but_invalidates_tokens`、`test_delete_one_source_only_stales_affected_schedule`、`test_api_via_dev_proxy_returns_json_for_both_accept_headers`。至少覆盖：创建两个课程与多个目标→明确今日优先目标→候选与依据→确认→减少预算→预览重排→去重→在原错题/计划/目标接口执行→刷新重启→查看证据→撤销安排不撤销已完成学习。
- [x] Step 2: Run `uv run pytest filemate/tests/orchestrator/test_journey.py -q`。Expected: 缺journey入口或跨域/恢复断言FAIL；不得用手改数据库模拟最终用户完成流程。
- [x] Step 3: 实现合成验收驱动及真实HTTP请求，模拟失联重试/DB503/过期token；启动自有隔离backend/Vite子进程，通过前端代理请求新API，Accept=application/json与text/html均须返回JSON，结束只关闭自有进程；用既有托管与个人备份机制恢复到新隔离目录并拒绝覆盖，核对完整记录与来源指纹。前三专项数据前后逐表/有序行摘要保存；预览和确认不得修改领域表，只有原领域提交带来预期变化。导出不含密钥，删除资料后不能从操作Artifact恢复原文或继续声称旧依据有效。
- [x] Step 4: Run `uv run pytest filemate/tests/orchestrator -q`、`uv run python -m scripts.acceptance.orchestrator_journey --out _working/orchestrator-b-20261031/journey-1`、`powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`。Expected: 定向、端到端及全项目门禁全部PASS；读取日志而非推定旧1820/302仍适用。新API类型构建和既有前三专项测试均进入本次门禁。
- [x] Step 5: 自查本计划覆盖，完成一次独立全范围审阅；Important/Critical以可复现测试修复，一次修复后回归，不循环重复审阅。交付记录实际提交、运行时、开关/关闭回退、确认与撤销手册、API、无迁移证明、容量、失败恢复、未完成条件；不把合成结果称为真人学习效果。
- [x] Step 6: Commit `docs(orchestrator): 归档B级联调与阶段交付证据`。停止于B级报告，等待用户确认B级通过后才进入C，不推送部署。

## B级退出清单与覆盖自检

| 原任务 | 所属任务及必须具备的证据 |
|---|---|
| B1证据快照与作用域 | 任务1；同一事务、跨课程/空间隔离、真实来源/时间、面试分不混用 |
| B2身份/去重/完成保护 | 任务2、4、7；动作身份、来源汇合、非复合误合、重试/周期/历史保护 |
| B3推荐理由可解释 | 任务3；稳定规则、真实引用、无模型与无伪造统计 |
| B4时间/固定/延期 | 任务3、4；0分钟、超预算、固定顺序、已完成不重置、延期明细 |
| B5预览/确认/回执/撤销 | 任务4、5、7；事务、CAS、异body重放、并发、丢响应、恢复旧token、源删除 |
| B6实际兼容条件 | 任务6；旧引擎真实SQL、无JSON1、实际生产探针、schema/升级与完整恢复 |
| 验收主链与前三专项保护 | 任务7及全量门禁；合成账号/HTTP真逻辑、重启恢复、既有数据指纹和原功能回归 |

自检要求：所有消费的类/函数均在前置任务产生；新增文件名与命令先核对；五项Review Focus分别有测试；各Task先RED后GREEN再提交。没有生产探针与匹配完整运行时self-test、没有实际旧引擎/恢复，或存在未修复Important/Critical时，报告保持条件通过或未完成，不能仅凭测试数量宣布B级全部通过。

2026-11-01执行进度：用户已确认逐项实施与一次独立审阅。任务1—6及任务7实现已完成；a7422ec修复独立审阅六项Important，目标解释器完整应用／34→36合成迁移／旧代码恢复通过。任务7与全项目门禁完成：1897项后端／304项前端、类型／构建／体积通过；证据归档于docs/audits/learning-orchestrator-b-2026-10-31/verification.json。B仍待用户验收，C—E未开始。B不新增迁移不代表现主站34无需升级至候选36。
