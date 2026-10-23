# Knowledge Graph 2.0 D/E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 用户已选当前会话连续实施，全部完成后一次独立审阅；不逐卡重新询问。

**Goal:** 把课程图谱与真实题目、作答、错题、复习、目标和今日任务连接，交付有界、可解释、须确认写入的图谱助手及科研工具。

**Architecture:** 保留现役Source/Artifact/QuizAttempt/WrongQuestion/StudyPlan，migration32追加课程映射与工作结果，33补派生Artifact的完整来源依赖。领域模块负责快照、版本、预览事务；模型调用在事务外且有界；Vue侧栏按需承接训练与助手，保持C浏览协议。

**Tech Stack:** Vue3、TypeScript、FastAPI、Pydantic、SQLite、Python；无新运行时依赖。

**Spec:** `docs/superpowers/specs/2026-10-23-knowledge-growth-de-design.md`；原A总设计及用户D/E原始需求为上游，新增授权覆盖此前逐级开工等待。

## Global Constraints

- 工作区沿用`codex/knowledge-graph-2-audit`；保留24份用户改动测试，不暂存；不推送／部署。
- 追加migration32／33，不改v1–31及已提交32。旧source图谱和旧数据可读；D继承课程开关，E助手默认关闭。Task3来源隐私补充见设计与执行记录。
- 不按词出现自动建立练习映射；不重建作答／错题／计划主表；不跨课累计证据。
- 状态`course-training-v1`：7天错答或复习到期优先巩固；30天3不同题跨2日、7天无错且无到期才近期稳定；否则已有练习／暂无证据。
- 所有写入先预览确认、版本绑定、幂等、审计、可撤销；只新增计划，不覆盖手工计划，完成计划不等于答对。
- 模型最多1次调用、20秒、零自动重试；课程最多1运行、24小时30次；外发独立授权，所有文字不可信，不执行代码。
- Agent最多4个只读步骤、7项任务；无删除／文件／SQL／核心画像写权限；确认写入独立于模型。
- 每次只读回复有界：12引文／12000字符、最多30概念摘要；查询分页50、批量映射20、练习草稿1–5题。
- 无衬线大字、蓝色四主题、现有SVG；不增顶栏业务入口／依赖／远程字体；保持选择与画布展开分离。
- 合成工程夹具与真实研究分开；真人协议另批后才能采集，未测数据用null／待评测。

## Review Focus

1. 同一题经多概念融合又撤销、或修订后恢复原文字，旧作答不能重复或被错归；Task2测试覆盖。
2. 用户切课程／身份、取消／恢复备份期间模型晚到与网络不确定，不能复活旧成功或重复计划；Task3/6/7测试覆盖。
3. 多来源回答在删除非首来源后不得残留该来源正文；Task1/7/10覆盖真实删除与恢复。
4. 目标依赖成环、跨课联系与无有效来源，不得产生伪前置推荐或无限遍历；Task4/5覆盖。
5. 10000节点＋大量作答并发读取与确认，不能N+1／长写锁／内存拼全回答；Task2/10覆盖，保留C的3007.3ms慢样本。

## 文件职责

- 后端`filemate/course_graph/learning_schema.py`（仅SQL）、`question_links.py`（题目审核映射）、`learning_commands.py`（确认／逆操作协议）、`learning_evidence.py`（只读训练事实）、`learning_work.py`（有限运行租约）、`practice.py`（草稿审核）、`learning_paths.py`（规则规划与计划事务）、`cross_links.py`（跨课导航）、`assistant.py`（有界问答／Agent）、`learning_api.py`（严格HTTP）。
- `execution/storage.py`只追加migration import／注册；privacy扩展删除影响和恢复失效；现役quiz判题不另写。
- 前端`types/courseLearning.ts`、`services/api.ts`；`course-graph/learning-state.ts`与`assistant-state.ts`为可测试状态机；`components/course-graph/CourseLearning.vue`、`CoursePractice.vue`、`CoursePathPreview.vue`、`CourseAssistant.vue`按需呈现，C壳仅接线。
- `evaluation/course_graph_quality.py`计算指标，`scripts/acceptance/course_growth_benchmark.py`工程证据；相应测试进入现有测试目录。文档在每任务同步合同，最终汇总研究协议与技术报告。

