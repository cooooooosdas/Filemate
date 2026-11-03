# Learning Orchestrator D级学习教练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已选择当前会话由实施者连续完成各任务、最后一次独立审阅，不重新选择执行方式。

**Goal:** 在今日行动提供有依据、规则可离线、模型单次授权的学习教练，并把用户采纳的短任务和未来七天安排一次确认、原子保存、保护式撤销。

**Architecture:** 复用同进程决策服务、现有证据快照、StudyPlan、日安排Artifact、data_actions及模型治理适配层。新增独立coach包管理最小证据、结构化建议和持久请求；建议不能直接调用工具或写正式计划。模型调用在业务事务外，正式写入只走联合命令。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、SQLite 3.26兼容、Vue 3、TypeScript、现有BoundedLLMRunner和Node测试工具；不新增依赖、外部服务或默认付费调用。

**Spec:** [2026-11-02-learning-orchestrator-d-design.md](../specs/2026-11-02-learning-orchestrator-d-design.md)。原任务书为 `C:/Users/胡希/.codex/attachments/7841a6a3-3b50-45cd-8996-97b11c136836/pasted-text-1.txt` 的D1—D8、D级验收和第04节。用户已确认完整设计及本九项详细计划；**当前会话连续逐项实施，最后一次独立审阅，不在任务间重复询问。** 当前执行账本为`_working/learning-coach-d/progress.md`；未勾选项仍待完成。

## Global Constraints

- 基线业务源码fdf6f40，业务schema36／治理3；本分支已有设计与容量调查文档提交，不把它们算作产品实现。
- 上阶段第三版与第四版A—C已上线；D仅本地开发，默认关闭；D验收后才进入E，新上线另按阶段授权。第三版Linux万题容量P2仍开放，不因D完成而关闭。
- “每批最多7条新动作，未来最多7个自然日”；使用上海日期，窗口为实际今天至今天+6天；每个自然日最多一组，按日期递增。
- “日预算之和不得超出用户当日预算，0分钟可返回空建议”；保留完成状态、固定位置和原任务身份。原C候选200／选中20的限制继续适用。
- 当前目标、最多20份资料、一门课程；显式选择最多3场面试、10份编程提交、5个概念。错题最多3组题目／原答片段，每段500字；面试最多3个反馈项，每项500字。
- “总上下文最多24000字符，序列化消息最多64KiB”；覆盖不足明确显示。默认不外发代码、录像、录音、简历、面部信息、整场面试或全库资料。
- 模型“最多2次真实上游尝试，每次最多20秒，整次硬墙钟60秒、输出最多3500tokens”；每天最多30次新教练请求，同空间最多1个运行中的模型请求，租约120秒。
- 复用治理账本的滚动24小时30次准入，使用全空间固定教练桶，作为每日上限的保守实现；API明确返回quota_window=rolling_24h，不把它显示成午夜清零。额度不随个人备份回退。
- 确认令牌15分钟；预览、确认、撤销均绑定当前证据、实际上海日期、恢复epoch和所有受影响日修订。原成功回执重放不重新执行。
- 新增部分保存为至多一份关联当前目标的新StudyPlan，旧计划不覆写；原日完成序号仍在study_plans.completed_days，原题结果仍在原模块。
- 预期零迁移，不改v1—v36迁移；若需表／列或新增服务费用，先提交具体设计差异，停止依赖该差异的实现。
- 保留四主题、无衬线大字、SVG、44px控件与懒加载；不扩大143360字节首包gzip预算，不更换框架、字体或图标库。
- 保留23份既有用户测试修改；只暂存明确列出的自有文件，不运行git add .，不清理用户资料或生产数据库。

## Review Focus

1. 显式选择的记录刚被重答、删除、移出课程或改错因：旧建议不可确认，迟到模型结果不可复活正文；由任务1、3、5测试。
2. 无资料目标和含多来源的短计划：只读取本目标且依赖全在范围内的计划，不把source_id=null当全空间许可；由任务1、4测试。
3. 上海午夜、近到期复习和未来第七天：实际证据时钟不前移，旧预览失效，历史成功回执仍可恢复；由任务2、4、8测试。
4. 确认已提交但响应丢失，随后切身份／恢复备份／另页修改：恢复只读原键，不补发确认，不把旧回执当新目标结果；由任务3、4、6、8测试。
5. 随机模型输出和资料内恶意指令：不生成任意路由、工具、统计或能力判断；坏增强保留规则结果，额度与子进程始终有界；由任务2、3、6测试。

## 文件职责与影响范围

| 职责 | 新增／修改文件 | 保护边界 |
|---|---|---|
| 合同与最小上下文 | 新增`filemate/study/orchestrator/coach/{__init__,models,context,evidence,catalog}.py`；修改`orchestrator/{context,snapshot_queries,task_views}.py` | 不扫描全空间原答，不改变原评分与错题调度 |
| 规则与模型校验 | 新增`coach/{rules,output,prompts}.py` | 不让模型生成可执行URL或个人统计 |
| 持久工作流 | 新增`coach/{repository,service,settings}.py`；修改`execution/storage.py`的Artifact保护 | 不在模型请求中持有SQLite写事务 |
| 计划与多日命令 | 新增`coach/{plans,commands}.py`；修改`orchestrator/{repository,task_views,snapshot_queries}.py` | 与C共用day_id，不另建完成真源 |
| 隐私与恢复 | 新增`coach/privacy.py`；修改`orchestrator/privacy.py`、`course_graph/privacy.py`、`operations/personal_backup.py`、`programming/privacy.py`、`career/repository.py`的岗位删除及`server.py`的面试清空／删除接线 | 通用导出、删除预览、来源派生、迟到结果与恢复一致 |
| HTTP与凭据 | 新增`coach/api.py`；修改`server.py`、`llm_client/request_credentials.py`、API_SPEC及环境变量样例 | 仅模型request路由临时接收浏览器密钥 |
| 前端状态 | 新增`web/src/types/learning-coach.ts`、`services/learning-coach-api.ts`、`today/coach-{state,commands,presentation}.ts` | 正文仅内存；持久恢复定位符不带正文、密钥或令牌 |
| 前端视图 | 新增`components/today/Coach{Panel,Evidence,Proposal}.vue`；修改`TodayWorkspace.vue`、`today/today.css`、`views/GoalPlanner.vue`、`services/{api,llm-vault}.ts`及现役开关类型声明 | 按需入口、按需加载；现有今日行动和原功能导航继续可用 |
| 验收与交付 | 新增`tests/orchestrator/coach/`、`web/tests/learning-coach-*.test.mjs`、`scripts/acceptance/learning_coach_{fixture,journey,runtime,performance}.py`、`evaluation/evaluate_learning_coach.py`与专用合成fixtures | 合成回归、实际上游调用、真人实验分开记账 |

