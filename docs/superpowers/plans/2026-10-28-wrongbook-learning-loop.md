# Wrongbook 2.0 D: Evidence-backed AI Review and Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 C 级稳定复盘流程上接入逐次授权、可追溯且可恢复的 AI 错因建议，以及真实图谱定位、今日同步和经确认新增的学习任务。

**Architecture:** 延用 Vue 3 + FastAPI + SQLite。证据上下文与关联读取不调用模型；分析先认领持久记录，再在写事务外通过现役 LLMClient 执行一次有界调用，校验成功才保存 Artifact。复用既有治理账本、StudyPlan、review_events 和预览确认机制，不建立第二套任务池或画像。

**Tech Stack:** Python、Pydantic、SQLite、现役 LLMClient／可配置 Provider、Vue 3、TypeScript、Node test runner、Playwright／Edge。

**Spec:** `docs/superpowers/specs/2026-10-25-wrongbook-2-design.md` 第 10—13 节；原任务书 SHA256 `809fee871c2664ba302c5ea42d6560a28d7b3dc2494d62697bb08ee077c64b20` 第七节。七项产品选择已获批准，D 仍独立验收，E 与发布不在本计划内。

**Status (2026-10-28):** 用户在 C 级交付后要求继续，现进入 D 级计划审阅。本文尚未实施，所有新函数、表、API、测试均为待实现合同。沿用当前会话逐项实施、结束后一次独立审阅的方式；计划获审阅确认后开始任务 1。

## Global Constraints

- 工作目录 `C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`；分支 `codex/wrongbook-2-audit`；C 基线 `55a7cfb`。保留现有工作树，不重新实现 C，不把名义目录 `D:/FileMate-Project` 当成本轮源码。
- 单次1次模型调用、20秒总期限、同错题1个在途；不隐式纠正重调，失败后用户主动重试。
- 最多最近5条相关历史、已确认错因、已审核概念与最多3段总计6000字的实际引用。不发整本资料、录像、简历或其他课程。
- AI只是候选，用户确认后落库。目标只出有依据的增量预览、确认才新增，绝不自动改学期目标。
- 用户点击采纳增量才新增任务，最大7项；不修改学期目标与原计划。旧目标快照/无效证据回路保留，已完成任务不得悄悄重置。
- 正文18px、问题24px起、辅助15—16px、主操作17—18px；44px以上触控区；正常正文对比度至少4.5:1。沿用四主题、无衬线字体、本地 SVG，不重做全站视觉。
- B/C 业务 schema35、治理3为当前代码基线。任务2拟追加业务36；执行时先核对 `_MIGRATIONS`，若已占用则停止分配，不能改写旧迁移。SQLite3.26语法兼容；真实旧运行时迁移／恢复的总体验收留 E，不冒认已通过。
- 新模型开关 `FILEMATE_ENABLE_WRONGBOOK_AI=0` 默认关闭；新建分析还须 `FILEMATE_ENABLE_WRONGBOOK_V2=1`。读取、导出、删除与取消在模型开关关闭后仍可用。前端延用 C 的 VITE 开关，并读服务端能力，不增第二套主题或导航。
- 不创建新配额库。模型调用仍走现役空间／全站次数、单位与并发治理；复用 `admit_learning`，D 采用固定命名空间 `wrongbook-analysis` 的滚动24小时30次认领上限（工程选择，不是假课程ID）。取消／失败不退款，恢复个人备份不退还治理额度。
- 原题、真实答案、判题、复习状态、阶段及学期目标均不可由模型改写。待核对与辅助结果不冒充确定正确；不输出心理诊断、掌握率或概率。
- 保留 `_working/wrongbook-a-20261025/preserved-tests.json` 中24个原有测试修改；只暂存本卡路径，不修改或清理其他卡临时目录。临时证据放 `_working/wrongbook-d-20261028/`。
- 初始递归静态依赖gzip预算143360字节保持。C 当前开启构建142888字节，新增界面／控制器按路由或面板懒加载，不从应用壳静态引入。

## Review Focus

1. 服务端已调用但响应丢失，刷新／双标签重试：以同键只读恢复，不重复调用或将未知状态显示成功（任务2、3、4、6、7）。
2. 分析期间换题／换身份／恢复旧备份，或来源删除后模型迟到：旧 epoch 永远不能发布结果，正文及所有外发来源的删除依赖完整（任务2、3、6、7）。
3. 同一个题目的错题摘要与图谱摘要不同，课程融合或映射停用：使用各自原函数验证当前题目，不能直接比较两类摘要、按同名映射或跨课累计（任务1、7）。
4. AI错因采纳后用户手改、已完成新任务后撤销、预览后又作答：版本冲突保留新事实及原稿；不能覆盖用户修改或擦除完成记录（任务4、5、6、7）。
5. 慢响应持续吐少量字节、Worker挂起、预算／密钥错误：20秒截止终止并回收该私有进程；不遗留无限线程／进程；基础复习继续可用（任务3、4、7）。

