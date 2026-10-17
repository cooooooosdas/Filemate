# 面试教练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已存在的面试链改为先保存回答、逐题反馈、可修改重答、以末次回答生成报告，并保留历史、明确授权和失败恢复。

**Architecture:** 在现役 SQLiteStorage、InterviewEvaluator 和 ReviewRepository 上增加独立 interview_coach 包，以不可变回答版本和有界分析运行管理状态；interview_turns 继续作为每题当前投影，保持现役调用方可读。Vue 页面复用现有准备、媒体与复盘能力，增加大字逐题主区和受版本约束的状态控制，不另建面试系统。

**Tech Stack:** Vue 3、TypeScript、Vite、现有 Element Plus／Tabler SVG；FastAPI、Pydantic、SQLite、Python／uv；pytest 和现有 Node test runner。无新增运行依赖。

**Spec:** [2026-10-16-coach-workflows-design.md](../specs/2026-10-16-coach-workflows-design.md)，2026-10-16 Q17 已确认完整设计。本文只实现该设计的共用引导与批次 A，编程和岗位分别另写计划。

## Global Constraints

- “真实学生日常使用与比赛演示同等重要”；演示使用明确标记的合成账户，不给正式账户植入样本统计。
- “最后一次提交始终是当前版本，不能用最高分或旧成功结果替代。”失败当前分数为空，显示待分析，历史结果只在历史中。
- “回答先保存，随后分析”；“每场最多一个在途分析，通过数据库原子认领保护”；模型最多初次请求加一次格式纠正，总截止 60 秒。
- “授权只属于当前场次，不能自动沿用到下一场。”不默认发送录像、照片、整份资料或其他会话；本地和私有资料限制优先。
- “问题正文桌面 28–32px、手机 24–28px；正文／操作 17px，说明 16px，辅助 15px”；操作目标至少 44px，按需 SVG、不用 Emoji、不新增远程字体。
- 默认文字和轻量状态动效、按需自然语音；输入、录音、切题和离页停止声音，语音失败保留文字，不自动换机械声。
- 只追加迁移；业务 schema 当前 26，治理 schema 当前 2；实施前重读最新列表后分配下一业务版本，不预占版本号，不改已发布迁移。
- API、schema、路由、环境变量变更同步调用方、测试及 README/API 文档；跨空间返回现役 404，不记录密钥、正文、源码或供应商异常原文。
- 每批使用当前候选独立证据，不累加历史测试数；真人学习效果、专家校准、真实设备和未实测外部服务保持独立未验收状态。
- 本轮不合并、推送或部署；保留原 OPT-02～05 与完整功能账本。新功能在 Task 9 验收前默认关闭。

## Review Focus

- 同一个提交／分析键因断网重发：返回原操作归属，不产生第二份回答或第二次模型调用；同键异文 409（Task 2、3、4）。
- 重答或撤销授权发生在模型返回前：旧运行无权更新当前投影，当前页和报告不会显示旧成功分数（Task 3、5、6）。
- 旧题文本带换行、英文、超长内容或已有损坏 JSON：历史原文与原时间保留；无效分析不能阻断其他会话、伪造分数或心理结论（Task 1、5、7）。
- 恢复包含运行中记录的备份，或恢复 schema 26 旧备份：不重放模型、不复活授权，保留回答并允许主动重试（Task 8）。
- 中文输入法合成、录像结束回调或旧路由请求迟到：不截断输入、不将前次媒体挂到新回答、不覆盖新会话（Task 6、7、9）。

---

## 0. 实施上下文与文件职责

现役工作树为 `C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`。设计提交为 `ce50f4b`，其父代码提交为 `18b6d77c`。D 盘只放临时证据。开始实施时核对分支、现役代码和下面锚点；当前有 24 个既有测试文件改动，记录其差异，禁止顺带暂存、覆盖或重置。需要修改其中的文件时仅形成自己的最小差异并人工检查，不将整文件既有修改纳入提交。

| 文件 | 责任／当前锚点 |
| --- | --- |
| `filemate/execution/storage.py` | 追加 schema、旧写入的版本同步；`init_schema:774`、`get_interview:2244`、`save_interview_turn:2303` |
| `filemate/interview_coach/{__init__,models,repository,commands,service}.py`（新增） | 类型、原子版本／操作、请求规范化和本地评价、受限分析；不把业务堆进 server.py |
| `filemate/interview_review/{content,repository,reports}.py` | 原句 JSON 校验、报告、清空与删除；保留现有职责 |
| `server.py` | 请求合同与薄路由；请求模型 2729 起，面试路由 4319–4631；认证与空间解析复用现役中间件 |
| `filemate/understanding/{interview,interview_practice}.py` | 现有评估、规则追问和跨场记忆 |
| `filemate/study/evidence_profile.py`、`filemate/career/evidence.py`、`filemate/portfolio/resume.py` | 当前证据与历史快照标识；不增加核心能力推断 |
| `filemate/web/src/types/interviewCoach.ts`（新增）、`types/interviewReview.ts`、`services/api.ts` | 新合同与现役 API 兼容 |
| `filemate/web/src/interview/{coach-state,useInterviewCoach,useInterviewCoachSpeech}.ts`（新增） | 纯状态投影、异步命令、按需朗读和资源释放 |
| `filemate/web/src/components/InterviewCoachPanel.vue`（新增） | 当前问题、作答、原句反馈、重答与明确下一步 |
| `filemate/web/src/views/Interview.vue`、`components/InterviewReviewPanel.vue`、`styles/interview-practice.css` | 挂载新交互、整场报告和历史／媒体，不重复导航 |
| `filemate/operations/{personal_backup,backup,workspace_privacy}.py` | 新表备份恢复与删除；只改确实需要的校验／规范化，保留现役动态枚举 |
| `filemate/tests/test_interview_coach_{storage,analysis,api,evidence,privacy}.py`（新增） | 各任务定向回归；夹具只使用 tmp_path、合成模型／记录 |
| `filemate/web/tests/interview-coach-{state,speech}.test.mjs`（新增） | 现役 Node runner，复用直接导入 TS 的做法 |
| `scripts/acceptance/interview_coach.mjs`、`docs/INTERVIEW_COACH_DELIVERY_2026-10-16.md`（新增） | 浏览器场景与候选证据；实际执行日期变更则同步文档文件名 |
| `scripts/verify.ps1`、`filemate/docs/API_SPEC.md`、`README.md`、`design-system/filemate/MASTER.md`、`docs/PRODUCT_OPTIMIZATION_EXECUTION_2026-10-16.md` | 接入门禁与准确交付状态，不把部分功能写成全部完成 |