允许修改上述模块的直接调用方与既有对应测试以保持合同一致；不重构整个server或storage，不触碰用户23份测试正文。新增文件仅在所属任务需要时创建，不预建空壳。以下类型及签名是任务间合同；实施时如发现合同无法满足现役约束，先修订本计划并说明原因。

## 固定合同

Python公共类型统一定义在`coach/models.py`，请求继承现役StrictRequest，禁止extra字段、布尔冒充整数、重复ID和重复JSON键。ID沿用Identifier；请求键16—80个字母数字／下划线／连字符。

| 类型 | 字段与约束 |
|---|---|
| `CoachSelection` | interview_ids≤3、submission_ids≤10、concept_ids≤5、wrong_ids≤3；feedback_refs≤3，每项为interview_id、attempt_id、feedback_item_id、expected_revision。job目标另可显式选position_id或null及最多5个requirement_indices（0—29），仅读该岗位保存的所选要求，不读岗位匹配分。各ID／索引唯一，feedback_refs必须属于显式所选场次 |
| `CoachDayInput` | study_date为规范YYYY-MM-DD字符串；options为现役ScheduleOptions。日期窗由服务器真实时间核验，日期不修改as_of |
| `CoachInput` | scope:ScopeRequest、selection:CoachSelection、intent:`budget/exam/error_cause/tomorrow/next_step`、question:str≤2000、days:list[CoachDayInput]长度1—7、按日期唯一递增 |
| `CoachFact` | fact_id、kind、record_id、revision、observed_at、display_text、data；kind限goal/source/attempt/review/cause/concept/relation/interview_feedback/compiler_result/position_requirement/plan。原文片段仅在选择后加入，data为相应kind的严格类型，不开放任意dict给模型 |
| `CoachTarget` | kind:`source/question/concept/interview/problem`、id、revision，question额外含artifact_id／question_index，concept含course_id，interview含attempt_id，problem含problem_version。只允许匹配对应动作的字段，不接受完整原答／代码 |
| `CoachContext` | input:CoachInput、as_of、context_revision、restore_epoch、snapshot:EvidenceSnapshot、projection:TaskProjection、facts:list[CoachFact]、coverage、external_payload、external_digest。as_of用于事实采样；外发体只含稳定、选定字段和实际study_date，不含精确采样时钟／隐藏快照 |
| `CoachRequest` | input、expected_context_revision、request_key、mode:`rule/llm`、allow_external_model:bool默认false、consent_digest:str或null；llm必须为true且digest匹配当前将外发的external_payload |
| `CoachAction` | action_key、action:`read_source/review_question/train_concept/rehearse_interview/practice_problem`、target_ref、method_code、study_date、minutes:1—240、fact_ids；目标、动作与来源必须由服务器映射，模型不输出route或自由任务身份 |
| `CoachProposal` | rule_version、prompt_version、facts、explanations、days、new_actions≤7、coverage、overlaps、limitations；days每项为CoachDayInput加schedule:ScheduleResult；explanations由task_id／fact_ids／reason_code／method_code渲染，服务器事实和方法建议分栏 |
| `CoachRunView` | work_id、request_key、status:`running/ready/failed/cancelled/interrupted/stale`、requested_mode、effective_mode:`rule/model/rule_fallback`、model_status:`not_requested/running/succeeded/failed/cancelled/interrupted`、safe_error_code、context_revision、proposal或null、版本及实际provider/model。ready只表示可用建议，不表示模型必定成功 |
| `CoachDraft` | work_id、expected_context_revision、days:list[CoachDayInput]、new_actions:list[CoachAction]、overlap_choices:list[{original_task_id,keep:`original/proposed`}]；候选原文编辑在UI中形成这些有限字段，不接受任意计划JSON |
| `CoachPreview` | draft、as_of、issued_study_date、day_revisions、new_plan_id或null、new_artifact_id或null、resolved_actions、changes、confirmation_token、expires_in_seconds=900 |
| `CoachConfirm` | CoachDraft加现役Confirmation字段；request_key是独立操作键，不能与建议请求键混用 |
| `CoachReceipt` | operation_id、request_key、status:`confirmed/undone`、study_dates、day_revisions、plan_id或null、affected；不带原答、模型正文或确认令牌 |
| `CoachUndoPreview` | operation_id、issued_study_date、day_revisions、plan_revision、confirmation_token、expires_in_seconds=900；撤销确认复用UndoConfirmRequest |

上下文修订排除易变as_of本身和本功能新写的请求／结果／预览控制记录，但包括实际日期、所有相关原记录完整修订、到期／完成事实、输入选择和恢复epoch；不能只哈希截断500字后的显示文本，也不能用全库data_version导致本功能每次认领都使自己失效。外发digest与context_revision不同：前者证明用户看见的确切最小消息，后者保护未外发的完成／固定等事实。工作区restore_epoch和单请求随机claim_epoch分开；`read_restore_epoch(conn) -> str`由context.py定义，缺少运行态Artifact时只读返回`initial`，首次认领持久化相同值。恢复无论备份有无该Artifact都写入新的随机restore_epoch，不能回到initial。

模型结构`CoachModelOutput`仅含`explanations`、`task_order`、`new_actions`三个字段。new_actions元素为`CoachActionCandidate`，字段为action、target_ref:CoachTarget、method_code、study_date、minutes、fact_ids，刻意不含action_key，由服务器推导真实身份。reason_code限`due_review/confirmed_cause/confirmed_dependency/selected_feedback/compiler_result/selected_requirement/goal_step`；method_code限`reread/trace_error/compare_cases/retry_independently/rehearse/practice`。每对原因／动作只能用于相符的typed fact，输出不允许个人计数、概率、自由URL、自由关系或新工具名。说明文字由服务器模板结合所选原句渲染，不能把格式核验写成教学建议正确性证明。