## 文件职责与共享合同

| 文件 | 待实现职责 |
|---|---|
| `filemate/wrongbook/learning_context.py`（新） | 单快照下绑定题目、选中作答、历史、错因、当前映射与有界原文；只读投影 |
| `filemate/wrongbook/analysis_schema.py`、`analysis_repository.py`、`privacy.py`（新） | 分析记录、全来源依赖、幂等请求墓碑、缓存／失效、恢复规范化 |
| `filemate/wrongbook/analysis_models.py`、`analysis.py`（新） | 严格输出结构、逐字引用校验、Prompt、分析领域服务 |
| `filemate/llm_client/bounded_call.py`、`bounded_worker.py`（新） | 仅供本卡使用的可终止工作进程；复用 LLMClient 与可信治理上下文，不改其他业务默认调用行为 |
| `filemate/wrongbook/learning_api.py`（新） | D 路由与严格请求／错误合同；模型路由精确授权 |
| `filemate/wrongbook/learning_commands.py`（新） | 采纳错因、增量计划、预览确认／撤销与审计 |
| `filemate/execution/storage.py`、`operations/personal_backup.py`、`operations/backup.py`、`server.py` | 追加迁移、删除影响／依赖、个人／管理员恢复中断及路由注册；保持既有主链 |
| `filemate/web/src/types/reviewLearning.ts`、`wrongbook/analysis-state.ts`、`wrongbook/learning-state.ts`（新） | D DTO、请求恢复、面板代次、可编辑任务预览 |
| `filemate/web/src/components/wrongbook/ReviewAnalysis.vue`、`ReviewLearningPlan.vue`、`ReviewConnections.vue`（新） | 按需分析、采纳、任务预览、明确映射；现有目录／作答不依赖其加载成功 |
| `services/review-api.ts`、`services/llm-vault.ts`、`llm_client/request_credentials.py` | 延用共享认证HTTP；仅精确模型 POST 接收临时凭据 |
| `ReviewWorkspace.vue`、`ReviewEvidence.vue`、`ReviewEntry.vue`、`entry-state.ts`、`CourseLearning.vue`、`Today.vue`、`GoalPlanner.vue` | 按需接入、精确往返链接、写入后重取与草稿保护 |

共享身份：`ReviewRef = {wrong_id,artifact_id,question_index,question_digest}`，摘要使用错题的 `execution.data_actions.digest(raw_question)`；图谱匹配另用 `course_graph.question_links.question_digest(raw_question)`。请求键沿用16—80位字母／数字／下划线／横线；ID沿用128字符上限；新命令 `StrictBody(extra='forbid', strict=True)`，显式确认只接受布尔 `true`。

`ReviewContext` 返回 `ref/attempt/related_attempts/confirmed_diagnosis/graph_links/source_evidence/next_actions/coverage/input_digest/context_revision/provider_identity/prompt_version/rule_version/as_of`。每份资料证据包含服务器生成ID、source_id、source_revision、连续quote、全局char_start/char_end、可核验页码或null、`relation_kind=confirmed_graph|retrieval_candidate`。不使用 chunk 内相对偏移冒充整本资料位置。无可用Provider配置时仍返回只读上下文及明确不可调用状态，不借读取抛出密钥异常；正式请求须绑定有效Provider身份。

领域内部另携带 `_source_dependencies:[{source_id,source_revision,membership_revision}]`、`_graph_binding` 和原始题目绑定，覆盖所有参与输入的来源；HTTP只投影公开字段。Task2从服务端重建的内部Context登记依赖，不能只登记最终引文来源。客户端input_digest仅作乐观校验，不是可信上下文；新认领前重新读库，原键恢复先读已保存回执，绝不能由客户端传正文／来源列表替换真实记录。

`ReviewAnalysis` 返回 `analysis_id/request_key/ref/attempt_id/status/stale/error_code/result_artifact_id/result/provenance/created_at/finished_at`；状态 `running|ready|failed|cancelling|cancelled|interrupted`。GET 不续租、不调用模型；失效是当前输入与已保存绑定不符，不抹掉历史。`provenance` 只含 provider身份、model、Prompt版本、规则版本、实际usage（未知null），无密钥、完整base_url或供应商异常正文。

`AnalysisOutput`严格字段：`kind`、`possible_causes`、`uncertainties`、`smallest_action`、`targeted_practice_suggestion`、`schedule_suggestion`、`reasons`。每项possible_causes为`{cause_code: Cause,hypothesis: str(1..500),answer_evidence_refs: [{attempt_id,quote: str(1..1000)}](1..3),source_evidence_refs: [evidence_id](1..3)}`；重复引用／重复cause拒绝。`insufficient_evidence`必须causes为空且uncertainties非空；其余建议仅可描述补证／重新独立作答，不能冒充已查明原因。`supported_hypotheses`必须至少1个有引文的候选。