下文新名称是本计划固定的实现合同，不是现有代码声明。除已列明职责的拆分外，不重构无关模块。

## 1. 固定数据与公开合同

### 数据模型

采用五张增量表，均属于当前空间数据库；所有时间为带时区 ISO，原历史时间无法判断时保留原字节并标 `legacy_unverified`，不以迁移时间充作作答时间。

1. `interview_answer_attempts`：`attempt_id` 主键，`interview_id`、`turn_id` 外键级联删除；`version>=1`、`question_index`、原 `question`、`question_digest`、原 `answer`、规范化请求 `input_digest`、`fluency_metrics`／`visual_metrics` JSON、`created_at`、`origin`（`migrated/legacy_write/coach`）。唯一 `(turn_id,version)`；索引 `(interview_id,question_index,version)`。不把可变分析或授权写进不可变回答。
2. `interview_coach_state`：场次外键主键，`revision`、`displayed_index`、`phase=question/feedback/summary`、`entered_indices`、`external_consent=false`、`consent_revision`、非敏感 `provider_identity`、`updated_at`。旧会话在启动回填时从现有进度初始化，新会话在create_interview事务中初始化；未授权是默认值。snapshot读取不补造状态，结构损坏明确显示不可写并保留原数据。
3. `interview_coach_analysis_runs`：`run_id` 主键，场次与回答版本外键级联；`attempt_seq`、`request_key`、`input_digest`、`consent_revision`、`review_revision`、`provider_identity`、`model`、`prompt_version`、`rubric_version`、`status`、`deadline_at`、`lease_until`、`evaluation` JSON、有限 `error_code`、创建／结束时间。唯一 `(attempt_id,attempt_seq)`；`running/cancelling` 的 `(interview_id)` 部分唯一索引，历史按 `(attempt_id,attempt_seq)` 查询。
4. `interview_coach_actions`：场次外键、`request_key`、`kind`、`input_digest`、`result_refs`、`created_at`；主键 `(interview_id,request_key)`。操作回执只存受限 ID／版本／目标位置，不重复存原文或密钥；用于提交、前进、授权和分析的重复请求识别。
5. `interview_coach_questions`：场次外键、`question_index`、`question`、`question_digest`、`entered_at`；主键 `(interview_id,question_index)`。仅记录已进入题目，进入后冻结；旧已作答题从 turn 原文回填，未作答的当前题在旧会话导入时冻结。

当前回答由同题最大 version 决定，不增设与 attempts 互相引用的 current_attempt 外键。`interview_turns` 的 answer、指标、评分、反馈是该版本的兼容投影；原 turn_id、首次 answer_key／answer_digest 保留。新版本或新分析运行开始时，当前内容分数清空，原 llm 结果留在运行历史；旧非空 `turns.score` 与 `sessions.overall_score` 列仍按现役约定存 0，但公开读取必须在无有效模型样本时为 null，不将占位 0 作为统计。合法的真实模型0分仍是有效样本。

SQL migration 只创建表和索引；新增 `backfill_legacy_attempts(conn: sqlite3.Connection) -> int`，在 schema 初始化后、开放请求前的独立事务中完整回填。失败回滚该次全部回填、启动失败；再次启动幂等重试，不能提供部分回填服务。缺少version1的旧turn才回填；新turn随后由同事务writer捕获，不能凭读取时投影差异制造新回答。历史有效分析转为已有attempt关联的成功运行，历史缺少模型／提示词版本标 legacy_unknown，结束时间未知则为空；原始异常分析保留而不当有效分。新／旧写入均在同一事务维护版本与投影，避免两套事实。

### Python 与 TypeScript 公共类型

