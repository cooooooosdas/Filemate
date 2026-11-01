# Learning Orchestrator 2.0 · C级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把目标、今日安排与现有任务执行整合为“今日行动”，让用户看清做什么、为什么、从哪里开始，并在真实完成后正确恢复进度。

**Architecture:** 复用 `/today` 路由、B级决策服务、原任务仓储和原执行页面，不建立第二套任务。增加按需加载的 Vue 工作台、可独立测试的展示／交互状态层；只补齐必要的只读目标目录、展示元数据和刷新回执定位。正式安排仍由B级预览、确认和撤销合同保存。

**Tech Stack:** 现有 Vue 3、TypeScript、Vue Router、Element Plus、Tabler SVG、Vite；FastAPI、Pydantic、SQLite。沿用 Node 内置测试及 pytest，不增加运行依赖、测试框架、模型调用或数据库迁移。

**Spec:** [已通过A级方案](../../LEARNING_ORCHESTRATOR_2_0_A_AUDIT.md)、[A级交付](../../LEARNING_ORCHESTRATOR_2_0_A_ACCEPTANCE.md)、[已验收B级交付](../../LEARNING_ORCHESTRATOR_2_0_B_DELIVERY.md)；原任务书 `C:/Users/胡希/.codex/attachments/7841a6a3-3b50-45cd-8996-97b11c136836/pasted-text-1.txt` 的 C1—C5、阶段验收与保护前三专项规则。

2026-11-01 用户确认“验收B级，进入C级计划”，随后批准本计划“从任务1逐项实施”。当前按八项任务连续开发，尚不表示C级整体完成或验收。沿用已选执行方式：当前会话由同一实施者逐项完成，结束后一次全范围独立审阅。第三版错题复盘成果继续维护，不被新入口替换。C完成后等待用户验收，不自动进入D／E或部署。

## Global Constraints

- 事实基线：独立工作树 `C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`，分支 `codex/wrongbook-2-audit`，计划取证时HEAD为 `c8b241b42e967e2476d6ece6d9a7de09044ac13c`。B源码为 `a7422ec`、报告为 `179d873`；后续安全修复和已有未提交测试不属于本卡，必须保留。
- “学习记录与学习能力不是同一概念”；阅读、任务勾选、模型面试分数不换算掌握率。只称任务完成和近期练习证据；无数据明确“待评测”或“证据不足”。
- “该层只能读取与当前目标有关的必要信息”；多目标保存，每次显式选择一个今日优先目标。共享资料须明确选课，最多20份来源；不自动汇总全资料库。
- “不允许后台静默覆盖学习安排”；预算、顺序、固定、排除和时长修改仅形成草稿，预览后确认才保存。新工作台没有泛化“标记全部完成”写入口；实际完成沿原领域功能。
- 用户目标名称、截止日期、完成记录、面试评分、知识关系与原计划不被调度修改。C中的“编辑”指候选安排的预算、顺序和选项；创建目标复用现有目标表单。
- `FILEMATE_ENABLE_LEARNING_ORCHESTRATOR` 默认0。只有能力响应明确 `enabled=false` 才进入旧版今日页；401／404／503／断网或合同不兼容均显示对应状态，不伪装成功或静默降级。
- B合同限额保留：候选200、选中20、来源20、每日100次新确认、有效未用预览100、令牌900秒、请求262144字节；预算0—1440分钟，每项估计1—240分钟。客户端约束不替代服务端验证。
- 上海自然日由服务端 `study_date` 确定；客户端时钟只用于提示刷新，不能授权跨日确认。
- 沿用 `design-system/filemate/MASTER.md` 的四主题与自动跟随系统、无衬线中文字体。正文17px、辅助16px、元数据至少15px、操作目标至少44px；不使用宋体、Emoji、突兀深黄、远程字体或新增机器人形象。
- 已选方案A“今日行动”作为主入口；方案B只保留为目标详情的参考。已完成两案选择，不重新询问风格。先展示A的当前主题可视预览，再接正式交互。
- 新工作台及控制器全部懒加载。B快照的初始gzip为143190／143360字节，仅余170字节；不得调高原体积门槛。API公开入口仍统一在 `services/api.ts`，实现可拆到按需模块。
- SQLite以实际 Linux Python3.11.13／SQLite3.26.0、JSON1及999变量上限为已知目标运行时；不得使用新SQL语法或修改既有迁移。生产仍需原有34→36升级，本卡不称生产零迁移。
- 合成回归、设计示例与真人研究分开记录。仅提交自有源码和脱敏证据；不提交数据库、密钥、真实用户资料或其他人的改动。