---

### Task 1: 迁移、题目显式映射与数据边界

**Files:** Create `filemate/course_graph/learning_schema.py`, `learning_commands.py`, `question_links.py`, `filemate/tests/course_graph/test_learning_links.py`; Modify `filemate/execution/storage.py`迁移31后、`filemate/course_graph/privacy.py`, `filemate/docs/API_SPEC.md`。

**Interfaces:**
- Consumes: `SQLiteStorage`, `require_course`, `transaction`, `record_change`, `data_actions.issue/check/finish`；C `read_workspace_snapshot`。
- Produces: `question_candidates(storage,cid,nid,*,q='',offset=0,limit=50)->dict`；`preview_question_links(storage,cid,nid,items:list[dict],active=True)->dict`；`confirm_question_links(storage,cid,nid,items,active,confirmation_token,request_key,confirmed)->dict`。items唯一`artifact_id/question_index/question_digest`，最多20，题目本身不作为客户端可信内容。
- Produces: `transition_learning_operation(storage,cid,operation_id,action,confirmation_token,request_key,confirmed)->dict`与`preview_learning_transition(...)`；使用`kg_changes`的`learning_*`kind，逆操作对当前状态摘要检查，不修改其他操作。

- [x] **Step 1: 写RED。** `test_schema_31_upgrade_preserves_old_rows`断言schema32、旧Source／Artifact不变、新FK／索引；`test_candidates_do_not_link_by_matching_word`断言0映射；`test_link_requires_preview_and_current_question`断言未确认422、改题后409；`test_duplicate_confirmation_is_single_receipt`断言两次同token仅1映射/1实际操作；`test_foreign_course_and_artifact_refused`、`test_unlink_undo_preserves_attempts`；删除任一work依赖来源同时删除work、预览计数/指纹改变；备份恢复使运行interrupted且epoch不同。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_learning_links.py -q`。Expected: missing learning schema/module/behavior，不是测试夹具错误。
- [x] **Step 3: 实现migration32和显式映射。** SQL表／字段按设计，UUID/题号/摘要唯一与双端FK，工作来源删除触发器；候选只来自当前课程所属Source的有效非只读题集，已移出来源仍有历史但不可新关联。复用现役validate_question并计算摘要；确认在短事务再读，记录前后state与ID，复用token回执。恢复中断旧work，清`course_graph_learning_%`预览；来源删除影响包含新增对象，日志不复制题目／引文。
- [x] **Step 4: 跑GREEN。** 本卡及`test_storage.py test_privacy.py test_final_regressions.py`。Expected: 0失败，PRAGMA FK空，旧31数据可读；同步新表／删除／恢复API合同。
- [x] **Step 5: 提交。** `feat(graph): 增加课程学习映射与迁移恢复边界`。

### Task 2: 真实训练状态、薄弱点与时间线

**Files:** Create `learning_evidence.py`, `filemate/tests/course_graph/test_learning_evidence.py`; Modify API_SPEC。

**Interfaces:**
- Consumes: Task1显式映射、现役quiz_attempts/wrong_questions/题目修订cutoff、C课程快照。
- Produces: `learning_snapshot(storage,cid,*,now:datetime)->dict`含`course_id,graph_digest,evidence_digest,rule_version,nodes`（ID→真实摘要）；`node_learning_evidence(storage,cid,nid,*,now,offset=0,limit=50)->dict`含状态、窗口、计数、question_refs、分页attempts/wrongs/plans、excluded_count；`list_learning_nodes(...,status=None,offset=0,limit=50)`分页摘要。

- [x] **Step 1: 写RED。** `test_empty_once_and_stable_windows`断言空暂无、1次已有、3题跨2日才稳定；`test_recent_wrong_and_due_override_stable`断言7天边界包含且到期优先；`test_future_invalid_and_revised_attempts_excluded`断言未来/坏时间/修订前均计排除；`test_shanghai_midnight_is_distinct_day`；`test_merged_members_deduplicate_attempt_and_undo_split`按attempt_id真实去重；`test_removed_source_retains_history_but_not_active_support`；`test_plan_completion_never_creates_correct_attempt`；`test_query_count_does_not_grow_per_concept`比较100/1000节点SQL计数有界、只映射题集被读取。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_learning_evidence.py -q`。Expected: missing module。
- [x] **Step 3: 实现一次SQLite读快照批量聚合。** 规则纯函数注入时钟，Asia/Shanghai日期；只用有效映射、当前题摘要、真实作答、匹配错题快照；合并聚合不改原ID。7/30天窗口、统计与记录可核对；错题未掌握且due<=now为到期，坏时间不当到期。unknown不补0分，不返回mastery_rate。
- [x] **Step 4: 跑GREEN。** Task1+2与旧`test_graph_storage.py/test_knowledge_graph.py`。Expected: 新旧0失败，输出含规则与真实依据；同步状态合同。
- [x] **Step 5: 提交。** `feat(graph): 按真实学习证据计算课程训练状态`。