公共前缀 `R=/wrongbook/v2/{wrong_id}`，新增路线如下，发布时才写入 API_SPEC 的现役合同：

| 方法／路径 | 严格输入／输出 |
|---|---|
| GET `R/learning-context` | `attempt_id`必填、`course_id`可选；返回上述只读上下文及外发范围预览 |
| GET `R/connections` | limit=1..30、offset=0..1000000；显式有效图谱映射及当前题目精确路径 |
| POST `R/analyses` | attempt_id、course_id、input_digest、request_key、force_refresh=false、allow_external_model=true；返回 Analysis |
| GET `R/analyses`、`R/analyses/{analysis_id}` | 历史默认20、最多100；只读，读取本人证据，不携带密钥 |
| GET `/wrongbook/v2/analysis-requests/{request_key}` | 以原键恢复；不存在404、已清理410，不触发重试调用 |
| POST `R/analyses/{analysis_id}/cancel` | request_key；可重复，终态不反转，取消不退款 |
| POST `R/analyses/{analysis_id}/adoption-preview` | selected_causes=1..3且唯一、expected_revision；返回将写入的完整错因差异与确认token |
| POST `R/analyses/{analysis_id}/adoption-confirm` | 同选项、revision、token、request_key、confirmed=true；返回review_event_id与当前错因 |
| POST `R/learning-plan-preview` | expected_revision、goal_id可选、start_date、tasks=1..7；返回选中任务、依据、确认token |
| POST `R/learning-plan-confirm` | 同选项、token、request_key、confirmed=true；返回新StudyPlan／Artifact／event ID及route |
| POST `R/learning-operations/{event_id}/undo-preview`、`.../undo-confirm` | 仅采纳错因／本卡新增计划；确认绑定token、request_key、confirmed=true；不支持任意表操作 |

GET未知／重复查询参数422，其他用户／不存在对象404，输入／版本／预览冲突409，墓碑410，参数／缺授权422，限额429，Provider502、依赖故障503。已建运行的模型故障持久化安全error_code并返回失败记录，不把其作为成功分析；调用方检查status。所有响应no-store；模型错误不会触发账号401跳转。

现有 `GET /wrongbook/v2/question-access/{artifact_id}/{question_index}` 增量返回 `wrong_id: str|null`、`review_route: str|null`，只定位该当前题目版本的真实错题；无错题返回null，不自动创建记录。Task6以此为课程／资料练习提供反向链接，原字段与旧调用合同保留。分析列表只返回摘要，不在20—100项列表批量返回原答案／模型正文／上下文；详情GET才按需取结果。

## Task 1: 真实上下文与图谱往返定位

**Files:** 新增 `learning_context.py`、`filemate/tests/wrongbook/test_learning_context.py`；修改 `learning_api.py`（只读部分）、`api.py`（路由查询白名单）、`server.py`（注册）、`filemate/docs/API_SPEC.md`（本任务已实现的读合同）。

**Interfaces:** `ReviewLearningContext(storage, clock).build(wrong_id, attempt_id, course_id=None) -> dict`；`.connections(wrong_id, *, limit=30, offset=0) -> dict`。产生 Task2—5 使用的确定性 `input_digest` 和 `context_revision`；时间戳不参与缓存hash。