持久化类型固定为`learning_coach_request`（去重控制／无正文墓碑）、`learning_coach_result`（建议与所选证据）、`learning_coach_runtime`（epoch／模型活动租约）、`learning_coach_operation`（确认与撤销回执／前态引用）。新短计划Artifact继续用`study_plan`，plan_data与metadata增加命名空间`learning_coach`，含goal_id、work_id、operation_id、action_keys、日期分组和依赖ID／修订；不另建任务主表。

## Task 1: 目标类型、最小证据与有界选择目录

**Files:** 新增`coach/{__init__,models,context,evidence,catalog}.py`、`tests/orchestrator/coach/{__init__,conftest,test_context,test_catalog}.py`；修改`orchestrator/{context,snapshot_queries}.py`、`study/goal_planner.py`、`server.py`目标参数、`web/src/{views/GoalPlanner.vue,services/api.ts}`的skill枚举／标签，以及`filemate/docs/API_SPEC.md`目标合同。

**Interfaces:** `CoachContextReader(storage, *, clock=None).read(input: CoachInput) -> CoachContext`；`read_in_transaction(read, input: CoachInput, *, as_of: datetime, restore_epoch: str) -> CoachContext`。`read_coach_catalog(storage, request: CoachCatalogRequest) -> CoachCatalogPage`：request为scope、kind:`interview/submission/concept/wrong/position`、q≤120、offset≤1000000，固定30条元数据／页；page含items／total／offset／limit=30，item仅id／label／updated_at／revision／valid／source_id或null。`read_goal_plans(conn, goal_id: str, source_ids: list[str], course_id: str | None) -> tuple[list[dict], dict]`补充明确目标关联计划，普通旧计划仍由read_plans读取，按plan_id合并去重。

测试夹具在本任务conftest.py定义：`coach_case`返回本空间storage、可控aware clock、合法CoachInput、另一课程／空间的拒绝用ID；复用上级world的真实SQLite／原始合成资料。后续`coach_context`由真实reader生成，`coach_request`由该上下文构造，`ready_run`由真实rule服务生成；confirm_body由真实预览构造，不用固定成功回执替代。

- [x] **1.1 写RED测试**：`test_selected_context_is_one_snapshot_and_minimal`断言另一课程／空间的ID拒绝，改首500字之外的原答也改变修订；未选择不返回secret原答／代码／视频／简历。`test_empty_scope_reads_only_linked_goal_plans`断言无资料时只出现当前goal_id的无来源关联计划；有资料时任一依赖越界则排除。`test_feedback_needs_selected_current_attempt`断言重答后旧feedback_refs拒绝。`test_catalog_pages_metadata_only`断言30条、稳定分页、q按字面匹配，损坏记录标无效，禁止整库正文扫描。`test_skill_goal_round_trip_and_legacy_goal_types`断言skill标签“能力训练”、新建／重读及旧五类不变；schema仍36。

```python
def test_selected_context_is_one_snapshot_and_minimal(coach_case):
    context = CoachContextReader(coach_case['storage'], clock=coach_case['clock']).read(coach_case['input'])
    assert context.input.scope.goal_id == coach_case['input'].scope.goal_id
    assert 'synthetic-secret-code' not in json.dumps(context.external_payload)
    assert len(json.dumps(context.external_payload, ensure_ascii=False).encode('utf-8')) <= 65536
```
- [x] **1.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_context.py filemate/tests/orchestrator/coach/test_catalog.py -q`。预期新接口不存在或上述行为断言失败；先修测试环境错误，不能把环境错误当业务RED。
- [x] **1.3 实现最小读取**：在一个只读事务内复用SnapshotReader，针对显式ID分别SELECT有界原记录；编程只采信completed且active、题目版本仍有效的服务端compiler结果，不调用会读取全部代码的CodingRepository.evidence。面试取最后实际回答及选定反馈版本，不改变分数；错因只采信人工确认。岗位只从同空间CareerRepository保存记录读取用户选中的要求和来源／版本，不取比较分、画像或全量职位描述，不发起爬取；岗位关闭／删除／要求修改使旧上下文失效，未选岗位明确未关联。对超限返回422，对越权／删除返回不泄露存在性的404或scope_changed409。
- [x] **1.4 验证GREEN**：运行1.2及`uv run pytest filemate/tests/orchestrator/test_context.py filemate/tests/orchestrator/test_snapshot.py filemate/tests/test_career_planning.py -q`；证明上下文24000字符／消息64KiB、片段上限和覆盖说明，无法容纳的内容不静默发送。来源选择与目录读取均零模型调用。
- [x] **1.5 提交**：仅暂存本任务自有路径，提交`feat(coach): 接通显式目标与最小学习证据`。保留RED／GREEN摘要于`_working/learning-coach-d/task1/`。

## Task 2: 规则建议、结构化增强与真实日期调度

**Files:** 新增`coach/{rules,output,prompts}.py`、`tests/orchestrator/coach/test_{rules,output}.py`；必要时给`orchestrator/scheduler.py`增加仅供coach使用的显式目标日参数，原调用默认行为保持不变。

**Interfaces:** `build_rule_proposal(context: CoachContext) -> CoachProposal`；`build_model_messages(context: CoachContext) -> list[dict[str,str]]`；`validate_enhancement(context: CoachContext, baseline: CoachProposal, raw: object) -> CoachProposal`；`render_explanation(reason_code: str, method_code: str, facts: list[CoachFact]) -> str`。`CoachModelOutput`及原因／方法适用矩阵定义于output.py，Prompt版本`learning-coach-v1`，规则版本`learning-coach-rules-v1`。

- [x] **2.1 写RED测试**：`test_five_intents_keep_evidence_and_budget`参数化五种请求、0／40／1440分钟；已固定不能移动，已完成不返待办，任务无估时不得靠0分钟塞入预算。`test_future_date_keeps_real_as_of`断言今天+6合法、+7与昨日拒绝，未来复习标届时计划、当前仍not_due。`test_duplicate_action_reuses_origin_and_cycle`断言换标题／顺序不产生第二动作，新复习周期可有不同action_key。`test_invalid_enhancement_preserves_rule_result`参数化未知ID、跨课依赖、未确认错因、个人分数、URL、额外字段、重复项和第8个新动作，整份增强拒绝。`test_selected_feedback_and_compiler_result_are_not_ability_scores`断言只生成练习方法，不改变课程排序或能力值。

```python
def test_five_intents_keep_evidence_and_budget(coach_context):
    proposal = build_rule_proposal(coach_context)
    assert len(proposal.new_actions) <= 7
    assert all(day.schedule.estimated_minutes <= day.options.available_minutes for day in proposal.days)
    assert len({action.action_key for action in proposal.new_actions}) == len(proposal.new_actions)