## Review Focus

1. 确认已提交但响应丢失／刷新：保留原请求键查回执，404仍可能是未决；不新建键重复写入。见任务4及8。
2. 快速切换目标、账号过期、恢复备份或跨上海零点：迟到结果不能回填旧范围，旧令牌和撤销预览立即失效。见任务3、4及7。
3. 精确目标不在最近20条、错题别名、计划的天数与0基索引不同、学期任务在后续分页：定位原任务，不默选第一项。见任务1、2及5。
4. 大量／截断证据、历史完成无逐项时间、概念未关联练习：披露查询边界，不生成“今日完成数”或“已掌握”推断。见任务2、6及8。
5. 手机键盘、200%缩放、超长标题、深色主题和键盘固定排序：主操作可见且可用，拖拽不是唯一排序方法。见任务6及7。

## 文件与职责

所有下列代码路径均相对本工作树；标记“新增”的文件在实施时创建。

| 边界 | 文件 | 职责 |
|---|---|---|
| 展示读合同 | `filemate/study/orchestrator/{models,api,snapshot,repository,commands}.py`；新增 `context.py` | 有界目标选项、快照标签、最新回执定位；保护既有调度写合同 |
| 公共客户端 | `filemate/web/src/{services/api.ts,types/orchestrator.ts}`；新增 `services/orchestrator-api.ts` | 保留八个公共函数，增加目录读合同与懒加载入口 |
| 纯展示与导航 | 新增 `filemate/web/src/today/{presentation,navigation,preferences}.ts`、`types/today.ts` | 守卫未知JSON、证据标签、精确导航、分空间显示偏好 |
| 生命周期 | 新增 `filemate/web/src/today/{workspace-state,command-state}.ts` | 范围代次、草稿／已存分离、确认／撤销与未知结果恢复 |
| 页面 | `views/Today.vue`；新增 `views/LegacyToday.vue`、`components/today/{TodayWorkspace,TodayScope,TodayTasks,TodayPreview,TodayFeedback}.vue`、`today/today.css` | 路由外壳、保留旧页、A方案三信息区及按需证据 |
| 原入口 | `views/{Home,GoalPlanner,StudyPlan,Wrongbook,Semester,Programming}.vue`、`navigation/{catalog,route-state}.ts` | 一个主导航；参数定位、明确失效提示、实际任务完成 |
| 测试证据 | 新增 `filemate/tests/orchestrator/test_context.py`；现有同目录 `test_{snapshot,commands,api,runtime,capacity,journey}.py` | 只读、兼容、回执和跨模块保护 |
| 前端测试 | 新增 `filemate/web/tests/today-{presentation,navigation,workspace,commands}.test.mjs`；既有 `orchestrator-api.test.mjs`、`navigation.test.mjs`、`route-state.test.mjs` | 实际函数行为，沿用 Node 内置测试；Vue交互由真实浏览器验证 |
| 文档 | `filemate/docs/API_SPEC.md`、`README.md`、`docs/{CURRENT_DELIVERY_INDEX,AGENT_DEVELOPMENT_EXECUTION_PLAN}.md`；新增 `docs/LEARNING_ORCHESTRATOR_2_0_C_DELIVERY.md`、`docs/audits/learning-orchestrator-c-2026-11-01/` | 合同、当前状态、前后截图、真实运行日志及限制 |

## 共享接口决策

既有八函数签名以 `types/orchestrator.ts`、`services/api.ts` 为准：`getOrchestratorCapabilities()`、`readOrchestratorSnapshot(scope)`、`previewOrchestratorSchedule(request)`、`confirmOrchestratorSchedule(request)`、`getOrchestratorToday()`、`findOrchestratorOperation(requestKey)`、`previewOrchestratorUndo(operationId)`、`confirmOrchestratorUndo(operationId, request)`。不改变参数语义、错误码、超时或幂等键规则。

本计划新增的相邻任务接口统一定义如下，后续步骤不得另起同义名称：