- [ ] **Step 1: 写失败测试。** `test_context_binds_real_attempt_and_bounds_history` 断言选中attempt属于同一题／版本；related_attempts≤5且不重复选中项；无作答拒绝分析而非伪造空答案。`test_connections_revalidate_both_digest_algorithms` 断言真实映射返回 `graph_scope=course&course=<cid>&node=<root>&view=evidence`，融合解析当前root，旧摘要／停用来源／历史题集无当前映射。`test_quotes_have_global_literal_offsets` 断言最多3段、总字数≤6000、每段raw_text[start:end]==quote；老chunk相对偏移、重复子串无法唯一定位时不补造页码／位置。
- [ ] **Step 2: 运行RED。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_context.py -q`；Expected: 缺领域投影的断言失败，不能只有fixture或路径错误。
- [ ] **Step 3: 实现只读投影。** 一次read_snapshot；只接受选定一门课程，不能把不同课程上下文合并发送；不选课程仍可用本题资料。优先有效图谱原文，剩余用现役 `understanding.retrieval.rank_chunks` 在本题资料内检索并标候选；只收可逐字核验的连续片段。题目快照沿用≤60000 JSON字符，单答案≤10000字符，概念标签最多12个，总外发JSON≤128KiB；超限拒绝或明确报告截断范围，不能偷偷删原答后声称完整分析。图谱和个人训练事实分栏，训练数据仍按trusted_attempt过滤。为新读路由实现独立ReviewLearningRoute查询白名单；扩展原question-access反向错题定位，并测试无错题／历史版本不误跳。Task5接入前next_actions固定为空且标尚不可用，不伪造待开发建议。
- [ ] **Step 4: 运行GREEN及相邻回归。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_context.py filemate/tests/course_graph/test_learning_links.py filemate/tests/wrongbook/test_workspace_reads.py -q`；Expected: 全通过，测试注入Provider调用数0。此命令为task-done命令。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 增加真实复盘上下文与图谱关联读取`。

## Task 2: 分析持久化、幂等、缓存与隐私生命周期

**Files:** 新增 `analysis_schema.py`、`analysis_repository.py`、`privacy.py`、`filemate/tests/wrongbook/test_analysis_repository.py`、`test_analysis_privacy.py`；修改 `execution/storage.py`、`operations/personal_backup.py`、`operations/backup.py`、`tests/test_backup.py`、`tests/wrongbook/test_schema.py`，及下述当前schema断言。

**Interfaces:** `ReviewAnalysisRepository(storage,clock).find_request(key)`、`.claim(context,request_key,force_refresh=False)`、`.finish(analysis_id,epoch,result,provenance)`、`.fail(analysis_id,epoch,error_code)`、`.cancel(wrong_id,analysis_id,request_key)`、`.get(wrong_id,analysis_id)`、`.page(wrong_id,limit=20,offset=0)`。claim返回 `(public_view, claimed, epoch)`；未claimed绝不能调用模型。

- [ ] **Step 1: 写失败测试。** `test_two_connections_claim_once_and_cache_replays`：同键同body只认领一次，同键异body409；新键相同上下文默认复用ready结果、不消耗模型额度，force_refresh才新建。`test_late_epoch_after_cancel_restore_or_source_delete_cannot_publish`：晚响应0个新Artifact；恢复旧备份即使重现原ID也不能写回。`test_delete_every_input_source_purges_snapshot_and_artifact`：删除任一实际输入来源（包括只贡献标签／未被最终引用的资料）清除全部派生正文，预览计数与真实删除集合一致。`test_upgrade35_preserves_nullable_attempts_and_rolls_back_failure`：旧ID／行序／NULL不变，quick_check=ok、FK=0，注入失败整笔迁移回滚。
- [ ] **Step 2: 运行RED。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_repository.py filemate/tests/wrongbook/test_analysis_privacy.py -q`；Expected: 缺认领／生命周期约束的断言失败。
- [ ] **Step 3: 追加migration36与仓储。** `wrong_review_analyses` 存 wrong_id FK CASCADE、attempt_id FK CASCADE、question_digest、input_digest、context_revision、provider_identity/model/prompt_version、input_snapshot、status、随机epoch、20秒deadline、30秒lease、result_artifact_id FK SET NULL、safe error与时间。按wrong_id建立仅running/cancelling的唯一部分索引；历史(wrong_id,created_at,analysis_id)索引。`wrong_review_analysis_sources(analysis_id,source_id)` FK CASCADE并索引source_id；源删除触发清理整份运行及结果Artifact，运行因其他FK级联删除也须同步清除其结果Artifact，禁止留下孤立正文。`wrong_review_analysis_requests(request_key PK,request_digest,analysis_id FK SET NULL,created_at)` 仅保留摘要／无正文墓碑，禁止以被删除结果的旧键重调；它不是配额账本。结果作为 `wrong_review_analysis` Artifact，并登记所有输入资料到现有 `kg_learning_artifact_sources`（无需假course_id）。完成时原子校验epoch／期限／当前输入／开关；ready Artifact与运行一次提交。失败／取消不覆盖旧ready结果。个人导出自动枚举新表；个人及管理员恢复钩子轮换所有epoch、running/cancelling→interrupted，清除本卡预览，不恢复外发授权；旧备份缺表可恢复为空。来源删除预览绑定本卡依赖及实际级联集合，使用集合去重避免重复计数。

  当前schema断言同步到36的确切文件：`filemate/tests/test_storage.py`、`test_programming.py`、`test_interview_review.py`、`test_interview_assessment_storage.py`、`test_runtime_governance.py`、`test_deploy_migration_contract.py`，以及`filemate/tests/course_graph/test_storage.py`、`test_learning_links.py`、`test_growth_lifecycle.py`、`test_growth_benchmark.py`、`test_review_closeout.py`。仅修改“最新版本”断言；B的v34→35升级／故障回滚测试通过冻结migration≤35保留历史合同，并另测35→36，不把历史迁移改成36。迁移静态检查器须仍验证所有旧迁移未变。