```
- [x] **2.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_rules.py filemate/tests/orchestrator/coach/test_output.py -q`，记录缺失行为。
- [x] **2.3 实现规则与校验**：既有任务复用project_tasks和build_schedule；新动作只来自允许的typed fact和固定方法，action_key绑定目标／课程／真实原ID／动作／复习周期。无证据明确不足，不给假错因。未来日单独重排可在届时使用的候选，证据截止保持当前时刻；规则和模型都按同一预算／去重／固定／依赖校验，现有任务加新动作共同计入日预算和20项上限。同一待办／周期不能在七天内重复安排。已固定项超预算或原安排不能保留时返回需用户解决的冲突，不静默延期固定项；普通复合计划仅列可能重叠，不自动判断等价。
- [x] **2.4 验证GREEN**：运行2.2和`uv run pytest filemate/tests/orchestrator/test_scheduler.py filemate/tests/orchestrator/test_task_views.py -q`。测试上海23:59→00:00、微秒到期及来源失效；模型无自由文本字段可伪造个人统计。输出携带覆盖与版本；规则结果在增强失败后仍可采纳。
- [x] **2.5 提交**：`feat(coach): 生成有依据的规则与受限模型建议`，证据存`_working/learning-coach-d/task2/`。

## Task 3: 持久请求、真实模型调用、准入与取消

**Files:** 新增`coach/{settings,repository,service}.py`、`tests/orchestrator/coach/test_{requests,model_runtime}.py`；修改`execution/storage.py`保护四种coach Artifact；只在需要安全复用时修改`runtime_governance.py`的教练准入封装，不更改治理schema／旧额度。

**Interfaces:** `CoachService(storage, *, clock=None, config_factory=None, runner=None)`；`request(body: CoachRequest) -> CoachRunView`、`get(request_key: str) -> CoachRunView`、`cancel(request_key: str) -> CoachRunView`。`CoachRepository(storage, *, clock=None)`提供`find(request_key, input_digest)`、`claim(body, context)`、`authorize_claim(work_id, claim_epoch, *, admitted: bool)`、`finish(work_id, claim_epoch, proposal, *, model_status, safe_error_code=None)`；返回的内部claim包含claimed、claim_epoch、lease_until，不能出现在API正文。模型调用复用BoundedLLMRunner.run的现役签名。

- [x] **3.1 写RED测试**：`test_same_key_never_calls_twice`用真实SQLite并发连接＋计数runner断言同键同正文只一次、冲突409；`test_pending_admission_race_does_not_interrupt_owner`在业务认领和独立账本准入之间阻塞，第二请求只能读取running，不得把首请求改interrupted。`test_admission_survives_restore_and_missing_local_receipt`断言固定教练桶第31次429、恢复后额度不回退，已准入但本地正文丢失时返回interrupted而非再调用。`test_model_does_not_hold_write_transaction`在慢runner执行中独立提交其他业务写入；`test_concurrent_models_are_per_space_and_bounded`断言同空间仅一个模型、其他空间独立。`test_cancel_or_expired_epoch_cannot_publish`覆盖取消、120秒租约过期、来源删除／恢复／跨日；`test_failure_has_real_status_and_rule_fallback`覆盖无密钥、坏JSON、配额、超时及供应商异常。

```python
def test_rule_replay_is_persistent(coach_service, coach_request):
    first = coach_service.request(coach_request)  # 该夹具mode=rule。
    replay = coach_service.request(coach_request)
    assert replay.work_id == first.work_id
    assert replay.model_status == 'not_requested'
    assert coach_service.get(coach_request.request_key).proposal == first.proposal
```
- [x] **3.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_requests.py filemate/tests/orchestrator/coach/test_model_runtime.py -q`。
- [x] **3.3 实现工作流**：先读原键，再校验范围和用户所见context_revision／consent_digest；业务短事务先认领受保护请求／结果和120秒租约，记录内部admitting状态。唯一本次claim拥有者在事务外用default_scope身份及BudgetStore.admit_learning、固定桶`learning-coach:v1`准入；第二请求直接读原running，不再准入。账本仅含摘要；准入后再短事务authorize_claim核对claim_epoch／restore_epoch。准入已存在但本地原claim消失时中断，不重调；两个账本间崩溃只能消耗一次保守额度，不能产生未准入模型调用。模型在事务外同步执行，HTTP等待由线程池承载，不添加后台队列。每次只调用一次runner，worker内部最多重试一次；60秒硬截止且取消回收自己持有的子进程。完成时重新读取当前证据和epoch，过期或变化只记stale／interrupted，不写迟到正文。
- [x] **3.4 实现安全落盘**：请求控制Artifact仅保存正文摘要、状态／安全码／epoch等必要去重字段；结果Artifact保存最小依据与建议并登记全部来源依赖。来源删除后保留无正文墓碑，同键不能重新外发。失败不保存原异常／Prompt／密钥；ready+rule_fallback与model_status=failed明确分开。rule不调用config_factory或runner，断网仍能完成本地路径。
- [x] **3.5 验证GREEN**：运行3.2与现役`filemate/tests/wrongbook/test_analysis_privacy.py`、`filemate/tests/test_runtime_governance.py`、`filemate/tests/test_llm_client.py`。增加真实本地失败HTTP服务／私有worker测试，证明总尝试≤2、输出3500tokens、60秒墙钟上限及进程回收；只有mock的测试不算真实运行时证明。
- [x] **3.6 提交**：`feat(coach): 固定请求认领与有界模型工作流`，证据存`_working/learning-coach-d/task3/`。

## Task 4: 新短计划与未来安排的联合确认及保护式撤销

**Files:** 新增`coach/{plans,commands}.py`、`tests/orchestrator/coach/test_{commands,plans}.py`；修改`orchestrator/{repository,snapshot_queries,task_views}.py`，只给日读取增加兼容入口，不改原C写入合同。

**Interfaces:** `CoachCommands(storage, *, clock=None).preview(draft: CoachDraft) -> CoachPreview`、`confirm(body: CoachConfirm) -> CoachReceipt`、`find(request_key: str) -> CoachReceipt | None`、`preview_undo(operation_id: str) -> CoachUndoPreview`、`confirm_undo(operation_id: str, body: UndoConfirmRequest) -> CoachReceipt`；`CoachDayReader(storage, *, clock=None).read(study_date: str) -> DayView`。`build_short_plan(context: CoachContext, draft: CoachDraft, *, plan_id: str, artifact_id: str) -> dict`返回现役StudyPlan格式；`write_short_plan(conn, plan: dict) -> None`要求现有事务，不自行commit。

- [ ] **4.1 写RED测试**：`test_preview_creates_no_study_plan`；`test_joint_confirm_rolls_back_every_write`在计划、来源绑定、第二日安排、回执、审计处逐一注入失败，断言全部业务写入为零、旧计划哈希不变。`test_two_tabs_compare_all_day_revisions`断言两个coach或coach与C同日竞争仅一个成功；`test_replay_before_revalidation_returns_original_receipt`在证据变化／跨日后同键恢复仍原回执。`test_undo_rejects_any_started_plan_or_changed_day`断言完成任一日、保存原功能执行证据、后改任一日或编辑新计划后整体拒绝，不部分撤销。`test_plan_day_grouping_and_goal_link`断言同日多动作只一学习日、正确completed_days含义、无来源／多来源计划读取隔离。

```python
def test_preview_creates_no_study_plan(coach_case, coach_draft):
    storage = coach_case['storage']
    before = storage._conn().execute('SELECT count(*) FROM study_plans').fetchone()[0]
    preview = CoachCommands(storage, clock=coach_case['clock']).preview(coach_draft)
    assert preview.expires_in_seconds == 900
    assert storage._conn().execute('SELECT count(*) FROM study_plans').fetchone()[0] == before