- Python：`GoalOptionsRequest(StrictRequest)` 只有 `q: str=''`（最多120字符）、`offset: int=0`（0—1000000）；`read_goal_options(storage, request) -> GoalOptionsPage`，每页固定30。新增 `POST /api/learning/orchestrator/goal-options` 是只读查询，沿用严格JSON、空间认证、开关与no-store，避免放宽现有路由对query的拒绝规则。
- `GoalChoice={goal_id,title,goal_type:string|null,deadline:string|null,source_id:string|null,valid:boolean}`；`GoalOptionsPage={items:GoalChoice[],total:number,offset:number,limit:30}`。`valid=false` 的损坏目标只能查看修复提示，不能确认安排。
- 快照 `facts.goal` 补入保存的目标 `title`（显示上限160字符）；`facts.sources` 补入 `original_name`（显示上限240字符）。目录标题同为160字符上限；超长内容可进入原目标／资料详情读取，不更改原值。显示元数据纳入证据版本，不加入旧目标的全局画像／gaps／模型评分。
- `DayView.latest_operation?: OperationReceipt|null`，`OrchestratorCapabilities.ui_contract?: 'today-workspace-v1'`。新确认／撤销只在日安排Artifact增加 `last_operation_id`，与回执同一事务保存；旧Artifact缺字段仍可读，返回null，不扫描全部历史猜测操作。指针缺失／不匹配只禁用该撤销入口，既有按键查回执仍可用。
- TypeScript：`OrchestratorClient` 包含上述八方法及 `getOrchestratorGoalOptions(request:GoalOptionsRequest):Promise<GoalOptionsPage>`；`loadOrchestratorClient():Promise<OrchestratorClient>` 为公共按需入口。
- `TodayMode='daily'|'exam'|'project'`；`TodayPreferences={mode:TodayMode,last_goal_id:string|null}`。模式是同一任务服务的场景视图，不发送为B请求未知字段，不另建任务表。
- `TodayPresentation={goal_title:string,scope_label:string,next_task:TaskView|null,today_attempts:number|null,historical_completed:number,coverage_notices:string[]}`；`presentToday(bundle:OrchestratorSnapshot, day:DayView|null):TodayPresentation`。未知或截断的“今日”计数为null，不把已返回条目数当完整总量。
- `TodayTarget={path:string,query:Record<string,string>,label:string}`；`TaskNavigation={primary:TodayTarget|null,related:TodayTarget[],notice:string}`；`resolveTodayTask(task:TaskView,bundle:OrchestratorSnapshot):TaskNavigation`。`readStoredGoal(artifact:KnowledgeArtifact):ReverseGoalPlan|null` 仅还原已存DTO，不计算新评价。
- `TodayReadPort={client:OrchestratorClient,getCourseBrowserScope:typeof getCourseBrowserScope,listGraphCourses:typeof listGraphCourses,getGraphCourse:typeof getGraphCourse}`。`createTodayWorkspace(port:TodayReadPort, storage:TodayStorage, clock:()=>number, wrap?:(state:TodayState)=>TodayState)` 返回 `{state,initialize,selectScope,setOptions,refresh,resetIdentity,dispose}`：`initialize(capabilities?:OrchestratorCapabilities)/refresh():Promise<void>`，`selectScope(scope:ScopeRequest):Promise<void>`，`setOptions(options:ScheduleOptions):void`，后两清理函数返回void。`wrap` 默认恒等，Vue传入reactive，控制器始终修改包装后的同一state；外壳可传已读能力避免重复初始化。`TodayStorage={getItem(key:string):string|null,setItem(key:string,value:string):void,removeItem(key:string):void}`；浏览器注入，不让纯模块直接依赖window。
- `TodayState` 定义在 `types/today.ts`：`phase:'loading'|'legacy'|'ready'|'error'|'expired'`、`identity:string|null`、`snapshot:OrchestratorSnapshot|null`、`day:DayView|null`、`draft:PreviewRequest|null`、`preview:SchedulePreview|null`、`receipt:OperationReceipt|null`、`write_status:'idle'|'previewing'|'confirming'|'unknown'|'saved'|'undo_preview'|'undoing'`、`error:string`、`dirty:boolean`、`generation:number`。
- `createTodayCommands(client:OrchestratorClient,state:TodayState,storage:TodayStorage,refresh:()=>Promise<void>)` 返回 `{preview,confirm,recover,previewUndo,confirmUndo,invalidate,dispose}`。前三个和 `confirmUndo()` 返回 `Promise<void>`；`previewUndo(operationId:string):Promise<void>`；`invalidate()/dispose():void`。确认体只留内存；存储仅留按身份隔离的 `PendingLocator={kind:'confirm'|'undo',request_key:string,study_date:string,operation_id?:string}`，用于查回执／恢复同类操作；不能将待决撤销误作新确认。
- `createTodayPreferences(storage:TodayStorage,identity:string|null)` 返回 `{read():TodayPreferences,write(value:TodayPreferences):void,clearMemory():void}`；身份无效则仅内存使用。每身份仅保存一个有界偏好与一个待决键，旧值覆盖；退出／恢复时删除待决定位，不持久化令牌、回答、资料正文或完整快照。
- `createTodayStorage(local:TodayStorage,session:TodayStorage):TodayStorage` 按键前缀分流：`filemate-today-preferences-v1:` 用local，`filemate-today-pending-v1:` 用session；键均含有效身份。待决键按标签页隔离并能同标签刷新恢复；路由dispose只清内存令牌，不删除用于查回执的定位。全局显示模式／保存目录设置继续使用原实现。