- [ ] **Step 4: 运行GREEN。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_repository.py filemate/tests/wrongbook/test_analysis_privacy.py filemate/tests/test_p1_personal_backup.py filemate/tests/test_backup.py filemate/tests/wrongbook/test_schema.py filemate/tests/test_deploy_migration_contract.py -q`；Expected: 全通过，治理额度恢复前后不减少，所有旧迁移SQL hash不变；本任务其余schema消费者在Task7全门禁覆盖。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 持久化分析运行及全来源删除依赖`。

## Task 3: 单次模型分析、结构校验与硬截止

**Files:** 新增 `analysis_models.py`、`analysis.py`、`llm_client/bounded_call.py`、`llm_client/bounded_worker.py`、`filemate/tests/wrongbook/test_analysis_service.py`、`filemate/tests/test_bounded_llm_call.py`；新增现有提示词目录的 `filemate/understanding/prompts/wrongbook-analysis-v1.md`（纯指令模板）；复用 Task1／2。

**Interfaces:** `BoundedLLMRunner.run(config,scope,*,prompt,messages,schema,deadline,cancelled) -> {output,usage}`；`ReviewAnalysisService(storage,config_factory,runner,clock).analyze(wrong_id,command) -> ReviewAnalysis`。`config_factory`延用`LLMConfig.from_env`，不另存密钥；替换服务端Provider仍通过LLMClient。生产进程入口固定，测试可注入runner但HTTP不得指定程序／工厂。

- [ ] **Step 1: 写失败测试。** `test_one_call_and_no_automatic_repair`：timeout≤20、retry=1、max_tokens=3500，坏JSON／伪引用失败且调用数1；同键重试不再调用。`test_causes_require_literal_answer_and_whitelisted_source_refs`：possible_causes≤3且不重复；每项实际answer子串引用与资料ID／修订／连续范围全部匹配。无来源时只允许 `insufficient_evidence`、空causes和明确uncertainties；有断言但无引用为invalid_output。`test_worker_deadline_kills_dribbling_provider_and_preserves_scope`：本地假服务持续小片段响应，短测试期限内停止并回收私有进程，无活跃子进程残留；治理记到原空间，密钥不在argv／环境／日志。`test_cancel_or_switch_provider_rejects_late_finish`：迟到结果不落库，显式重试使用新输入／版本。
- [ ] **Step 2: 运行RED。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_service.py filemate/tests/test_bounded_llm_call.py -q`；Expected: 分析约束／截止未实现的断言失败。
- [ ] **Step 3: 实现有界调用及校验。** 20秒总期限从认领新模型工作开始，包含工作进程启动／通信，传给LLMClient的timeout只取剩余秒数。父进程只通过私有stdin管道传受信配置、限128KiB上下文及现役Scope描述，子进程恢复同一治理账本路径／Policy／owner_hash／trace／managed_db_path，调用原LLMClient；这些描述绝不可由HTTP body提供。子进程不接触业务SQLite，不继承额外密钥环境，不在命令行或磁盘存配置。stdout仅有界结果≤128KiB、stderr丢弃；内存上限384MiB、期限／取消时终止并wait回收，仅处理自己创建的进程。Windows隐藏窗口。父进程未回收前不释放占位，Worker被杀的治理在途记录由既有进程存活检测回收，次数不退款。输出严格Pydantic extra=forbid：kind=`supported_hypotheses|insufficient_evidence`，possible_causes、uncertainties≤5、smallest_action≤500字、targeted_practice_suggestion≤500字、schedule_suggestion≤500字及reasons≤3；每项只接受既有Cause枚举。Prompt将资料／回答当不受信数据，无工具能力，不写个人成绩／概率／确定掌握结论。语义仍须人核对，不能承诺格式验证证明真因。
- [ ] **Step 4: 运行GREEN与治理回归。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_service.py filemate/tests/test_bounded_llm_call.py filemate/tests/test_llm_client.py filemate/tests/test_runtime_governance.py -q`；Expected: 全通过；无密钥／401／429／timeout／非法引用各有固定safe error，原始异常不进入Artifact。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 实现有引用的单次有界模型复盘`。

## Task 4: 分析API、精确凭据与错因采纳

**Files:** 扩展 `learning_api.py`；新增 `learning_commands.py`（错因部分）、`filemate/tests/wrongbook/test_learning_api.py`、`test_analysis_adoption.py`；修改 `request_credentials.py`、`services/llm-vault.ts`、`repository.py`（可共事务诊断内部函数）、`api.py`（capabilities）、`server.py`、API_SPEC、README及`.env.example`中现有开关区。

**Interfaces:** Task前API表中分析／恢复／取消／adoption全部路线；capabilities追加`analysis_enabled`。`ReviewLearningCommands(storage,clock).preview_adoption(wrong_id,analysis_id,selection)`、`.confirm_adoption(wrong_id,analysis_id,selection,token,key,confirmed)`。每个采纳输出标准`review_event_id`与完整当前错因，供Task6刷新同一详情。

- [ ] **Step 1: 写失败测试。** `test_api_enforces_owner_consent_and_exact_key_route`：仅POST精确 `R/analyses` 加入前后端密钥白名单；GET、取消、adoption、相似后缀不带凭据，双账号互读404，漏授权／extra字段422，服务端Provider错误不映射账号401。`test_adoption_preserves_manual_causes_and_requires_current_preview`：逐项选1..3个真实候选，与既有用户错因合并；超3须用户重选，不能静默删除；保留备注／标签，source=user，并在事件记analysis_id、选项和before/after。陈旧结果／后续作答／用户已改原因使确认409；重复确认同结果且只写一事件。`test_disabled_still_reads_and_cancels`：关闭阻止新分析／采纳，不阻止读取／取消／原规则复习。
- [ ] **Step 2: 运行RED。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_api.py filemate/tests/wrongbook/test_analysis_adoption.py -q`；Expected: 新边界断言失败。
- [ ] **Step 3: 接线与采纳。** 工厂在HTTP受信上下文构造配置；模型在同步路由线程执行，不能阻塞ASGI事件循环。白名单锚定完整路由，浏览器临时密钥仍固定现役DeepSeek官方HTTPS，不切换共享服务端endpoint。GET context若带密钥仍拒绝／剥离，不能被当成生成授权；context_revision不等同外发授权，必须用户逐次明确同意。新输出型错误固定枚举，无供应商正文。抽取 `_diagnose_in_transaction` 给原手动诊断与采纳共用，不能嵌套BEGIN或令旧接口丢失校验；保留C的revision及幂等合同。仅缺来源但结构合法的insufficient_evidence允许展示，禁止采纳不存在的候选。
- [ ] **Step 4: 运行GREEN。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_api.py filemate/tests/wrongbook/test_analysis_adoption.py filemate/tests/wrongbook/test_api.py filemate/tests/test_server_persistence.py -q`；Expected: 全通过，包括现有浏览器密钥／Origin／Action／并发上下文测试；前端另跑 `node --test tests/llm-vault.test.mjs`，cwd=`filemate/web`，Expected: 全通过。task-done用封装这两条命令的本卡验证脚本，任一失败退出非0。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 接通授权分析与可确认错因采纳`。