- `AttemptView`：上述不可变字段、`analysis_status: unrequested|running|succeeded|failed|cancelled|interrupted`、当前 `score: float|None`、当前 `evaluation`、`latest_run_id: str|None`、`data_error: bool`；历史可读取各分析运行。内部 `cancelling` 对外显示 cancelled、仍占用分析槽。
- `CoachSnapshot`：`session`（兼容 InterviewSession）、`revision`、`displayed_index`、`phase`、`external_consent`、`consent_revision`、`provider_identity`、`current_attempt: AttemptView|None`、`active_run_id: str|None`、`pending_retries: list[str]`。不夹带其他场次数据。
- `CoachMutationResult`：`snapshot: CoachSnapshot`、`receipt: {kind,request_key,attempt_id?,run_id?,target_index?}`。重发回原操作归属和最新快照；前端核对 receipt 后再展示，不能误把旧响应当新提交成功。
- `SubmitAnswer`：`answer`（非空白，1–12000 字符）、`question_index`（0–100）、`request_key`（现役16–80位字母数字／下划线／短横线）、`expected_revision`、`expected_attempt_id: str|None`、可选既有 `InterviewFluencyMetrics`／`VisualMetrics`；问题文字与题目摘要由服务端读取，不信任客户端改题。
- `AnalysisCommand`：`attempt_id`、`request_key`、`consent_revision`、`expected_revision`；明确重试使用新 key，同 key不重发模型。
- `AdvanceCommand`：`from_index`、`expected_attempt_id`、`expected_revision`、`request_key`；`ConsentCommand`：`allowed`、`expected_revision`、`request_key`。客户端不得自传官方 provider 身份，服务端从当前配置得到非敏感身份。

### HTTP 合同（均沿用 ApiResponse、认证、CSRF／写保护与空间隔离）

| 方法／路径 | 请求 → 返回 |
| --- | --- |
| `GET /interviews/{id}/coach` | 无 → `CoachSnapshot`；仅显式读自己的场次，不发模型 |
| `POST /interviews/{id}/coach/answers` | `SubmitAnswer` → `CoachMutationResult`；首次回答推进旧 submitted_index，显示仍停本题 feedback；重答不推进 |
| `GET /interviews/{id}/turns/{turn_id}/attempts?limit=20&before_version=...` | 1–100条，版本倒序、下一游标；只取同题历史 |
| `POST /interviews/{id}/coach/consent` | `ConsentCommand` → `CoachMutationResult`；撤销重复幂等，不自动申请模型 |
| `POST /interviews/{id}/coach/analysis` | `AnalysisCommand` → `CoachMutationResult`；同步、有界，回答已在之前独立保存 |
| `POST /interviews/{id}/coach/advance` | `AdvanceCommand` → `CoachMutationResult`；进入下一题或 summary，不重新提交回答 |

分析成功与失败均先持久运行结果。模型未配置／外部失败返回安全502；治理超额429、治理故障503，本地／关闭503、私有资料限制403、参数422、冲突409、跨空间404保留。错误响应提供受限 `run_id/attempt_id/error_code/retryable`（不含供应商正文），客户端随后 GET 恢复快照。重复失败 key 返回同一失败与运行 ID；running 重复 key返回当前快照，不重放请求。GET 的过期运行只做终态规范化，不发起 AI。

`FILEMATE_ENABLE_INTERVIEW_COACH=0`（默认）拒绝所有新 coach 写接口、保留 coach／历史只读；`VITE_ENABLE_INTERVIEW_COACH=false`（默认）使用现有交互。现有 REVIEW 总开关优先，关闭后拒绝分析和报告写入，但保留保存文字和读取回答能力。个人导出／删除不受新开关阻断。

---

### Task 1: 追加版本模型并兼容旧写入

**Files:** 新增 `filemate/interview_coach/__init__.py`、`models.py`、`repository.py`；修改 `filemate/execution/storage.py:593,774,2205,2303`、`scripts/verify.ps1`；新增 `filemate/tests/test_interview_coach_storage.py`。

**Interfaces:** 新增 `backfill_legacy_attempts(conn: sqlite3.Connection) -> int` 和 `record_attempt_from_turn(conn: sqlite3.Connection, turn_id: str, *, origin: str) -> AttemptView`；后者从当前 turn 原文构造版本，只能在调用者事务内使用。提取 `SQLiteStorage._save_interview_turn_tx(self, conn: sqlite3.Connection, *, payload: dict[str, Any], origin: str) -> str`，payload 字段与现有 save 参数一一对应，返回 turn_id，不 commit。原 `save_interview_turn` 签名不变，调用 helper 后 commit，并返回旧会话结构；helper 插入 turn、版本、冻结问题与原进度／事件，避免重复逻辑。