---

### Task 1: 补齐有界展示读合同和刷新回执定位

**Files:** 修改后端 `models.py`、`api.py`、`snapshot.py`、`repository.py`、`commands.py`，新增 `context.py`、`test_context.py`；扩展 `test_snapshot.py`、`test_commands.py`、`test_api.py`、`API_SPEC.md`。

**Interfaces:** 消费 `ScopeRequest`、`OperationReceipt`、`OrchestratorRepository.today()` 和同空间Artifact；产出共享接口中的 `read_goal_options`、目标标签、`latest_operation` 与 `ui_contract`。

- [x] 1. 先写 `test_goal_options_are_paged_and_private`：65个原创目标分三页；第二页offset30、items30、total65；q中的 `%`、`_` 按普通字符；返回无tasks/gaps/原回答，外空间记录0条。损坏JSON仍有可识别的disabled条目，不能阻塞整页；非法offset和额外字段422。
- [x] 2. 写 `test_day_receipt_pointer_is_atomic_and_backward_readable`：确认后关闭重开仓储，`today.latest_operation.operation_id == receipt.operation_id`；撤销后为撤销回执；注入事务失败时日安排和回执均不部分保存；旧B日Artifact无指针仍可读；指针类型／日期／修订不匹配返回null，不引用其他记录。快照标签没有旧全局画像，重命名使旧证据版本失效。
- [x] 3. 运行 `uv run pytest filemate/tests/orchestrator/test_context.py filemate/tests/orchestrator/test_snapshot.py filemate/tests/orchestrator/test_commands.py filemate/tests/orchestrator/test_api.py -q`，先看到新增断言失败；实现上述接口。目录用参数化SQL、普通列搜索和固定30行分页，分页后再解码内容，不依赖新JSON语法；仅读取 `reverse_goal_plan`。新日指针为兼容元数据，不新增表或migration。
- [x] 4. 重跑同一命令，预期全通过；读操作前后业务表指纹相同，默认关闭仍拒绝新读入口，历史回执可读。同步API示例，说明老日安排没有定位指针时仍可凭原request_key查询。
- [x] 5. 仅暂存本任务文件，提交 `feat(orchestrator): 补齐工作台展示与回执定位合同`。

### Task 2: 建立懒加载客户端与可信展示、导航适配

**Files:** 修改 `services/api.ts`、`types/orchestrator.ts`、`tests/orchestrator-api.test.mjs`；新增 `services/orchestrator-api.ts`、`types/today.ts`、`today/{presentation,navigation}.ts`、`tests/today-{presentation,navigation}.test.mjs`。

**Interfaces:** 消费任务1读合同与现有 `getKnowledgeArtifact` DTO；产出 `OrchestratorClient`、`loadOrchestratorClient`、`presentToday`、`resolveTodayTask`、`readStoredGoal`。保留八个已有公共函数，改为按需委托；新模块复用现有已配置HTTP实例，不创建第二套认证或密钥拦截器。