## Task 5: 有依据且可撤销的增量学习任务

**Files:** 扩展 `learning_commands.py`、`learning_api.py`；新增 `learning_suggestions.py`、`filemate/tests/wrongbook/test_learning_plans.py`；必要时扩展 `study/goal_planner.py` 的只读证据入口，不改原replan语义。

**Interfaces:** `ReviewLearningCommands.suggestions(wrong_id,goal_id=None) -> dict` 在 `GET R/learning-context` 的 `next_actions` 内返回；`.preview_plan(wrong_id,selection)`、`.confirm_plan(wrong_id,selection,token,key,confirmed)`、`.preview_undo(wrong_id,event_id)`、`.confirm_undo(wrong_id,event_id,token,key,confirmed)`。selection.tasks是候选action_id与用户编辑后的title≤120、instructions≤500、duration_minutes=5..60、day_offset=0..6，1..7项唯一；start_date为上海当日到未来30日；goal_id可空且必须同资料／所选课程。

- [ ] **Step 1: 写失败测试。** `test_one_error_only_proposes_small_action_and_never_rewrites_goal`：仅一次错答候选最多1项短行动；重复错答≥2／当前已逾期至少1天／用户确认错因可产生多项，合计≤7，不调用模型。每项basis含真实wrong_id、attempt_ids、时间窗30天、trusted分母、规则版本，统计均服务器计算。`test_preview_edits_confirm_and_replay_add_exactly_one_plan`：预览／取消不创建计划，修改后重预览才可确认，同token异key重放不重复；原有目标、计划、completed_days逐字未变，任务准入使用admit_plan。`test_undo_conflicts_after_completion_or_manual_edit`：仅撤销本卡新增计划，已有完成／内容变化409；错因采纳撤销只恢复before诊断，不删除作答。`test_stale_goal_source_or_attempt_invalidates_preview`：任何相关证据变化拒绝旧确认，不能只校验wrong.revision。
- [ ] **Step 2: 运行RED。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_plans.py -q`；Expected: 缺增量／保护约束的断言失败。
- [ ] **Step 3: 实现规则候选与事务确认。** 候选是复盘／阅读已核验片段／针对性重练，不替用户生成答题记录；AI建议若展示，必须挂当前有效分析ID，仍由服务器候选白名单决定可执行动作。预览绑定题目／选中证据、诊断、来源／图谱、goal完整摘要、用户编辑内容、日期及任务数。确认原子新建1个既有study_plan Artifact及StudyPlan，一天可多任务、总数≤7，关联 `review_learning` metadata与原证据、所有资料依赖；复用admit_plan，不创建新目标、不调用replan、不覆盖任何旧任务。review_events action=`analysis_adopt|learning_plan_confirm|learning_undo` 保存最小回执与前后摘要；data_actions token／audit按现有机制，撤销必须独立预览确认。删除新增计划可明确执行，仅限本操作创建且仍未修改／未完成的对象；同一事件仅一次逆转，原作答不可删。Today继续读现役StudyPlan／错题投影。
- [ ] **Step 4: 运行GREEN。** `.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_plans.py filemate/tests/test_goal_planner.py filemate/tests/wrongbook/test_consumers.py -q`；Expected: 全通过，原目标快照／口述训练失效保护不变。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 增加有证据的学习任务预览与撤销`。