### Task 3: 有界练习草稿、人工审核与正式题集

**Files:** Create `learning_work.py`, `practice.py`, `filemate/tests/course_graph/test_course_practice.py`；Modify privacy（仅work恢复与来源依赖必要部分）、API_SPEC。

**Interfaces:**
- Consumes: Task1/2快照和命令；`LLMClient.call_structured`, `validate_questions`, 现役Artifact与`admit_plan`。
- Produces: `LearningWorkService(storage,clock)`的`claim(cid,kind,input,request_key,sources,graph_digest,evidence_digest)`, `finish(work_id,epoch,result)`, `fail(...)`, `cancel(...)`, `get(...)`。kind=`practice/answer`；epoch+状态+输入版本核对，重复键仅返回已持久化结果，不重发模型。
- Produces: `PracticeService(storage,provider_factory,clock)`的`generate(cid,nid,difficulty,count,mode,request_key,allow_external_model=False)->dict`、`get(cid,work_id)->dict`、`preview(cid,work_id,decisions)->dict`、`confirm(...,decisions,confirmation_token,request_key,confirmed)->dict`。decision包含题序、accept/reject及可选修订question；不信客户端validation标志。

- [x] **Step 1: 写RED。** `test_local_cloze_is_supported_not_llm`；`test_model_requires_consent_and_runs_once_outside_write_lock`用可控provider检查其他连接可写；`test_malformed_answer_or_unknown_quote_cannot_confirm`；`test_human_review_required_before_artifact`；`test_confirmed_selection_creates_one_real_artifact_and_links`；`test_cancel_restore_source_change_blocks_late_finish`；`test_timeout_and_provider_error_are_persisted_failure_without_secret`；`test_rate_and_running_budget`断言第31次/并发第二次拒绝、20秒/1次调用参数真实传入；`test_same_key_does_not_resend_after_uncertain_response`。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_course_practice.py -q`。Expected: missing service。
- [x] **Step 3: 实现规则／模型草稿与审核事务。** count1–5、difficulty三值；资料12000字、有效引用白名单、格式答案引用校验；模型失败不伪装fallback成功。领取work短事务，provider调用在锁外，完成核对epoch及版本；前述限额，错误只存安全码。确认先校验人工决策与当前work摘要，原子写现役Artifact＋映射＋回执，未答题不创建attempt/wrong。
- [x] **Step 4: 跑GREEN。** Task1–3+`test_quiz_api.py`（若实际路径不同以rg定位并ledger）及`test_privacy.py`。Expected: 同题集走现役quiz真实评分／错题，取消晚到不落成功。
- [x] **Step 5: 提交。** `feat(graph): 增加可审核的节点练习草稿`。

### Task 4: 可解释路径、目标范围与新增计划

**Files:** Create `learning_paths.py`, `filemate/tests/course_graph/test_learning_paths.py`; Modify learning_commands（计划逆操作）、API_SPEC、今日学习路由必要接线。

**Interfaces:**
- Consumes: Task2 `learning_snapshot`、有效确认关系、既有goals/StudyPlan/Artifact/admit_plan。
- Produces: `suggest_path(storage,cid,goal,*,concept_ids,chapter_id,goal_id,daily_minutes,days,now)->dict`，task含稳定concept_id/day_index、kind、依据IDs、duration_minutes；`preview_path(storage,cid,options)->dict`、`confirm_path(storage,cid,options,confirmation_token,request_key,confirmed)->dict`。 options同suggest参数，days1–7/daily5–180、最多7项；receipt=`operation_id,plan_id,artifact_id,affected`。

- [x] **Step 1: 写RED。** `test_dependency_direction_and_cycle_refusal`；`test_due_wrong_goal_priority_has_record_ids`；`test_budget_and_seven_task_ceiling`；`test_inactive_or_cross_course_support_not_prerequisite`；`test_confirm_stale_evidence_refused`；`test_existing_manual_plan_unchanged_and_duplicate_single_new_plan`；`test_undo_restore_keeps_completed_days_and_detects_user_edit`；`test_today_links_plan_and_completion_is_separate_evidence`。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_learning_paths.py -q`。Expected: missing planner。
- [x] **Step 3: 实现有界拓扑与透明优先。** 使用已确认有效依赖和真实状态，不按AI分数；目标范围与日期／时间预算进入预览摘要，日计划沿现役格式；加入任务受`admit_plan`约束；计划新增、关联、token回执同事务。逆操作只归档本计划，完成天不擦除；用户编辑内容后冲突而非覆盖。
- [x] **Step 4: 跑GREEN。** Task1/2/4+现役daily-coach／study-plan子集；真实今日队列能定位新plan，完成回读不增加答对次数。Expected:0失败。
- [x] **Step 5: 提交。** `feat(graph): 生成有依据且可撤销的课程学习计划`。