```
- [ ] **4.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_commands.py filemate/tests/orchestrator/coach/test_plans.py -q`。
- [ ] **4.3 实现联合命令**：预览为有限新计划／Artifact／动作预分配稳定ID，保存于受保护建议结果中，并将全部待写正文摘要、原任务修订、重叠选择、目标、来源、完成／固定、epoch、签发上海日期及所有日CAS绑定到令牌。一个BEGIN IMMEDIATE事务内写至多一份新StudyPlan、来源关联、原day_id(date)的日Artifact、不可变coach回执及data_actions.finish；任一步失败回滚。跨日拒绝未用令牌；原键先查回执，禁止重复创建或挪到今日。
- [ ] **4.4 实现读取／撤销**：当日C工作台能投影coach所建原格式计划和最新操作定位，未知旧字段保持兼容；新短计划沿用原按日执行单位，内部training_actions定位原功能，不能再把同一动作重复投影成第二个独立待办。未来目标日读取用显式date，as_of仍真实。允许用户编辑days／预算后基于原work输入重新核验证据，再按新draft重算并绑定新预览，不要求为人工改预算再调用模型。撤销预览绑定全部日修订／新计划内容和实际执行证据；确认仅归档本批尚未开始的新计划并恢复本批未后改的安排。原计划、答题、面试和编程结果不删除；“自报完成学习日”不增加答对次数。
- [ ] **4.5 验证GREEN**：运行4.2与`uv run pytest filemate/tests/orchestrator/test_commands.py filemate/tests/orchestrator/test_journey.py filemate/tests/orchestrator/test_task_views.py -q`；增加SQLite提交失败后的同键重试与未用撤销令牌跨上海日失效测试，确认旧C操作不会误撤销coach日写入。
- [ ] **4.6 提交**：`feat(coach): 原子确认短计划与多日安排`，证据存`_working/learning-coach-d/task4/`。

## Task 5: 多来源、面试／作答／代码依赖的删除与恢复

**Files:** 新增`coach/privacy.py`、`tests/orchestrator/coach/test_{privacy,restore}.py`；修改文件职责表中的隐私接线、`execution/storage.py`相关派生删除／Artifact保护，以及原答／错题现役删除入口。只连接现有删除操作，不新增静默批删入口。

**Interfaces:** `normalize_restored_coach(conn) -> None`；`invalidate_coach_dependencies(conn, *, kind: str, record_ids: list[str]) -> dict[str,int]`，kind限source/interview/attempt/submission/position/goal；`coach_dependency_impact(conn, *, kind: str, record_ids: list[str]) -> dict[str,int]`用于既有删除预览。均复用调用方事务；严禁内部commit。未删除但重答／修改／移出课程时由上下文修订令建议stale，实际彻底删除时清除对应派生正文并保留去重墓碑。

- [ ] **5.1 写RED测试**：`test_delete_either_source_purges_body_but_keeps_tombstone`覆盖两来源的无课程目标、请求运行中删除、私密句无法从结果／导出／历史回执取得。`test_interview_clear_and_attempt_delete_invalidate_derivatives`覆盖清空分析／删除场次／重答／错题清空／代码删除；迟到runner不可恢复正文。`test_generic_artifact_paths_cannot_forge_coach_authority`覆盖通用保存／编辑／导入／批量删除受保护Artifact；合法备份读取继续工作。`test_restore_rotates_epoch_without_resuming_or_refunding`覆盖running→interrupted、清令牌、旧结果不发布、原记录仍可读；备份故意含坏coach JSON不崩全站。