- [ ] **Step 1:** 建临时库夹具 `store`（tmp_path、init_schema、close）；以当前26迁移 SQL构造旧库。添加 `test_upgrade_backfills_once_without_rewriting_raw_turn`：

  ```python
  assert (attempt.version, attempt.answer, attempt.created_at) == (1, original, old_created_at)
  assert turn.turn_id == original_id
  assert second_init_attempt_count == 1
  ```

  添加注入回填中途失败、坏 JSON和缺失来源样例，断言 `rollback_attempt_count == 0`、原字节不变、重启可恢复。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_storage.py -q`，确认因缺新表／函数而 FAIL，记录原因；环境缺依赖不算红灯。
- [ ] **Step 3:** 实现第1节模型、五张表和启动回填；把旧 helper 写入与版本捕获置于同一事务。create_interview同步初始化state和首题冻结记录；legacy_write在返回原链下一题时同步更新显示位置并冻结该题，coach写入只保留本题反馈位置、下一题由advance冻结。业务迁移版本实施时串行分配；新包和本批测试加入 verify 的 ruff目标。不改既有24份脏测试。
- [ ] **Step 4:** 同命令 PASS；补 `test_legacy_save_is_atomic_with_version_capture`，注入版本插入失败后断言 `turn_count == 0`、`current_index == 0`；执行现有 `uv run pytest filemate/tests/test_storage.py filemate/tests/test_interview_review.py -q`，新旧用例均通过。
- [ ] **Step 5:** 仅暂存本任务文件，`git diff --cached --check` 后提交 `feat(interview): 增加不可变回答版本与旧记录迁移`。

### Task 2: 原子保存、重答与显式推进

**Files:** 修改 `filemate/interview_coach/repository.py`；新增 `commands.py`（请求规范化和本地评价）；扩展 `test_interview_coach_storage.py`；现有 `interview_practice.py` 只复用 grounded_followup，不改题库规则。

**Interfaces:** `CoachRepository(storage: SQLiteStorage)`；`snapshot(interview_id: str) -> CoachSnapshot`、`submit(interview_id: str, command: SubmitAnswer) -> CoachMutationResult`、`advance(interview_id: str, command: AdvanceCommand) -> CoachMutationResult`、`list_attempts(interview_id: str, turn_id: str, *, limit: int=20, before_version: int|None=None) -> dict[str, Any]`。`commands.local_evaluation(answer: str, fluency_metrics: dict[str,Any]|None, *, speech_language: str) -> dict[str,Any]` 复用 InterviewEvaluator(None) 的纯本地路径，零外发。

- [ ] **Step 1:** 写 `test_submit_then_reanswer_keeps_turn_and_reading_position`：

  ```python
  assert turn_id_1 == turn_id_2
  assert versions == [1, 2]
  assert (snapshot.session['current_index'], snapshot.displayed_index, snapshot.phase) == (1, 0, 'feedback')
  assert snapshot.current_attempt.score is None
  ```

  写 `test_two_connections_same_key_commit_once`：用两个独立 SQLiteStorage连接和 barrier，断言 `attempt_count == 1`、`action_count == 1`、同回执；同键异文／不同kind断言409语义冲突。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_storage.py -q`，确认新行为 FAIL。
- [ ] **Step 3:** 实现 BEGIN IMMEDIATE 内检查回执→核对预期版本→首次沿用 Task1 helper／重答更新投影→失效旧报告和运行写资格→保存回执→commit。外部请求和规则追问在事务外计算，提交时再核对指纹。推进冻结下一题，重答已结束场次仍可用；初次写最后题可令旧 status completed，但 phase维持 feedback直至显式继续。维护 summary和回看位置，不复写已进入题目。
- [ ] **Step 4:** 增加 `test_advance_refreshes_only_unentered_followup`、`test_stale_revision_keeps_both_answers_and_draft_conflict`、`test_pagination_never_crosses_session`；断言重复advance回执同一target、已进入题的digest不变、重答不重复目标完成事件。旧已完成场次首次进入默认summary；从历史重答可选任一已答题，保存后displayed_index回该题、submitted_index不回退；继续到已答下一题显示其feedback，未答显示question，越过末题为summary。上述专项 PASS。
- [ ] **Step 5:** 提交 `feat(interview): 支持重答版本与显式切题`，只包含本任务差异。

### Task 3: 授权、有界分析和迟到保护

**Files:** 新增 `filemate/interview_coach/service.py`；修改 repository、models、`filemate/interview_review/content.py:104`、`filemate/interview_review/repository.py:122`、`filemate/understanding/interview.py:311`；新增 `filemate/tests/test_interview_coach_analysis.py`。

**Interfaces:** `CoachRepository.set_consent(id: str, command: ConsentCommand, *, provider_identity: str) -> CoachMutationResult`、`claim_analysis(id: str, command: AnalysisCommand, *, provider_identity: str, model: str, one_shot_consent: bool=False) -> dict[str,Any]`、`finish_analysis(run_id: str, *, evaluation: dict[str,Any]|None, error_code: str|None) -> CoachSnapshot`、`interrupt_expired(id: str, *, now: datetime) -> int`；`CoachAnalysisService(storage: SQLiteStorage, llm_factory: Callable[[],Any]).analyze(id: str, command: AnalysisCommand, *, one_shot_consent: bool=False) -> CoachMutationResult`。`analyze_content(..., *, budget_seconds: float=45.0) -> dict` 和 `InterviewEvaluator.evaluate(..., analysis_budget_seconds: float=45.0)`为兼容追加关键字，新教练传60，旧调用默认45。