## Task 6: 工作台分析、图谱和任务面板实装

**Files:** 新增职责表中的前端types／控制器／3个面板及 `filemate/web/tests/wrongbook-analysis.test.mjs`、`wrongbook-learning.test.mjs`；修改 `services/review-api.ts`、`types/wrongbook.ts`、`wrongbook/entry-state.ts`、`ReviewEntry.vue`、`ReviewWorkspace.vue`、`ReviewEvidence.vue`、`review-workspace.css`、`CourseLearning.vue`、`Today.vue`、`GoalPlanner.vue`、现有 `wrongbook-component-wiring.test.mjs`。

**Interfaces:** `createReviewAnalysisController(api,reactive,storage)` 暴露 `open(ref,attemptId,courseId)`、`loadContext()`、`authorizeAndAnalyze()`、`recover()`、`cancel()`、`invalidate()`、`dirty()`；`createReviewLearningController(api,reactive)` 暴露 `open(ref)`、`previewAdoption()`、`previewPlan()`、`confirm()`、`previewUndo()`、`invalidate()`、`dirty()`。API函数名与Task4／5一致，类型从`reviewLearning.ts`导入。

- [ ] **Step 1: 写失败测试。** `test_open_never_calls_model_and_displays_exact_outbound_scope`：展开面板只GET，选择真实attempt后展示将发送的题目／答案／历史／引用，授权默认false且每次重新分析都重新确认。`test_timeout_recovers_same_key_without_resending`：POST未知时只查GET，刷新只存scope+ref+request_key+input_digest、不保存正文／密钥，最多20条、7日TTL，多实例合并不覆盖其他pending。`test_identity_restore_and_new_answer_invalidate_all_previews`：换题／身份／恢复／新作答后旧响应不写新界面；旧结果可回看但标历史，不能采纳，原草稿不丢。`test_edit_plan_requires_new_preview_and_cancel_preserves_goal`：编辑／取消／409不改原计划，confirmed后按真实回执显示。挂载实际SFC测试取消导航保留草稿、键盘焦点、取消分析不等于停止全站复习。
- [ ] **Step 2: 运行RED。** cwd=`filemate/web`：`node --test tests/wrongbook-analysis.test.mjs tests/wrongbook-learning.test.mjs tests/wrongbook-component-wiring.test.mjs`；Expected: 新交互断言失败，非仅静态字符串缺失。
- [ ] **Step 3: 按需面板与往返链接。** 单题主动作保留独立作答；提交结果下提供“分析这次回答”，历史中可另选真实attempt。AI区分可能原因／逐字原答／资料原文／仍未知；逐项采纳预览，禁用失效建议。手动错因草稿尚未保存时先选择保存或继续编辑，不能用AI覆盖。无图谱映射给真实空态，有多个课程先选择；图谱训练面板按当前题身份显示“打开此题复盘”，返回保留课程／节点与视图，未保存回答走既有guard；URL只放ID。Today和错题在变更成功、重新进入／前台恢复时重取，dirty项不卸载，不声称推送实时同步。目标页提供既有任务入口与本卡创建计划的证据回看，不增加重复顶栏。模型开关关闭／组件加载失败时基础ReviewQuestion、诊断、历史及排期仍可用；参考答案只有核对后才展示，专注答前不出现AI提示。任务可编辑、重预览、确认和撤销均有清楚状态；跟随现有字体／主题／下载配置。
- [ ] **Step 4: 运行GREEN。** cwd=`filemate/web`：`npm test`、`npm run build`、`npm run check:bundle`；Expected: 全部测试／类型／构建／原143360预算通过；不得提高预算或把错误转为静默fallback。task-done使用依次运行上述命令且传递非0退出码的本卡脚本。
- [ ] **Step 5: 仅提交本任务路径。** `feat(wrongbook): 接入分析与增量学习的引导面板`。

## Task 7: 故障闭环、浏览器验收与D级交付