- [x] 1. 先写实际客户端行为测试：九方法发送完整原body／编码ID，读15秒、写30秒；拒绝缺data／success=false；公开委托仍返回同一回执。测试懒加载实现本身，不能只搜索源码字符串。
- [x] 2. 写 `history_and_truncation_are_not_today_statistics`：2026-11-01上海日只计范围内、有效判定且时间可验证的作答；历史计划勾选不计入今日；attempts截断使 `today_attempts === null` 且有边界提示；没有练习关联不能判断“不掌握”。未知JSON、null、重复来源、超长标题不抛异常；标题以文本显示。
- [x] 3. 写 `targets_use_real_origin_identity`：review指向原wrong_id；plan使用原plan_id及真实day；goal使用goal与task_id；semester保留原task_id。显式course＋concept关联才提供 `graph_scope=course&course=…&node=…`；资料使用实际source；无具体编程题／面试会话ID显示选择提示，禁止填入首题或伪造ID。`javascript:`、外站URL及未允许路径不能成为主操作。
- [x] 4. 运行 `node --test tests/orchestrator-api.test.mjs tests/today-presentation.test.mjs tests/today-navigation.test.mjs`（目录 `filemate/web`），看到新增失败后实现。纯适配只处理当前返回的200候选和有界事实；旧Goal Artifact只能还原保存字段，类型不合法返回null，不重新生成gaps。
- [x] 5. 同命令全通过并运行 `npm run build`、`node scripts/check-bundle.mjs --dist dist`。若初始体积超限，拆分新实现和只在工作台使用的代码；不提高阈值。提交 `feat(today): 增加可信展示与任务导航适配`。

### Task 3: 实现范围、草稿和页面生命周期

**Files:** 新增 `today/{workspace-state,preferences}.ts`、`tests/today-workspace.test.mjs`；扩展 `types/today.ts`。

**Interfaces:** 消费任务2的客户端、展示类型及既有 `getCourseBrowserScope/listGraphCourses/getGraphCourse`；产出 `createTodayWorkspace`、`createTodayPreferences`、`createTodayStorage`。Vue通过wrap注入响应式包装，控制器写入同一代理；测试默认恒等包装，不依赖DOM。

- [x] 1. 先写 `late_goal_identity_and_restore_results_are_discarded`：延迟A读取后切到B，A不能回填；session-expired／data-restored调用 `resetIdentity()` 立即清快照、草稿和令牌；重新获得身份后才能请求。身份读取失败不能沿用上个账号的缓存；dispose后无写状态和遗留监听。
- [x] 2. 写 `scope_and_draft_never_save_silently`：无今日优先目标显示选择，不自动选最近目标；共享资料要求选课；来源明确选择且最多20；改预算或顺序只更新draft、清preview，不请求confirm。budget=0可预览空安排，NaN／小数／超过1440拒绝；已完成项只读，dirty时刷新只提示证据变化，不覆盖草稿。
- [x] 3. 写 `preferences_and_day_rollover_are_scoped`：本地存储拒绝／损坏JSON退回内存，A账号偏好不出现在B；模式只保存daily/exam/project；两个标签页的待决键不互相覆盖，同标签页刷新可读原键。服务端新study_date或倒计时提示跨日时丢弃旧预览，重新读取，不用本机日期提交旧日确认。
- [x] 4. 运行 `node --test tests/today-workspace.test.mjs`（`filemate/web`），新增失败后实现代次控制和一次初始化。目录分页按需读取，不拉全目标正文；课程元数据只用于明确范围，不能默认选整门课程所有资料。请求失败保留有效已存day和用户输入，并区分未确认、已确认、证据已变化。
- [x] 5. 重跑全通过；验证重复初始化／卸载不重复请求，不使用定时轮询全库。提交 `feat(today): 实现目标范围与可恢复草稿状态`。

### Task 4: 接通预览、确认、未知结果恢复和撤销

**Files:** 新增 `today/command-state.ts`、`tests/today-commands.test.mjs`；扩展 `workspace-state.ts`、`types/today.ts`。

**Interfaces:** 消费 `TodayState`、任务3的refresh及B级写合同；产出 `createTodayCommands`。预览body、确认body和undo token分别管理，不能互用。