- [ ] **Step 1:** 写 `test_analysis_claim_is_unique_across_connections`：两个连接同键发起仅 `provider.calls == 1`，不同键在running期间被拒、回答保留；写 `test_late_success_after_reanswer_or_revoke_never_projects`，用Event控制真实函数进入/返回：

  ```python
  assert snapshot.current_attempt.attempt_id == newest
  assert snapshot.current_attempt.score is None
  assert snapshot.current_attempt.latest_run_id != old_run_id
  ```

  以不同provider身份断言需重新授权，密钥不入库。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_analysis.py -q`，确认新行为 FAIL。
- [ ] **Step 3:** claim短事务后释放写锁再调用既有 LLMClient，保持空间和请求独立BYOK上下文；实际两次格式请求分别走治理账本、`retry=1`（该客户端含义为总尝试1次）。monotonic合计60秒，每次不超过剩余且最多30秒；仅结构／原句错误纠正一次，429／网络错误不后台重试。JSON校验仍使用现有四维／六类与逐字引用；格式／原句／超时失败当前无分数。
- [ ] **Step 4:** 用 `deadline_at=开始+60秒`、`lease_until=开始+65秒` 保留运行槽；取消／重答把旧running改cancelling并撤销写资格，直到返回或租约到期才释放，避免立即新建并发调用。结束按 attempt、consent_revision、review_revision、provider、run状态、截止和最新版本做CAS；旧 ReviewRepository.cancel 在同一事务增加既有revision并将该场coach运行标cancelling，新增 `CoachRepository.cancel_analysis(id: str) -> CoachSnapshot` 复用同一操作。clear和delete也使上述revision校验失效，旧analyze入口不能绕过。超时迟到不可写，过期标interrupted且从不自动重放。网络超时依赖现有适配器执行，不能声称可强杀第三方已接收请求或保证零重复计费。
- [ ] **Step 5:** 增加 `test_repeated_failed_key_is_not_reexecuted`、`test_only_format_error_gets_second_call_within_60_seconds`、`test_budget_429_and_unavailable_503_preserve_answer`、`test_log_and_error_never_contain_secret_or_answer`。上述专项和 `uv run pytest filemate/tests/test_interview_review.py filemate/tests/test_llm_client.py filemate/tests/test_runtime_governance.py -q` PASS。显式重试新key才能新增运行，开始新运行清当前成功投影，旧成功留历史。
- [ ] **Step 6:** 提交 `feat(interview): 约束逐题分析授权并阻止迟到覆盖`；若需修改原脏文件 `test_interview_ai.py`，只暂存自己的差异。

### Task 4: 接入 API、旧客户端和功能开关

**Files:** 修改 `server.py:2729,4319–4631`、`filemate/docs/API_SPEC.md`、`README.md`；新增 `filemate/tests/test_interview_coach_api.py`。

**Interfaces:** 实现第1节全部新路由；服务层返回 Pydantic/普通dict均统一 ApiResponse。新 coach 开关读取函数 `_require_interview_coach_write_enabled() -> None`；旧 `answer_interview`、`analyze_interview_turn` 保留请求／响应主形状。

- [ ] **Step 1:** 在新测试文件内定义临时API夹具（沿用 test_interview_review.py:395 的导入隔离方式，不复制现有真实配置）。`test_answer_is_readable_while_model_is_blocked` 断言保存返回后 GET立刻可见、health仍可响应；`test_api_duplicate_and_foreign_space` 固定断言：

  ```python
  assert first['receipt'] == repeated['receipt']
  assert foreign_snapshot.status_code == 404
  assert foreign_submit.status_code == 404
  ```

  `test_flags_preserve_text_and_read_only_history` 断言关闭新写503但旧文字回答和历史读取成功。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_api.py -q` 确认缺路由而 FAIL。
- [ ] **Step 3:** 薄路由调用 Task2/3；旧answers同样先保存本地结果再可选分析，不再因模型失败丢回答。旧start仅在 `allow_external_analysis is True` 时记录本场明确授权；未明确授权返回待分析，不因None隐式外发。旧analyze的 `external_consent=true`仍可单次授权，但不得升级为后续自动授权；一次授权也绑定当前consent_revision，撤销优先。旧首次请求键始终可查，重答不能覆写其key／digest。legacy分析必须写运行历史和投影，不能绕过新并发控制。
- [ ] **Step 4:** 六种专项、知识讲解、资料/错题私有模式、复盘总开关、英语speech_language、目标完成与Agent轨迹逐项回归；完成事件与练习记忆只在真正状态变化写一次，重答更新当前摘要而不再完成目标。参数422、冲突409、治理429/503和安全502按合同返回。专项及 `uv run pytest filemate/tests/test_interview_review.py filemate/tests/test_feature_closeout.py -q` PASS。
- [ ] **Step 5:** 同步API字段、状态、分页、授权默认值、错误细节和两个开关默认关闭；README标开发中候选。提交 `feat(api): 接入面试教练并兼容既有训练流程`。

### Task 5: 报告和所有下游只引用当前有效版本

**Files:** 修改 `filemate/interview_review/{reports,repository}.py`、`filemate/execution/storage.py:get_interview,get_learning_analytics,get_source_lineage`、`filemate/understanding/interview_practice.py`、`filemate/study/evidence_profile.py`、`filemate/career/evidence.py`、`filemate/portfolio/resume.py`、`filemate/web/src/types/interviewReview.ts`；新增 `filemate/tests/test_interview_coach_evidence.py`。

**Interfaces:** `current_attempt_projection(conn: sqlite3.Connection, turn_id: str) -> dict[str,Any]` 放repository中，storage与报告复用；`attempt_comparison(conn: sqlite3.Connection, turn_id: str) -> dict[str,Any]` 返回首末文本／原句、版本元信息及 `scores_comparable`，不同prompt／rubric／model或任一失败为false。报告仍兼容version2.4读取，新增 `attempt_id`、`attempt_version`、`analysis_status`、`analysis_run_id`、`source_revision`、首末比较和明确部分分析范围；修订增量是可选字段而不是丢弃旧报告。