```python
def test_restore_rotates_epoch(coach_case):
    conn = coach_case['storage']._conn()
    before = read_restore_epoch(conn)
    with atomic(coach_case['storage']) as transaction:
        normalize_restored_coach(transaction)
    assert read_restore_epoch(conn) != before
```
- [ ] **5.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_privacy.py filemate/tests/orchestrator/coach/test_restore.py -q`。
- [ ] **5.3 实现派生与恢复接线**：来源关联复用kg_learning_artifact_sources，同步source_impact计数和显示标签；移出课程只使范围／引用失效，沿用已确认的“移出／彻底删除”区别。面试、原答、编程删除在原事务中移除依赖正文，不能仅在下次打开时隐藏。恢复转新epoch、清未用coach令牌、运行中改interrupted，并将个人恢复阻断条件扩展到活跃coach调用；关闭开关仍能导出、删除和重读。遍历派生记录要覆盖全部匹配项，不用LIMIT漏删。
- [ ] **5.4 验证GREEN**：运行5.2和`uv run pytest filemate/tests/course_graph/test_privacy.py filemate/tests/test_interview_coach_privacy.py filemate/tests/test_p1_personal_backup.py filemate/tests/test_p1_coding_privacy.py -q`。验证SQLite外键、旧schema36合成备份往返、来源依赖数与实际派生内容一致；若复用实体不能满足则按Global Constraints报告迁移差异。
- [ ] **5.5 提交**：`fix(coach): 阻断删除恢复后的旧建议与迟到写入`，证据存`_working/learning-coach-d/task5/`。

## Task 6: HTTP合同、开关与可信请求凭据

**Files:** 新增`coach/api.py`、`tests/orchestrator/coach/test_api.py`；修改`server.py`路由注册、`llm_client/request_credentials.py`、现有凭据相关合同测试、`filemate/docs/API_SPEC.md`及`.env.example`。不读取／提交实际.env。

**Interfaces:** `create_router(get_storage: Callable[[],SQLiteStorage]) -> APIRouter`，prefix=`/api/learning/orchestrator/coach`，复用DecisionRoute及现役认证／Origin。均返回`{success,data,error}`，no-store；JSON正文上限64KiB，意外query／路径字段严格拒绝。端点固定如下：

| 方法与相对路径 | 请求 → 响应／条件 |
|---|---|
| GET `/capabilities` | enabled、limits、quota_window、contract_version=`learning-coach-v1`、规则／Prompt版本；不调用模型 |
| POST `/catalog` | CoachCatalogRequest → CoachCatalogPage；只读，需要开关 |
| POST `/context` | CoachInput → CoachContext；只读，需要开关 |
| POST `/requests` | CoachRequest → CoachRunView；首次模型可能等待≤60秒，重复running返回202；创建需开关 |
| GET `/requests/{request_key}` | CoachRunView；开关关闭仍可重读；未知404 |
| POST `/requests/{request_key}/cancel` | 空StrictRequest → CoachRunView；关闭后仍可取消自己已运行的请求 |
| POST `/proposals/preview` | CoachDraft → CoachPreview；需要开关 |
| POST `/proposals/confirm` | CoachConfirm → CoachReceipt；新写需开关，关闭后可通过GET读取原成功回执 |
| GET `/operations/{request_key}` | CoachReceipt；关闭后可读 |
| POST `/operations/{operation_id}/undo-preview` | 空StrictRequest → CoachUndoPreview |
| POST `/operations/{operation_id}/undo-confirm` | UndoConfirmRequest → CoachReceipt；允许撤销关闭前已有操作，仍受全部保护条件约束 |
| POST `/day` | 严格`{study_date}` → DayView；关闭后可读已有保存结果，禁止用此入口生成新安排 |

- [ ] **6.1 写RED测试**：`test_coach_api_auth_origin_and_tenant_isolation`覆盖游客／账号、另一身份ID、未知记录及Origin；`test_strict_body_and_safe_errors`覆盖重复键、NaN、布尔minutes、超长／超64KiB、任意workspace/db_path/model_url、坏存储，响应不回显秘密。`test_flags_preserve_reads_cancel_and_safe_undo`覆盖两个后端开关AND关系、默认关闭及只读／取消／撤销。`test_only_requests_accepts_ephemeral_model_key`断言仅POST requests匹配白名单，其他读／确认／撤销不转发、不存密钥；无授权绝不调用。

```python
def test_only_requests_accepts_ephemeral_model_key():
    prefix = '/api/learning/orchestrator/coach'
    assert is_model_request('POST', prefix + '/requests')
    assert not is_model_request('POST', prefix + '/proposals/confirm')
    assert not is_model_request('POST', prefix + '/context')
```
- [ ] **6.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_api.py -q`。
- [ ] **6.3 实现API与文档**：`FILEMATE_ENABLE_LEARNING_COACH=1`且原ORCHESTRATOR开启才允许新建议／确认，默认0；保留历史控制操作。固定错误码包括model_consent_required、context_changed、scope_changed、request_key_conflict、preview_expired_or_changed、schedule_changed_since_operation、coach_request_limit、coach_model_busy、coach_disabled；分别映射422／409／429／503，未授权401、越权记录404。runner异常只返回安全码，不含供应商异常。API_SPEC记录每字段上限、返回状态、只读与取消行为；仅requests加入现役模型凭据白名单。
- [ ] **6.4 验证GREEN**：运行6.2与`uv run pytest filemate/tests/orchestrator/test_api.py filemate/tests/test_p1_account_privacy.py filemate/tests/test_llm_client.py -q`；读取OpenAPI与实际测试核对路径和模型，不凭手写文档宣称接通。
- [ ] **6.5 提交**：`feat(coach): 接通严格API与单次模型授权`，证据存`_working/learning-coach-d/task6/`。

## Task 7: 今日行动按需教练、证据预览与建议阅读

**Files:** 新增`web/src/types/learning-coach.ts`、`services/learning-coach-api.ts`、`today/coach-{state,presentation}.ts`、`components/today/Coach{Panel,Evidence}.vue`、`web/tests/learning-coach-{api,state,presentation}.test.mjs`；修改`TodayWorkspace.vue`、`services/{api,llm-vault}.ts`、`today/today.css`和现役Vite环境声明／示例。

**Interfaces:** `loadLearningCoachClient(): Promise<LearningCoachClient>`为api.ts的懒加载出口；LearningCoachClient函数与任务6逐一同名对应：`capabilities/catalog/context/request/get/cancel/preview/confirm/operation/undoPreview/undoConfirm/day`，返回Promise对应固定合同。`CoachState`含phase:`closed/loading/ready/running/error/expired`、identity、generation、input、context、run、draft、preview、undo_preview、receipt、pending、dirty、error；input／context／run／draft／preview／undo_preview／receipt／pending可空，dirty为bool，error为安全文字。`createCoachWorkspace(client: LearningCoachClient, options: {identity:()=>string|null; wrap?:(state:CoachState)=>CoachState})`返回state与`open(input:CoachInput):Promise<void>`、`readContext(input:CoachInput):Promise<void>`、`submit(mode:'rule'|'llm'):Promise<void>`、`cancel():Promise<void>`、`close():void`、`invalidate():void`；提交只在授权数据匹配时发送，内部不自动重试。`presentCoach(run:CoachRunView):CoachPresentation`分离facts／rule_days／model_status／methods／coverage_notices五项，不从正文反推统计。