### Task 5: 人工跨课联系与严格学习API

**Files:** Create `cross_links.py`, `learning_api.py`, `filemate/tests/course_graph/test_learning_api.py`; Modify `api.py`注册新路由、learning_commands、API_SPEC。

**Interfaces:**
- Consumes: Task1–4服务与原`CourseRoute/StrictBody/Key/Identity/_enabled`。
- Produces: `preview_cross_link`, `confirm_cross_link`, `list_cross_links`，两端课程／概念作为唯一规范端点；只有`related`可写，逆操作复用learning_commands。
- HTTP: `GET /{cid}/learning/nodes`、`GET /{cid}/concepts/{nid}/learning`、`GET .../question-candidates`；`POST .../question-links/preview|confirm`；`POST .../practice-drafts`、`GET /{cid}/learning/work/{wid}`、`POST .../{wid}/cancel`、`POST .../{wid}/review/preview|confirm`；`POST /{cid}/learning/path/preview|confirm`；跨课`GET /{cid}/concepts/{nid}/related-courses`与`POST .../preview|confirm`；`POST /{cid}/learning/operations/{oid}/preview|confirm`。新GET参数严格禁止多余／重复项；新POST继承StrictBody，返回no-store。

- [x] **Step 1: 写RED。** 真ASGI `test_learning_routes_tenant_flags_validation_and_redacted_storage_failure`、`test_no_read_triggers_model_or_mutation`；`test_cross_link_navigation_only_cannot_change_evidence_or_plan`；`test_cross_link_endpoints_belong_to_current_tenant`；`test_reversed_pair_idempotent_and_revoke_undo`；`test_failed_confirm_does_not_partial_write`。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_learning_api.py -q`。Expected:404 missing routes。
- [x] **Step 3: 实现严格边界并同步调用合同。** 允许HTTP自带密钥仅现有受信POST模型路径，GET/非模型参数拒收；不更改全局身份／凭据流程。跨课关系不加入C依赖／D学习聚合，显示真实目标课程链接与失效说明。隐私删除、默认关闭读退回兼容旧图谱。
- [x] **Step 4: 跑GREEN。** Task1–5+`test_api.py/test_workspace_api.py`。Expected:新老接口0失败。
- [x] **Step 5: 提交。** `feat(graph): 接入课程学习接口与人工跨课联系`。

### Task 6: D工作台学习闭环与失败恢复

**Files:** Create前端`types/courseLearning.ts`, `course-graph/learning-state.ts`, `components/course-graph/CourseLearning.vue`, `CoursePractice.vue`, `CoursePathPreview.vue`, `filemate/web/tests/course-learning-state.test.mjs`；Modify `services/api.ts`, `CourseEvidence.vue`, `CourseWorkspace.vue`, `styles/course-workspace.css`及现役计划／错题深链必要处。

**Interfaces:**
- Consumes: Task5真实API；现役`submitQuizAttempt`、学习计划日更新和错题复习接口；C面板协调／canLeave。
- Produces: `createCourseLearningController(api,observe)`拥有`open(scope,cid,nid)`, `loadEvidence`, `chooseQuestion`, `submitAnswer`, `previewLinks/confirmLinks`, `generatePractice/reviewPractice/confirmPractice`, `previewPath/confirmPath`, `cancel`, `resetIdentity`, `dispose`；每个异步响应绑定scope/course/node/generation，预览令牌与请求键只在对应流程保留。

- [ ] **Step 1: 写RED。** node:test `late_read_cannot_cross_node_or_identity`、`answer_failure_retains_draft_and_retry_uses_same_version`、`confirm_receipt_dedupes_refresh_not_write`、`changed_options_invalidate_preview`、`no_auto_model_after_read_or_reopen`、`cancel_and_navigation_preserve_or_explicitly_discard`、`plan_completion_does_not_upgrade_training`。
- [ ] **Step 2: 跑RED。** `node --test filemate/web/tests/course-learning-state.test.mjs`。Expected:missing controller。
- [ ] **Step 3: 实现状态机与API类型。** 使用现有api受信凭据／AbortSignal；界面逐题大字、提交后解析／真实错题，草稿先审核后练习；没有数据给“关联题目／创建基础练习”具体入口，不生成样本。计划大按钮预览，显示目标／时间／每项原因；确认后可到今日学习／撤销。关联、跨课、历史按需面板，复用单弹层焦点／离开保护，保留C画布选择。
- [ ] **Step 4: 跑GREEN并真实浏览器。** node新旧course tests、`npm run build`；同合成账号节点→证据→错答→错题／复习→状态→计划→今日完成→图谱完成记录；390/768/1366宽、四主题、长题干／文件名、断网不丢答案，模型失败可重试。Expected:0失败／无横向溢出；记录实际屏幕与DB摘要。
- [ ] **Step 5: 提交。** `feat(graph): 接通节点训练复习与今日计划工作台`。

### Task 7: 有出处问答与只读有限Agent

**Files:** Create `assistant.py`, `filemate/tests/course_graph/test_graph_assistant.py`; Modify learning_api、API_SPEC、README环境变量。

**Interfaces:**
- Consumes: Task2真实事实、C有效来源／关系、Task3work协议、Task4路径预览。
- Produces: `GraphAssistant(storage,provider_factory,clock)`的`context(cid,question,concept_ids,chapter_id,goal_id)->dict`、`answer(...,mode,request_key,allow_external_model)->dict`、`propose_plan(cid,options)->dict`。context=`textbook_evidence,personal_facts,confirmed_relations,goal,coverage`；answer=`work_id,status,mode,textbook_evidence,personal_facts,suggestions,citation_ids,limitations,stale`，事实来自服务端而非模型数字。
- HTTP: `POST /{cid}/assistant/answer`（明确模型授权或rule模式）、`POST /{cid}/assistant/plan/preview`（至多4工具步骤）、读取Task3work；确认计划继续Task4合同。`FILEMATE_ENABLE_GRAPH_ASSISTANT=1`才新建助手请求，关闭仍可读旧work。

- [ ] **Step 1: 写RED。** `test_textbook_personal_facts_and_suggestions_separate`、`test_unknown_quote_or_personal_fact_id_rejected`、`test_injection_is_data_not_action`、`test_context_is_bounded_and_shows_coverage`、`test_provider_swappable_and_one_bounded_call`、`test_failure_or_no_model_not_fake_success`、`test_agent_max_four_read_steps_seven_tasks_no_write_before_confirm`、`test_deleted_second_source_removes_answer_and_preview`、`test_restore_or_evidence_change_marks_work_stale`、`test_flag_off_no_new_ai_work_but_read_results`。
- [ ] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_graph_assistant.py -q`。Expected:missing assistant。
- [ ] **Step 3: 实现有限工具与严格结构输出。** provider_factory允许替换；文本/引用ID白名单Pydantic，prompt明确不执行资料指令、无证据不下结论。只允许引用原始事实对象，模型建议独立；保存来源依赖、运行版本、输入覆盖。规则检索清晰标模式，模型失败不伪装。Agent没有任意工具执行器／SQL／画像／删除；只返回Task4预览，不返回可由模型调用的确认能力。
- [ ] **Step 4: 跑GREEN。** Task1–5/7+work取消隐私回归；实际外部服务无凭据时明确未测，适配器契约测试不冒充真实模型质量。
- [ ] **Step 5: 提交。** `feat(graph): 增加证据问答与有限学习助手`。