- [ ] **Step 1:** `test_failed_last_attempt_excluded_everywhere`：初答80、末答失败：

  ```python
  assert (report['assessed'], report['overall_score']) == (0, None)
  assert growth['metrics']['interview']['sample_count'] == 0
  assert historical_first.score == 80
  ```

  岗位／简历无当前80分；`test_comparison_requires_matching_provenance` 断言异版本 `scores_comparable is False`，有原句无编造进步。`test_malformed_current_json_keeps_raw_and_excludes_score`断言同场其他健康回答仍可看。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_evidence.py -q` 确认新行为 FAIL。
- [ ] **Step 3:** get_interview仅增可选版本字段，报告digest绑定当前attempt和有效run，不把读位置／分页历史纳入报告输入。重答／清空／重试使旧报告引用失效；原Artifact保留历史身份。每次变更同步现役场次缓存分，公开get_source_lineage改从关联场次的已核验当前投影汇总，不能继续用current_index>0就把缓存占位0当均分；增加真实模型0分仍被计入的反例测试。成长证据时间取当前attempt原提交时间而非首次turn时间；历史岗位匹配／简历快照保留且标所引版本，展示时标过期，不静默重写。练习记忆检索使用当前版本，撤销／失效的旧分数不能进入提示。
- [ ] **Step 4:** 专项及 `uv run pytest filemate/tests/test_evidence_profile.py filemate/tests/test_career.py filemate/tests/test_p1_resume.py filemate/tests/test_p1_growth_report.py filemate/tests/test_interview_review.py -q` PASS；JSON／Markdown／PDF包含当前原文与已分析题数，导出只作模型参考标识，不把本地视觉写成情绪百分比。
- [ ] **Step 5:** 提交 `fix(interview): 让报告与成长证据跟随末次回答`。

### Task 6: 前端合同与可恢复状态

**Files:** 新增 `filemate/web/src/types/interviewCoach.ts`、`interview/coach-state.ts`、`interview/useInterviewCoach.ts`、`filemate/web/src/types/env.d.ts`、`filemate/web/tests/interview-coach-state.test.mjs`；修改 `services/api.ts:1015–1146`。现役通过 `vite/client` 提供环境类型，新env.d.ts只补新开关声明。

**Interfaces:** API函数 `getInterviewCoach(id): Promise<CoachSnapshot>`、`submitInterviewCoachAnswer(id,input): Promise<CoachMutationResult>`、`setInterviewCoachConsent(id,input)`、`analyzeInterviewCoachAttempt(id,input)`、`advanceInterviewCoach(id,input)`、`getInterviewAttempts(id,turnId,options)`对应第1节合同，全部在api.ts实现。`coach-state.ts` 导出 `projectCoach(snapshot: CoachSnapshot, pending: CoachClientState['pending']='idle'): CoachView`、`reduceCoach(state: CoachClientState,event: CoachEvent): CoachClientState`；`useInterviewCoach()`返回 snapshot、view、draft、pending、error和上述命令的UI动作及 `dispose(): void`。

`CoachClientState`包含 `sessionId:string|null, epoch:number, snapshot:CoachSnapshot|null, draft:string, composing:boolean, pending:'idle'|'save'|'analysis'|'advance'|'consent', error:{code:string,message:string}|null`；`CoachEvent`是 `open(id,epoch)`、`snapshot(id,epoch,value)`、`draft(text,composing)`、`pending(value)`、`error(id,epoch,value)`、`dispose` 的可辨识联合。`CoachView`含 `phase,questionIndex,question,attemptId,analysisStatus,score,feedback,analysis:ContentAnalysis|null,canSubmit,canAdvance,canRetry`；score仅由当前成功且有效run投影，操作能力同时考虑受限模式和pending。以上类型均在types/interviewCoach.ts定义，不引入第二套会话store。

- [ ] **Step 1:** 新 Node 用例 `late_response_cannot_replace_new_session`、`failed_latest_never_uses_historical_score`、`ime_composition_preserves_draft`、`retry_uses_original_submit_key_but_new_explicit_analysis_key`；使用断言：

  ```javascript
  assert.equal(next.sessionId, 'new-session')
  assert.equal(projectCoach(failedLatest).score, null)
  assert.equal(composingState.draft, '正在输入中文')
  ```

  另断言丢响应重发key不变而明确新分析key改变。
- [ ] **Step 2:** 在 `filemate/web` 运行 `node --test tests/interview-coach-state.test.mjs`，确认缺模块／行为而 FAIL。
- [ ] **Step 3:** 定义 request epoch和场次／attempt守卫；提交先更新已保存快照，再有有效授权时最多自动发起一次当前版本分析。重复刷新／恢复绝不重触发AI；断网／超时先GET确认服务端状态。HTTP失败保留draft；409保留草稿、显示重新读取和对照，不自动覆盖；一次授权状态由服务端读取，刷新不中断该场有效授权，provider改变先停止并重问。abort只停止本地等待，取消权限必须走服务端取消／撤销。
- [ ] **Step 4:** 相同Node命令、`npm test`、`npm run build`通过；再确认旧InterviewSession可缺新字段，旧URL内部ID同步不卸载页面。提交 `feat(web): 建立面试教练版本状态与恢复逻辑`。

### Task 7: 大字逐题界面、历史和自然语音

**Files:** 新增 `components/InterviewCoachPanel.vue`、`interview/useInterviewCoachSpeech.ts`、`filemate/web/tests/interview-coach-speech.test.mjs`；修改 `views/Interview.vue`、`components/InterviewReviewPanel.vue`、`styles/interview-practice.css`、`design-system/filemate/MASTER.md`。

**Interfaces:** `InterviewCoachPanel` props `coach: CoachView`、`draft: string`、`busy: boolean`，emits `update:draft`、`submit`、`retry-analysis`、`advance`、`select-attempt`、`reanswer`、`consent-change`；不自行发API。`useInterviewCoachSpeech()`返回 `speaking`、`error`、默认false的 `voiceConsent: Ref<boolean>`、`read(text: string, voiceId: string): void`、`stop(): void`；撤销voiceConsent立刻stop，未授权read只报可操作错误。内部复用MicrosoftSpeechProvider、NATURAL_VOICES、synthesizeNaturalSpeech，不新增TTS供应商。

- [ ] **Step 1:** `speech_stops_and_releases_url_on_input_recording_route` 用可控provider断言stop只释放一次、迟到onEnd不复活播放；`tts_failure_preserves_feedback_without_browser_voice_fallback`／`unconsented_read_never_sends_text`固定断言：

  ```javascript
  assert.equal(feedbackAfterError, originalFeedback)
  assert.equal(browserSpeechCalls, 0)
  assert.equal(unconsentedTtsCalls, 0)
  ```

  运行 `node --test tests/interview-coach-speech.test.mjs` 先 FAIL。
- [ ] **Step 2:** 实现面试“准备→作答与反馈→汇总”引导、当前大问题与一个主要操作；反馈默认展示原句／具体问题／建议，四维和六项详情按需展开；末次失败清晰待分析。历史用分页列表，首末比较标来源差异，不用分数小卡阵列替代内容。左侧导航保持唯一，不另加顶栏业务页签。
- [ ] **Step 3:** 逐题文本／重答共用现有语音输入、摄像头与本地视觉；本地录像归属改为 `attempt_id` 或未提交 `draft_media_id`，提交后明确绑定，仅保存在当前页Blob；不自动把前次视频挂给新回答。切题停止识别/音频并处理未提交输入确认，取消操作保留文本；迟到录制回调核对epoch。默认不启摄像头、不录音。
- [ ] **Step 4:** 点击朗读另有Microsoft正文外发授权（独立于LLM），默认晓晓、可选现有云夏等自然声。反馈超5000字符时只朗读可见反馈段并明确范围，不截断问题／原文；复用provider.stop及资源清理。轻量SVG状态动效尊重prefers-reduced-motion，沿用现有头像，不做两图切换说话或虚构情绪。
- [ ] **Step 5:** Node专项、`npm test`、`npm run build`、`npm run check:bundle` PASS；在390/768/1280/1440px用长中文、英文换行、12000字回答、键盘、读屏标签、减少动态、空／加载／失败场景实看并截图。任何超界、过小正文、重复入口修正后重验受影响场景。提交 `feat(ui): 呈现大字逐题面试与按需自然语音`。

### Task 8: 隐私生命周期、备份与关闭恢复

**Files:** 修改 `filemate/interview_review/repository.py:132–191`、`filemate/operations/personal_backup.py:269–381`、`filemate/operations/backup.py`（仅必要校验）、`workspace_privacy.py`（仅必要校验）；新增 `filemate/tests/test_interview_coach_privacy.py`；更新API与交付文档。

**Interfaces:** `normalize_restored_coach(conn: sqlite3.Connection) -> None` 放新repository中，在恢复最终commit前调用；对旧备份执行Task1 backfill、对恢复run标interrupted／保留终态、清所有本场外发授权并增加consent_revision，不发外部请求。删除预览增加 `answer_attempts/analysis_runs/coach_actions` 计数，指纹包含当前revision与版本；确认沿用现有token。

- [ ] **Step 1:** `test_delete_preview_changes_after_reanswer_and_repeat_delete_is_safe`断言旧token409、新预览完整计数、重复删除幂等、全部新表与媒体摘要清理且其他空间不变。`test_export_restore_preserves_history_but_never_replays_analysis`断言首末原文／时间完整：

  ```python
  assert restored_state.external_consent is False
  assert restored_run.status == 'interrupted'
  assert provider.calls == 0
  ```

  `test_restore_schema26_backfills_and_corruption_rolls_back`断言旧备份补第1版、坏外键恢复失败且原库／文件保留。
- [ ] **Step 2:** 运行 `uv run pytest filemate/tests/test_interview_coach_privacy.py -q`，确认新生命周期行为 FAIL。
- [ ] **Step 3:** 扩展清空分析覆盖每个版本的内容／视觉派生结果和run（保留原回答及语音节奏），清当前投影与报告引用、取消在途写资格；重试过往运行不能复活已清数据。已有clear成功结果不当有效分。整场删除级联新表、已有memory／report按旧合同处理。导出包含新表和provenance、不含BYOK／TTS音频／录像。
- [ ] **Step 4:** 个人恢复若当前有running/cancelling拒绝并解释需结束任务；归档中run从不恢复执行。管理员 `restore_backup` 完成原文件hash／库facts和当前删除账本核验后、返回结果前，对新目标中的业务库逐个调用 `normalize_restored_coach`，治理库不改；无新表的旧库此函数不操作，首启由Task1回填。每库事务并复查外键，报告单列安全规范化计数；失败保留未启用的新目录、activated仍false，原备份不变。不能在原hash核验前修改恢复库，不能靠一般GET自动重放。动态表枚举已覆盖部分保持不重复改写；签名、容量、外键校验沿用。专项与 `uv run pytest filemate/tests/test_p1_personal_backup.py filemate/tests/test_p1_account_privacy.py filemate/tests/test_backup.py -q` PASS。
- [ ] **Step 5:** 当前候选关闭COACH、关闭REVIEW分别回归文字训练／只读／隐私动作；在临时副本验证“升级→新写→关闭→指定旧候选18b6d77c启动与旧读取→再升级”。旧候选不能安全写新版本则列为只读维护，不宣称任意旧版兼容；如旧候选拒绝新schema，演练恢复升级前备份＋保存期间增量导出，不执行down migration。实录结果写兼容矩阵后提交 `fix(privacy): 覆盖面试版本导出删除与安全恢复`。

### Task 9: 完整流程、故障恢复与候选交付

**Files:** 新增 `scripts/acceptance/interview_coach.mjs`、`docs/INTERVIEW_COACH_DELIVERY_2026-10-16.md`；更新 README、API、MASTER、优化合同的本轮子卡状态；运行证据只在 `_working/interview-coach-<实际日期>/`。

**Interfaces:** 浏览器脚本复用 `scripts/acceptance/interview_review.mjs` 的Playwright初始化、check记录与输出方式；`FILEMATE_WEB_URL`／`FILEMATE_API_URL`必须显式指向隔离本地候选，`FILEMATE_EVIDENCE_DIR`指定临时证据目录，未指定或指向非回环地址则拒绝。只用合成账号／临时资料，断网／延迟／模型输出由本地夹具控制。单独的真实提供商检查使用现有安全配置，不把密钥写命令、页面截图或报告。

- [ ] **Step 1:** 写浏览器断言：`first_saved_before_analysis`、`reanswer_latest_failure`、`history_comparison`、`next_is_explicit`、`refresh_no_auto_ai`、`route_cancel_preserves_input`、`stale_media_does_not_attach`、`flags_and_long_mobile_content`。例如：

  ```javascript
  assert.equal(savedAttempt.answer, submittedText)
  assert.equal(snapshot.current_attempt.score, null)
  assert.equal(aiCallsAfterRefresh, aiCallsBeforeRefresh)
  ```

  每项断言当前可见正文、实际持久记录／运行次数及本次候选，页面截图不能代替数据库断言。按现役acceptance脚本的运行环境执行 `node scripts/acceptance/interview_coach.mjs`，要求退出0，八组均通过、未发生未处理异常；若本机无已配置的Playwright运行环境，先记录依赖，不静默安装或改生产环境。
- [ ] **Step 2:** 逐场运行首答→成功反馈→重答→失败待分析→同版主动重试→历史首末→下一题→整场报告→刷新回看→成长有效证据→导出→清空／删除→备份恢复。注入LLM超时／错误JSON／429／治理503／数据库写失败／断网／TTS失败／摄像头拒绝；失败只影响对应步骤，保存文字和其他页面仍可用。
- [ ] **Step 3:** 执行 `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`，要求退出0，包含全部新测试和前端类型／构建／体积；失败定位后仅重复受影响检查及最终同候选门禁。未经执行不填通过数，跳过项单列。实施前的24份脏文件须再次比对，不能把它们的内容当本轮新增成果。
- [ ] **Step 4:** 有现有有效配置时单独验真实模型的原句JSON反馈、一次失败与人工重试，以及Microsoft晓晓／云夏播放和停止；无配置则交付明确“未验收”依赖，不使用合成结果声称外部服务接通。记录模型／prompt／rubric版本、样本范围、调用数，不宣称学习有效或专家校准完成。
- [ ] **Step 5:** 完成当前候选的独立整分支审阅（按用户选择的实施流程），修复确凿问题后核验。把开关设置方法、schema变更、旧版本数据与代码回退矩阵、备份位置和恢复结果写交付报告；只有本批关键路径通过才将面试子卡记“本地验收通过”。编程、岗位及原始缺项保持未完成，不自动发布。
- [ ] **Step 6:** 提交 `test(interview): 验收面试教练完整训练与故障恢复`；提供精确提交、命令结果、截图、已知依赖。后续另写编程实施计划，完成后再写岗位／学习资源计划。

## 计划自审与交接

覆盖映射：设计§4→Task6/7/9；§5.1→Task2/3/4/7；§5.2→Task1/5；§5.3→Task2/3/4；§5.4→Task7；§8的面试部分→Task1/4/8；§9批次A→Task9；§10→Task4/8/9。设计§6/7不在本计划内，后续独立执行。Review Focus五项均已分配明确测试。

自审确认：types／方法名称一致；旧分析不会绕过新claim；当前得分来源与历史分离；恢复不重放且授权不复活；新写入与版本投影同事务；无预占迁移号、无新增依赖；未将计划中的测试写成已运行。执行者先对照当前源码更新移动的行号，不能用本计划替代阅读。

推荐 **Native（当前会话逐项实施）**：九项任务共享版本／分析／报告合同，连续上下文便于保持接口一致，也控制消耗；完成后独立整分支审阅。若更重视逐任务独立审阅，可选 Subagent-driven，成本较高。当前仅完成计划文档，待用户审阅并选择执行方式后实施。