- [ ] **7.1 写RED测试**：`opening_never_requests_model`、`consent_is_bound_to_exact_context_and_input`、`changed_identity_ignores_late_result`、`model_error_keeps_rule_proposal`、`raw_text_is_never_persisted`；断言取消后迟到响应不覆盖当前状态，身份切换清正文和授权。客户端断言GET／POST及≤65秒模型timeout正确，除requests外从不携带密钥；模型失败不显示“分析完成”。

```javascript
test('rule request never requires browser credentials', () => {
  const path = '/api/learning/orchestrator/coach/requests'
  assert.equal(requiresModelCredential('POST', path, { mode: 'rule' }), false)
  assert.equal(requiresModelCredential('POST', path, { mode: 'llm' }), true)
})
```
- [ ] **7.2 运行RED**：在`filemate/web`执行`node --test tests/learning-coach-api.test.mjs tests/learning-coach-state.test.mjs tests/learning-coach-presentation.test.mjs`。
- [ ] **7.3 实现阅读路径**：入口“请教学习教练”位于当前目标／预算旁，`VITE_ENABLE_LEARNING_COACH=true`且能力响应有效才显示可用操作，懒加载Vue面板及客户端。五类快捷请求可编辑，默认“先用本地规则”；模型点击先展示确切外发字段／摘录／覆盖再授权一次。requiresModelCredential对新requests路由仅在data.mode为llm时返回true，规则请求不读取本地密钥库。前后端能力错误不能当默认关闭静默消失。沿用四主题、17px正文、至少44px动作和SVG，事实／建议层级清晰，不增加常驻聊天或另一排业务导航。
- [ ] **7.4 验证GREEN**：运行7.2及`npm test`、`npm run build`、`npm run check:bundle`；检查coach未打开时没有新增模型或整库原答请求。检查长中文、长文件名、无数据、400／401／409／429／503状态的可读提示与焦点回到触发按钮。
- [ ] **7.5 提交**：`feat(coach): 增加今日行动教练与外发依据预览`，证据存`_working/learning-coach-d/task7/`。

## Task 8: 方案编辑、联合预览、回执恢复和未来安排

**Files:** 新增`web/src/today/coach-commands.ts`、`components/today/CoachProposal.vue`、`web/tests/learning-coach-commands.test.mjs`；修改任务7前端合同、CoachPanel.vue及`today/navigation.ts`的原功能定位适配，必要时同步原TodayPreview对coach回执的展示。

**Interfaces:** `createCoachCommands(client: LearningCoachClient, options: {state:CoachState; storage:TodayStorage; refresh:()=>Promise<void>})`返回`preview(draft:CoachDraft)`、`confirm()`、`recover()`、`previewUndo(operationId:string)`、`confirmUndo()`、`invalidate()`。恢复定位符固定`{kind:'request'|'confirm'|'undo',request_key,issued_study_date,operation_id?}`，按现役浏览器空间隔离；不存scope、问题、原答、token或整个draft。草稿仅内存，离开提示。

- [ ] **8.1 写RED测试**：`lost_confirm_response_recovers_by_get_only`断言请求键在发出写请求前安全保存，失败恢复不POST；持久定位失败则阻止写。`tomorrow_receipt_does_not_replace_today`断言保存明日显示对应日期，原今日草稿／安排不丢；跨日重读同一日安排而不创建第二份。`editing_or_completing_invalidates_preview`、`double_click_cannot_duplicate_plan`、`expired_identity_clears_authority`；`undo_conflict_preserves_all_progress`展示整体拒绝，无局部“成功”假象。

```javascript
test('lost response recovery reads the original operation', async () => {
  // h使用真实控制器，port记录method；首次confirm已提交但模拟丢失响应。
  const h = await lostResponseHarness()
  h.calls.length = 0
  await h.commands.recover()
  assert.deepEqual(h.calls.map(call => call.method), ['GET'])
  assert.equal(h.state.receipt.request_key, h.originalKey)
})
```

lostResponseHarness在本任务测试文件定义，pending由一次真实commands.confirm调用生成；只替换网络边界响应，不能直接给控制器塞成功receipt。
- [ ] **8.2 运行RED**：在`filemate/web`执行`node --test tests/learning-coach-commands.test.mjs`。
- [ ] **8.3 实现交互**：可调整有限时长、顺序、排除项、目标日期与重叠选择，显示新增／保留完成／固定／延期／替换安排的实际影响；预览与确认两步清晰。建议阶段不建StudyPlan；确认后返回原功能执行，完成事实只从原模块读取，回来刷新。保存响应不明时保留定位符并仅“查询保存结果”；查询404也不自动重发。明日与今日分别显示，已发生操作的撤销另预览，409引导重新读取。
- [ ] **8.4 验证GREEN**：运行8.2及所有today、orchestrator与learning-coach前端测试；在真实Edge以1440／1024／390／320px执行选择→规则→编辑→确认→原功能完成→返回、双页竞争、响应丢失恢复、明日与跨日、取消／离线／401、恢复和删除。四主题抽样、键盘Tab／Escape／焦点、长文本与横向溢出留截图和请求证据；时钟测试显式标为受控日期，不伪称等候真实次日。
- [ ] **8.5 提交**：`feat(coach): 完成短计划确认与失败恢复交互`，证据存`_working/learning-coach-d/task8/`。

## Task 9: D级四目标验收、三条件对比与统一交付

**Files:** 新增`tests/orchestrator/coach/test_{journey,runtime,capacity,evaluation}.py`、`scripts/acceptance/learning_coach_{fixture,journey,runtime,performance}.py`、`evaluation/evaluate_learning_coach.py`、`evaluation/fixtures/learning_coach_cases.json`；新增`docs/LEARNING_ORCHESTRATOR_2_0_D_DELIVERY.md`和`docs/audits/learning-coach-d-2026-11-02/`；更新README、CURRENT_DELIVERY_INDEX、AGENT_DEVELOPMENT_EXECUTION_PLAN、API_SPEC及verify现役检查清单。