**Files:** 新增 `scripts/acceptance/wrongbook_learning_fixture.py`、`wrongbook_learning.mjs`、`verify_wrongbook_learning.ps1`、`docs/WRONGBOOK_2_0_D_DELIVERY.md`、`docs/audits/wrongbook-2-d-2026-10-28/verification.json`／`review.md`／`execution-record.md`；同步README、API_SPEC、CURRENT_DELIVERY_INDEX、阶段执行入口。

**Interfaces:** 隔离合成账号／两门课程／有映射与无映射题／主观待核对／失败Provider，绝不连接生产资料。fixture沿用不存在的新根目录、`.synthetic-wrongbook`标记；凭据仅进程内与环境传递，报告不含明文。本地受控Provider只监听loopback，按合成请求场景返回JSON／401／429／坏引用／缓慢响应，不替换真实业务路由；默认部署不可启用它。浏览器脚本输出真实check结果、调用次数、耗时与错误；遇失败退出非0。

- [ ] **Step 1: 补失败用例并实际RED。** 对浏览器／领域组合尚未覆盖的 `lost_response_refresh`、`source_deleted_during_analysis`、`restore_during_analysis`、`expired_quote`、`cross_account`、`cancel_hung_worker`、`undo_after_completion` 各写可观察断言；先在缺相应接线的测试边界复现失败，再最小修正；已由Task1—6覆盖的用例不为形式重复制造产品错误。
- [ ] **Step 2: 真HTTP／浏览器完成D闭环。** 原答→授权范围→一次模型调用→引用与未知部分→逐项采纳／撤销→新作答使旧分析过期→图谱精确往返→编辑任务预览／取消／确认／撤销→Today同源→刷新重登恢复。失败矩阵无密钥、401、429、超时、断网、无引用、伪引用、坏JSON、过期来源、数据库故障；每种失败后独立回答／查看历史仍可用。1440／1024／768／375四宽与四主题，大字、44px、4.5对比、键盘焦点、200%缩放、长题名／代码／长模型文本无横向溢出。Expected: 每项有实际API／DOM证据，0未解释pageerror；未执行明确列出。
- [ ] **Step 3: 全量门禁和开关回退。** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`；前端开关开启与关闭分别构建／check:bundle，后端AI关闭后读取／取消／导出可用，既有2.0记录不降级到旧判题。Expected: 各命令exit0、原预算不变。E的真实SQLite3.26迁移／整包恢复／生产容量不借本机结果记通过；真实外部模型质量、真人学习实验未执行也必须明示。
- [ ] **Step 4: 一次新上下文整卡独立审阅。** 依executing-plans生成本计划review package，审阅范围C基线至D最终HEAD，特别检查五项Review Focus和ledger所有ruling。只派1名最终审阅者；Important／Critical一轮TDD修复并重跑相关／全门禁，不重复派重审；Minor列明保留。完成记录归档到docs，不删除其他卡临时目录。
- [ ] **Step 5: 提交交付与阶段报告。** `docs(wrongbook): 记录D级证据闭环验收与边界`。task-done通过 `verify_wrongbook_learning.ps1 -CheckRecordedEvidence` 检查本轮全门禁、浏览器与最终源码hash一致，再跑前端测试；任何产品修改使既有证据失效须重跑受影响门禁。报告实现／真实测试／未解决项／E计划，停止等待D阶段验收；不推送、不迁移生产、不替用户宣布正式上线。

## 计划自审与交接

- 需求覆盖：任务书7.1／7.2→Task1—4、6；7.3→Task1、6、7；7.4→Task5—7；7.5→Task5—7；7.6→Task2—4、6、7。A设计约定的全来源删除、配额不回滚、Provider切换、缓存与迟到响应均有对应测试。
- 接口一致性：Context的input_digest不含as_of，绑定Provider／Prompt／规则和全部真实输入，包括当前复习revision、排期及诊断；不能绑定全库data_version，否则认领本身会令自己过期。采纳／计划确认要求当前revision，采纳改变诊断后原分析自然成为历史；撤销依据采纳事件的before/after及当前版本，不要求被采纳的旧分析再次变成当前。输入变化以新上下文重新授权。相同输入不同request_key缓存命中不产生新模型工作。cancel终止运行，不能撤销已保存真实作答。
- 工程选择明示：复用现有治理命名空间而非假课程；20秒独立可回收进程；缺引用时保守显示无法确定；计划新建一个既有StudyPlan；无匹配图谱时不自动建联系；生产SQLite实测留E。这些不表示已实现或已验收。
- 执行前仅校对计划中实际测试／环境模板路径，发现路径或合同不符作最小更正并记ledger；不得为不存在文件报错冒充RED。不降低预算、隔离、引用或确认门槛。
- 计划审阅后创建本计划独立执行ledger，先核对Task1→2→3→4→6及Task1／4→5→6→7的共享接口；C的已完成任务不重做。全部新行为维持在D范围，E及统一OJ排期另卡。