- [x] 1. 先写 `lost_confirm_uses_one_key_and_never_means_failure`：重复点击只发一次confirm；超时进入unknown；recover沿原键查询，404仍unknown；收到回执后再读day。回执已成功而day读取503显示“已保存，刷新暂不可用”，不能再确认或假撤销。另写 `missing_request_can_resume_with_fresh_preview_and_same_key`：刷新后旧请求从未到达时，用户可重读并明确重新预览／确认，沿用未决键；旧请求若先提交，新体得到冲突后查出原回执；新体若先提交，旧体不能另写一次。不得永久卡在404，也不得自动换键反复提交。
- [x] 2. 写 `confirm_and_undo_bind_the_reviewed_revision`：改预算／目标／顺序后旧preview不可确认；900秒过期或409需重预览；撤销先独立预览且显示影响，使用自己的稳定键。重新打开页面用day.latest_operation恢复撤销入口，完成过的领域任务不被撤销重置；无旧指针说明限制，不猜operation_id。
- [x] 3. 写 `pending_locator_survives_refresh_without_secrets`：同身份同日期刷新后只按保存键查回执；存储中没有token、scope正文、回答或快照；待决撤销只允许按原operation_id重做撤销预览并沿用原键，不变成确认安排。恢复备份／账号过期／dispose清除确认与撤销授权。旧日回执只能作为同身份历史显示，不能覆盖新的日期／范围／修订；确认或撤销在途时禁止再发另一写操作。
- [x] 4. 运行 `node --test tests/today-commands.test.mjs tests/today-workspace.test.mjs`（`filemate/web`），新增失败后实现。429不自动循环重试；503保留输入；401清身份；未知错误有明确重读／查回执操作。刷新和路由离开须提示未提交草稿或在途请求可能完成。
- [x] 5. 重跑全通过，确认UI发出的confirm完全沿用预览scope/options/evidence_revision。提交 `feat(today): 接入确认撤销与断线回执恢复`。

### Task 5: 让原功能精确接住任务

**Files:** 修改 `views/{GoalPlanner,StudyPlan,Wrongbook,Semester,Programming}.vue`、`navigation/route-state.ts`；扩展 `today/navigation.ts`、`tests/today-navigation.test.mjs`、`tests/route-state.test.mjs`。

**Interfaces:** 消费 `TaskNavigation` 与既有 `getKnowledgeArtifact/getStudyPlan/updateStudyPlanDay`、semester任务和Wrongbook路由；产出精确定位的原页面，不新增任务完成API。

- [x] 1. 先写 `exact_goal_outside_recent_list_remains_selected`：目标不在最近20条时按明确goal读取已存Artifact并校验类型，不选择首目标；task_id不存在显示失效提示。Wrongbook V2把旧wrong_id别名规范为focus；旧版保留其原参数，重复／非法参数不触发错误记录提交。
- [x] 2. 写 `plan_day_and_semester_focus_do_not_choose_the_first_item`：`?plan=p&day=7`在day字段不等于数组index+1的样本中仍定位真实day；完成写回对应0基index。缺失／已归档计划不回退最新计划。学期第75项任务能定位其实际页，不更改筛选后误指另一项；不存在则提示。
- [x] 3. 写 `programming_missing_reference_is_explicit`：明确problem不存在时不默选首题；没有题目关联时给出选择练习的清晰入口。目标面试保留现有source/focus/goal/scenario/target上下文；只有确有对应训练记录才能称“继续本场”。原功能开关关闭时呈现不可用原因及合理替代入口。
- [x] 4. 运行 `node --test tests/today-navigation.test.mjs tests/route-state.test.mjs`（`filemate/web`），新增失败后实现纯参数解析并在Vue挂接定位／滚动。返回固定 `/today`，不接受任意外部return URL；不把额外参数塞进会拒绝未知字段的图谱query。
- [x] 5. 同命令与 `npm run build` 通过；浏览器验证留到任务7，不以纯函数测试代替点击证据。提交 `fix(today): 精确定位原任务与失效入口`。

### Task 6: 实现A方案工作台与统一入口

**Files:** `views/Today.vue`；新增 `views/LegacyToday.vue`、五个 `components/today/*.vue`、`today/today.css`；修改 `views/{Home,GoalPlanner,StudyPlan}.vue`、`navigation/catalog.ts`、`tests/navigation.test.mjs`。

**Interfaces:** 消费任务2—5的状态、命令和导航；产出用户可用的三信息区工作台。Today路由外壳只检查能力并按需加载工作台／原页；新页面的复杂模块不进入Home／App初始包。