**Interfaces:** `evaluate_case(case: dict) -> dict`和命令`uv run python evaluation/evaluate_learning_coach.py --cases evaluation/fixtures/learning_coach_cases.json --output _working/learning-coach-d/evaluation.json`；验收工具使用`--output`创建自己独占的临时夹具，不读取服务器真实用户目录。对比rule、model_explanation、manual_edit三个条件，共用同一证据与预算；明确synthetic／recorded_provider／human_study类型，不把mock标成上游实测。

- [ ] **9.1 写RED测试与场景**：四条实际流程分别为课程考试、竞赛答辩、求职训练、四周C++skill目标；每条完成创建目标、保存真实合成作答／反馈／编译器结果、显式选依据、规则／授权模型、编辑、联合确认、原功能完成、重读及可撤销边界。增加证据不足、重复任务、模型未授权／失败、计划冲突、来源删除／备份恢复。`test_evaluation_rejects_duplicate_overbudget_stale_and_crosscourse`故意输入违规建议，断言各违规计数真实递增；人工编辑次数仅按该次实际操作记录，不生成真实用户修改率或学习提升。

```python
def test_evaluation_rejects_duplicate_and_overbudget(invalid_coach_case):
    report = evaluate_case(invalid_coach_case)
    assert report['duplicate_actions'] == 1
    assert report['overbudget_days'] == 1
    assert report['learning_improvement'] is None
```

evaluation的结果字段固定为evidence_unsupported、duplicate_actions、overbudget_days、irrelevant_actions、stale_evidence、crosscourse_evidence、history_damage、actual_edit_count、learning_improvement；前三条件逐项输出，缺真人数据时learning_improvement始终null。上述夹具仅包含一处重复动作和一个超预算日。
- [ ] **9.2 运行RED**：`uv run pytest filemate/tests/orchestrator/coach/test_journey.py filemate/tests/orchestrator/coach/test_evaluation.py -q`；场景失败必须定位原功能或教练实际缺口，不靠替换固定成功数据通过。
- [ ] **9.3 完成独立验收工具并验证GREEN**：重跑9.2并要求所有具名场景通过。runtime在Python3.11／SQLite3.26隔离新目录跑整应用、强制无JSON1、schema36读取／备份恢复／事务注入；性能使用0／100／1000／10000错题与100／1000／10000节点，记录上下文、规则、HTTP四并发P50／P95、返回数量／ID摘要与截断。结构和语义不变才能比较；延用已公布500ms读取目标，任何未达标项保留P2，禁止换小夹具或缓存命中结果掩盖无JSON1执行。模型时间／费用单独列，不和本地读取混算。
- [ ] **9.4 执行工程门禁**：项目根目录`powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`；干净检出Linux跑相同后端、前端、lint／类型／构建／体积／evaluation门禁。保留原生Windows日志；若Windows未完成只能标未完成，不用Linux结果替代其名称。保护23份用户修改哈希。运行上面evaluation命令、四个验收脚本各自`--output _working/learning-coach-d/<name>`，输出包含源码commit、环境、退出码、真实执行项和限制。
- [ ] **9.5 执行浏览器与上游证明**：任务8全部交互矩阵收口；允许时用现有已授权Provider做一次最小真实模型调用，读取治理真实usage及持久建议后清除合成账号。没有密钥／费用授权就明确待验，不伪造；其他浏览器、Tauri和实体设备按实际运行范围记载，缺工具保持依赖。页面开关关闭、模型故障和数据库故障不拖垮原主流程。
- [ ] **9.6 最终独立审阅与修复**：使用requesting-code-review技能，由一个全新只读审阅者核对整个实现分支、D1—D8、五项Review Focus、隐私／恢复／并发与实际证据；作者修复重要发现并重跑受影响测试，代码变化后再固定最终完整门禁。按已选执行方式仅这次统一独立审阅，不逐任务追加审阅代理。
- [ ] **9.7 交付与阶段边界**：D报告逐条映射D1—D8、四目标结果、数据流／模型版本／额度、API、手册、备份恢复、性能及限制；给出E1—E5待办与三条件真实研究协议所需字段，但不声称E已完成。核验索引／链接／源码哈希，提交`docs(coach): 归档D级工程与交互验收`，请求用户确认D级；未收到D验收不得实施E或打开生产D开关。

## 计划自审与执行起点

| 自审项 | 结论与定位 |
|---|---|
| D1职责、三目标及skill | 任务1证据／目标、2方法／拆分、4实际计划、7—9交互与完整流程 |
| D2双路径与真实版本 | 任务2—3规则、结构化增强、失败状态／费用；7—8展示和恢复 |
| D3五请求、D4有限工作流 | 任务1—4固定合同与事务；6—8入口、单次授权、统一确认 |
| D5面试、D6图谱、D7错题 | 任务1逐项选择与版本、2依据适用矩阵／周期、5删除恢复、9原模块回归 |
| D8对比 | 任务9合成三条件、有依据／重复／预算／相关性／实际编辑／过期跨课／历史损害计数；真实效果留E协议 |
| 隐私、恢复、限流与进程 | 任务3、5、6；调用事务外、全空间治理桶、只读／取消开关、删除墓碑、零密钥落盘 |
| 未来安排、撤销与兼容 | 任务4、8；真实as_of、共享day_id、多日CAS、原键先查、完成真源、所有日原子撤销 |
| Review Focus五项 | 分别落实任务1／3／5，1／4，2／4／8，3／4／6／8，2／3／6的具名测试 |
| 类型／方法一致 | 固定合同与Tasks 1—8接口逐项对应；CoachReceipt区别原C单日OperationReceipt，C只增兼容读，不改变旧写正文 |
| 范围与缺口 | 9个可独立验证交付单元，每项RED→GREEN→显式提交；无空壳／TBD；E、P2修复、真人研究与部署各保留自己的验收边界 |

执行前再次检查Git、原23份测试哈希及schema，记录当前分支HEAD；阅读本计划和完整设计。**下一步从任务1开始，仅在用户审阅本计划后实施**。文档计划通过不等于D功能／测试／正式上线通过。