### Task 8: 助手交互与可解释计划预览

**Files:** Create `course-graph/assistant-state.ts`, `components/course-graph/CourseAssistant.vue`, `filemate/web/tests/course-assistant-state.test.mjs`; Modify CourseWorkspace/学习组件/services/api/types/courseLearning/styles。

**Interfaces:**
- Consumes: Task7 HTTP与Task6计划／结果状态机；`VITE_ENABLE_GRAPH_ASSISTANT=true`且课程开启才呈现助手新建入口。
- Produces: `createGraphAssistantController(api,observe)`绑定身份／课程／范围，send与cancel、读取持久化历史、显示过期结果、预览路径但确认沿D合同；不把外发授权保存在偏好。

- [ ] **Step 1: 写RED。** `consent_is_per_request_not_restored`、`late_answer_never_crosses_scope`、`network_unknown_does_not_duplicate_model_call`、`facts_are_read_only_and_failed_model_has_no_fake_answer`、`agent_preview_never_autoconfirms`、`history_reopen_is_read_only`。
- [ ] **Step 2: 跑RED。** `node --test filemate/web/tests/course-assistant-state.test.mjs`。Expected:missing module。
- [ ] **Step 3: 实现侧栏按需助手。** 教材／个人事实／建议分区、引用定位和覆盖说明可读；工作步骤与最多7任务可核对，一次主动作；取消、失败、重试、已保存与过期状态就地显示。手机单面板，无重复导航；默认读文字，无自动语音／摄像头。
- [ ] **Step 4: 跑GREEN并浏览器。** D+C全前端tests/build，rule问答真实接口、模型失败与取消、切课和身份、刷新历史、计划预览/确认不重复；五尺寸与键盘焦点。Expected:0失败／无横向溢出；外部模型未调不称已调通。
- [ ] **Step 5: 提交。** `feat(graph): 呈现可核对的课程助手与任务建议`。