- [x] 1. 把已选A草图 `docs/design/learning-orchestrator-a/today-action.{svg,png}` 与当前四主题变量对齐，先提供当前选中方案的浏览器静态预览，明确示例数据只用于排版；保存桌面／窄屏预览到 `_working/learning-orchestrator-c/`。不重新发起两案风格选择，不把静态预览写成已实现功能。
- [x] 2. 先补导航行为回归：侧栏仅一个“今日行动”入口；原“今日学习”为搜索别名，目标／学习计划／学期保持同组详情入口，无重复业务顶栏；关闭后仍可访问旧页。能力未知显示加载／重试；enabled=true而缺ui_contract显示版本不匹配，不假装关闭。运行 `node --test tests/navigation.test.mjs tests/today-workspace.test.mjs`，新增断言先失败。
- [x] 3. 原Today完整保留为LegacyToday，保留未提交作答离开守卫；实现新外壳及TodayScope：目标名称、截止日期、明确范围、真实任务状态／证据和下一步。创建目标进入原表单；新工作台的“调整”进入本页候选预览，不调用会覆盖旧目标任务的 `replanReverseGoal`。开启新能力时GoalPlanner的原重排按钮改为这一入口；不宣称旧后端重排接口已安全重构。
- [x] 4. 实现TodayTasks／TodayPreview：动作、预计时长、估计来源、推荐理由、证据折叠、键盘上移下移、固定／排除、变更摘要、延期理由、确认／撤销回执。预计分钟数不称实际学习时长；已完成任务不提供统一伪完成按钮。桌面8:4分栏，平板先目标／时间，小屏当前行动优先；保留原页面完成能力。
- [x] 5. 实现TodayFeedback及三模式：日常、用户主动开启且有考试目标日期的冲刺、项目／能力训练；共享相同证据与预算管线，不自动换目标。反馈将“有时间的今日练习”与“当前目标已完成任务（含历史）”分开；延期和需要巩固直接引用真实记录。概念缺口仅按需调用 `getCourseLearning(course_id,concept_id)`，一次最多5个明确关联概念并显示查询范围／as_of；无关联标为未能核对，不把全课都判成无证据。
- [x] 6. 同命令、全部 `npm test`、`npm run build`、`node scripts/check-bundle.mjs --dist dist` 通过；三场景无模型调用、无重复任务创建，目标创建后可返回选择。提交 `feat(today): 完成今日行动工作台`（仅本地候选，不推送部署）。

### Task 7: 真实浏览器交互、响应式与故障验收

**Files:** 按实际发现修改任务2—6的自有文件；新增 `docs/audits/learning-orchestrator-c-2026-11-01/{browser.json,browser.md}`、脱敏前后截图。临时账户和数据库仅在 `_working/learning-orchestrator-c/`。

**Interfaces:** 消费真实FastAPI／Vite代理和原功能；产出浏览器操作与错误证据。本任务不用新 `@playwright/test` 框架，先读可用浏览器技能并检查本机工具；使用已有浏览器控制能力，CLI路径若采用Playwright则先验证npx可用，不擅自联网安装。

- [ ] 1. 用同一原创合成账户记录旧版截图，再开启新能力，完成：创建两目标→明确选一目标与课程→预览→改120为45分钟→固定／排序／排除／改估计→再次预览→确认→查看依据→进入具体错题真实作答→返回→刷新看到原领域结果→预览撤销→确认撤销。保存每步真实响应／回执ID，证明另一目标、已完成记录和原计划未被改写。
- [ ] 2. 分别点击真实plan日、goal任务、semester后续页任务、已关联graph概念／资料；有实际关联的面试／编程场景精确进入，无关联场景明确提示后选择，不声称恢复记录。创建、编辑、导航、完成和刷新均以真实点击证明，不能用静态HTML或纯API成功替代。
- [ ] 3. 用浏览器故障拦截验证：确认已到服务端但响应丢失、查回执暂404、确认成功后day503、401、429、旧令牌／双标签页修订冲突409、关闭能力、合同缺版本、资料删除、备份恢复、网络离线、快速切换范围。验证按原键恢复、原记录保留、无无限重试、无后台AI调用，记录不能执行的设备／浏览器依赖。
- [ ] 4. 实测1440×1000、1024×768、390×844及320px窄屏；桌面200%缩放、移动端输入键盘、四主题／跟随系统、reduced-motion、纯键盘排序和弹层焦点。160字目标、超长无空格文件名、200候选、0预算和空库均无关键操作遮挡、横向正文溢出或失效按钮；正文／普通控件对比度至少4.5:1，焦点可见。
- [ ] 5. 发现功能缺陷先添加其所属纯状态／后端回归再修；视觉间距问题直接修并重拍，不制造镜像实现的测试。保存前后同尺寸截图、pageerror／控制台错误、实际请求及失败状态，脱敏后提交 `test(today): 归档真实交互与多尺寸验收`。无实际运行的项目明确NOT RUN。