### Task 9: 质量计算器与待确认研究协议

**Files:** Create `evaluation/course_graph_quality.py`, `filemate/tests/course_graph/test_graph_quality.py`, `docs/research/KNOWLEDGE_GRAPH_2_STUDY_PROTOCOL.md`; Modify evaluation README入口。

**Interfaces:**
- Produces: CLI `uv run python -m evaluation.course_graph_quality --gold <authorized human gold.json> --prediction <candidate.json> --output <new report.json>`；`evaluate_quality(gold,prediction)->dict`。gold包含授权／人工标注声明、概念ID集合、类型方向关系集合、逐候选引用/融合/错误关系人工判定，缺失则指标null并解释，不从AI自评推断真值；拒绝覆盖输出。

- [ ] **Step 1: 写RED。** 已知集合TP/FP/FN断言1/2、1/3、0.4等精确分数；零分母null；方向反转为错误；无授权/无人工gold不出质量成绩；缺判定不填0或1；CLI既有输出拒绝；synthetic=true贯穿。
- [ ] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_graph_quality.py -q`。Expected:missing calculator。
- [ ] **Step 3: 实现计算器并写协议。** 固定指标定义／分母／覆盖率，JSON schema版本与模型／prompt版本可追溯；协议按设计给三组、初步90人、分层随机、等量时间、盲评分、7天延迟、基线调整、预设两比较与Holm、缺失/退出、同意/删除、批准页。未批准不采集，不编结果。
- [ ] **Step 4: 跑GREEN。** 本卡+现有evaluation测试；只运行原创合成算例验证工具，报告明确“计算器回归，非系统质量成绩”。Expected:0失败且真实研究状态pending_approval。
- [ ] **Step 5: 提交。** `feat(evaluation): 增加图谱质量计算器与研究协议`。

### Task 10: 全账户链、工程规模与最终交付

**Files:** Create `scripts/acceptance/course_growth_benchmark.py`, `filemate/tests/course_graph/test_growth_lifecycle.py`, `test_growth_benchmark.py`, `docs/KNOWLEDGE_GRAPH_2_0_DE_DELIVERY.md`, `docs/KNOWLEDGE_GRAPH_2_TECHNICAL_REPORT.md`；Modify README/API_SPEC/执行记录/设计系统；脱敏实际证据`docs/audits/knowledge-graph-2-de-2026-10-23/`，DB/原日志`_working/kg-de-20261023/`。

**Interfaces:**
- Consumes: Task1–9真实API及B/C；CLI新绝对输出目录、100/1000/10000规模和额外证据密集负载，不用真实用户库。
- Produces: 注册测试账户D完整流程、E规则／失败／取消／计划链JSON和截图；性能按原始全部样本记录，进程资源与浏览器分开，未测null；协议／技术报告均链接实际结果和限制。

- [ ] **Step 1: 写RED。** lifecycle注册→登录→两数据结构＋第二课程→审核→人工题目映射→错答→复习→状态→路径预览/确认/重复/撤销/恢复→今日完成→规则问答→Agent预览→导出/删除第二来源/恢复→旧token拒绝/旧数据可读；benchmark新目录安全、精确规模／作答数、并发读与一次写、无N+1、迁移31→32、旧schema31备份、FK与失败恢复测试。
- [ ] **Step 2: 跑RED→实现夹具／基准→GREEN。** `uv run pytest filemate/tests/course_graph/test_growth_lifecycle.py filemate/tests/course_graph/test_growth_benchmark.py -q`。Expected: 全链真实数据库记录一致，合成标记不遗漏。
- [ ] **Step 3: 测工程与定位C慢样本。** 100/1000/10000各首1热5实际HTTP；证据密集至少10000attempts、并发4读＋重复确认、内存/DB/WAL记录；浏览器初始画布、选择/缩放/练习/搜索与故障。初始3秒目标、HTTP热最大2秒、交互无>200ms样本；不满足则保留失败、分析实际瓶颈并用行为／性能回归固定修复，不以抽样删失通过。
- [ ] **Step 4: 全量门禁。** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`；Expected: exit0，后端／前端／类型／构建／预算；24用户测试SHA逐一不变，diff check干净。已有warning/skip具体报告，真实模型与真人未验如实列出。
- [ ] **Step 5: 汇总文档并提交。** D/E逐要求矩阵、工程状态与科研依赖分别表述；交付架构、数据模型、有限Agent、规则方法、解释、实际结果和局限；迁移32回退须恢复备份与兼容代码，不伪称down migration。`test(graph): 记录知识成长全链与规模验收`。
- [ ] **Step 6: 一次独立整项审阅与修复。** 执行executing-plans全分支review-package、Review Focus及所有Ruling交给fresh reviewer；Critical/Important一轮RED→GREEN修复并全量门禁；Minor按规则记账，不反复派审。最终保留分支与工作区，不自动推送／部署，真实研究等待单独批准。

## 自审与执行授权记录

原需求D1–D6→Tasks1/2/3/4/5/6，D验收→10；E1/E2/E3→4/7/8，E4质量／协议→9、工程→10，E5→10。跨课人工联系→5；来源移出／彻底删除区别→1/2/7/10。所有写入共用预览／版本／回执，模型仅锁外运行，UI不发第二次不确定请求。已检查接口、限额、范围、失败恢复与用户既定技术栈一致。

用户已明示审阅全部后连续实施，故保存自审与builder check结果后执行，不再把常规实现细节变成审批问题；真人实验／生产发布仍不在这份工程授权内。