### Task 8: 兼容、容量、全量门禁与C级交付

**Files:** 扩展 `filemate/tests/orchestrator/test_{journey,runtime,capacity}.py`；新增 `docs/LEARNING_ORCHESTRATOR_2_0_C_DELIVERY.md`、`docs/audits/learning-orchestrator-c-2026-11-01/{verification.json,review.md}`；更新README、索引、执行状态及API文档。

**Interfaces:** 消费任务1—7所有实现与现有 `scripts/verify.ps1`；产出可复现证据和C验收请求，不产出D级模型功能或E级整体验收结论。

- [ ] 1. 增加并运行真实仓储／HTTP旅程：新确认→丢响应→同键查回执→重启→day回执入口→实际领域完成→撤销；恢复备份后旧令牌／待决缓存失效。指纹确认前三专项、原评分、关系、复习历史和计划完成没有被调度重置。旧B Artifact缺新字段、旧客户端忽略新字段、能力关闭后的旧页均可读。
- [ ] 2. 扩展现有容量样本100／1000／10000条本域错题及等量外域、高差异到期时间；沿用B测法，暖请求与四并发P95各≤500ms、最大响应≤512KiB，完整披露冷请求及运行环境，不用截断换假总量。检查Today只取200候选、20选中、30条目录页，未加载整张万节点图；最多5条概念证据按需请求。缺口计数覆盖不足时为未知。
- [ ] 3. 在真实旧运行时执行新增读合同、日回执定位和旧数据读取；不能只用新SQLite或CLI证明整个应用。C不新增migration，核对definitions；若修改使SQL或迁移兼容性改变，停在本卡解释风险，不能沿用B已通过结论。临时服务必须是本轮拥有的实例，认证优雅停止；不杀未知服务。
- [ ] 4. 执行 `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`，保存完整退出码、通过／跳过／排除及体积。独立记录C新增测试、旧版回归与生产未测项；B的1897／304属于旧快照，不冒充当前结果。仅在相关失败修复后按风险补跑，不重复无目的全量验证。
- [ ] 5. 按已选Native方法完成一次全范围独立审阅：范围从本计划后实施基线到C最终候选，只含自有改动；要求正确性、隐私、写入恢复与UI实际行为。保留原审阅结论和发现，实施者修复并回归，不伪称未经复审的新独立PASS。审阅器不可用则明确依赖，不能虚构结论。
- [ ] 6. 形成C交付：C1—C5逐项矩阵、前后截图、浏览器旅程、真实测试日志、体积／容量、兼容与恢复、操作说明及已知限制；说明真实学生学习效果仍未采集。仅提交自有文件，提交 `docs(orchestrator): 归档C级工作台与验收证据`，随后请求用户验收C；D／E和推送部署继续等待相应授权。

## 计划自审与验收映射

| 原要求 | 实施／证据 |
|---|---|
| C1 少步骤知道目标、原因、开始和下一步 | 任务2、5、6；任务7真实点击旅程 |
| C2 目标／安排／反馈三区及真实证据 | 任务1—4、6；历史与今日计数分别测试，缺口查询显式有界 |
| C3 三场景复用，不建三套系统 | 任务3偏好、任务6用户主动视图、任务7切换；确认仍使用同一B合同 |
| C4 两案后选择、原站规范、大屏／窄屏 | A级已交两案并选A；任务6实际预览、任务7四主题与多尺寸证据 |
| C5 精确入口／无法恢复明确替代 | 任务2导航守卫、任务5原页定位、任务7真实点击；禁止默选第一项 |
| C验收创建／编辑／导航／完成／刷新 | 任务7实际流程；编辑候选安排不覆盖目标，真实完成由原功能写入 |
| 保护第三版、可恢复、版本与容量 | 任务1原子指针、任务3—4隔离和恢复、任务8指纹／旧运行时／全量门禁 |

自审修订：将原本需要全量读取目标的选择器改为30条只读目录；为刷新撤销补入兼容日指针而不扫描所有回执；明确历史完成没有逐项时间时不计作今日；图谱概念缺口只核对最多5个真实关联节点并披露范围；客户端实现按需拆分以保护仅余170字节的初始gzip预算。以上均为计划决策，代码、浏览器旅程、性能与C级测试尚未执行。
