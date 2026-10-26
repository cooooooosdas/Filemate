# 错题复盘 2.0 C级交互工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将B级真实复习证据接入目录＋单题工作区、可恢复的有界专注批次，以及今日、课程练习和图谱练习入口。

**Architecture:** 延用Vue 3、现有API服务和schema35；追加有界只读投影，不创建第二套错题或作答表。用可注入API的纯TypeScript控制器管理请求键、身份代次与页面状态；浏览器仅保存当前空间的导航、批次引用与请求标识，不默认保存回答正文。B级事务负责所有成绩与排期，C级不重新实现规则。

**Tech Stack:** Vue 3 / TypeScript / Vue Router / Element Plus现有弹窗 / Tabler按需SVG；FastAPI / SQLite / pytest；Node原生测试；现有Playwright验收工具。

**Spec:** [A级已获准设计](../specs/2026-10-25-wrongbook-2-design.md)，重点第7、9、11、12、13节；[B级交付与边界](../../WRONGBOOK_2_0_B_DELIVERY.md)。原任务书SHA256：`809fee871c2664ba302c5ea42d6560a28d7b3dc2494d62697bb08ee077c64b20`。

## 授权与事实基线

2026-10-26用户在B级交付后回复“继续”，据任务书“明确同意继续”的要求进入C级计划准备，不要求固定口令。A级七项选择不重复询问。本计划尚待用户审阅；此文不是C级实现或验收结果。继续沿用本会话逐项实施、结束后一次独立审阅的方式。

- 实际目录：`C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`；分支`codex/wrongbook-2-audit`；B级基线`e1c97e1`。
- `Wrongbook.vue`仍循环完整卡片并调用旧提交／单因接口；`Today.vue`和`LearningArtifact.vue`也调用旧接口。`course-graph/learning-state.ts`已经有同键重试，但仍使用旧非空布尔结果，必须一并适配，防止2.0题返回409或将NULL当答错。
- B级新写开关默认关闭；只读历史及导出仍可用。C级接入必须先读服务端能力，不能靠前端开关判断写入权限，也不能遇到2.0故障后自动降回旧算法。
- 全量列表目前缺少2.0状态、13类多错因与历史只读筛选。现有`/wrongbook/page`合同保留，新页面使用独立v2只读接口。
- `getLearningSource()`可读取实际来源正文；没有位置证据的旧题只能打开资料全文。精确图谱反查与AI来源证据属于D级，C级不按同名知识点伪造关联。

## Global Constraints

- 只实施C级，不调用AI、不进入D/E、不推送或部署；不将本地工程测试称为真实学习效果。
- 默认10题、最多20题的专注批次；先独立回答，主动查看参考答案／解析后本次`answer_revealed=true`不能再恢复为false。
- 保留现有蓝色、四主题、原无衬线、统一左侧导航；不用Emoji、艺术字、黄色主块、远程字体或第二套组件库。
- 正文18px、问题24px起、辅助15—16px、主操作17—18px，点击目标≥44px；正文对比度≥4.5:1；尊重减少动画偏好。
- 分页默认30，不一次渲染全库；新只读分页最大100。所有过滤在分页前执行，排序最后以`wrong_id`确定；未知／重复参数422。
- 上海日期规则、1/3/7/15/30天、至少3次合格验证／3日／首末7天与旧历史口径沿用B级；不重新计算或迁移成绩。
- schema保持35，不改既有迁移。性能若确需索引，先记录执行计划及计时，再单独提出追加迁移，不能暗改已发布SQL。
- 未提交正文只在内存；切题／切页／刷新前提示，强制关闭无法保证保留。已提交证据在服务端；本机批次恢复不等于跨设备同步。
- 回答正文、参考答案、资料正文、邮箱和密钥不进入URL、本机批次记录或普通日志；身份未知时禁用持久偏好，回退页内状态。
- 浏览器答案隐藏仅为学习交互，不声称防抓包或防作弊。
- 保留24个原有测试修改，提交前逐文件SHA256核对`_working/wrongbook-a-20261025/preserved-tests.json`；仅暂存本卡路径。
- 初始递归静态依赖gzip预算143360字节不得提高；B级143305字节仅余55字节。错题组件、控制器与图标保持路由懒加载，不从App壳静态引入。

## Review Focus

1. 请求已保存但响应丢失：保留原键，刷新后查服务端回执；未确认不能显示成功或换键重复提交（任务2、4）。
2. 切换题目／身份／恢复备份后旧请求迟到：不串题、不把原空间正文写进新空间，撤销预览失效（任务2、3、5）。
3. 先看解析再进入专注／改答案：本次辅助标记不可清除；旧历史原答不提前出现在专注DOM或可访问文本中（任务2、4、6）。
4. 资料删除、题集修订、历史只读和无效日期：保留可读证据并解释限制，不静默换到第一题、不继续提交旧版本（任务1、3、4）。
5. 1万条记录、超长内容与窄屏键盘：真正全库筛选、有限DOM、列表返回位置及弹窗焦点均可用（任务1、3、6）。

## 文件职责与接口总表

| 文件 | 职责 |
|---|---|
| `filemate/wrongbook/queries.py`（新） | 参数化SQL只读分页、筛选选项、摘要DTO与请求回执读取 |
| `filemate/wrongbook/api.py`、`repository.py` | 新读路由／能力及摘要字段；沿用B级写接口 |
| `filemate/web/src/types/wrongbook.ts`、`services/api.ts` | 完整可空合同、有界读函数、能力与身份范围 |
| `filemate/web/src/wrongbook/presentation.ts`（新） | 原始题目安全归一化、状态及结果文案；不修改提交快照 |
| `filemate/web/src/wrongbook/submission.ts`（新） | 同次操作同键、单请求互斥、结果不确定与回执恢复 |
| `filemate/web/src/wrongbook/browse-state.ts`（新） | URL白名单、导航偏好、无正文的本机批次元数据 |
| `filemate/web/src/wrongbook/workspace-state.ts`（新） | 目录／详情／历史／排期控制器、草稿及代次隔离 |
| `filemate/web/src/wrongbook/focus-state.ts`（新） | 最多20题的批次、独立／辅助回答和恢复 |
| `filemate/web/src/views/Wrongbook.vue` | v1/v2路由内分流；旧版代码保留为独立Legacy组件 |
| `filemate/web/src/components/wrongbook/`（新） | LegacyWrongbook、ReviewWorkspace、ReviewList、ReviewQuestion、ReviewEvidence、ReviewSchedule、FocusReview；每个文件一个交互责任 |
| `Today.vue`、`LearningArtifact.vue`、`LearningWorkspace.vue`、`course-graph/learning-state.ts`、`types/courseLearning.ts`、`CourseLearning.vue` | 其余三个入口接共享提交、可空结果和离开保护 |
| `filemate/web/tests/wrongbook-*.test.mjs`（新） | 纯控制器用户结果测试，沿用Node直接导入TS模式 |
| `filemate/tests/wrongbook/test_workspace_reads.py`（新） | 新读合同、隔离、过滤、错误与无模型调用 |
| `scripts/acceptance/wrongbook_workspace_fixture.py`、`wrongbook_workspace.mjs`（新） | 只用隔离合成账号，真实API浏览器验收 |

已有代码中`ReviewDetail.question`必须继续保留原始JSON；展示转换不能替代`expected_question`。

## Task 1：有界目录与能力合同

**Files:** 新增`queries.py`、`test_workspace_reads.py`；修改`api.py`、`repository.py`、`types/wrongbook.ts`、`services/api.ts`、`filemate/docs/API_SPEC.md`。

**Interfaces:**
- `ReviewFilter`：`q`≤160；`source_id`、`course_id`≤128；`knowledge_q`≤120；`status=all|due|overdue|active|pending|criterion_met|legacy_completed|paused|history|invalid`；`cause`为B级13类或`unconfirmed`；`min_errors/max_errors=0..1000000`；`due_from/due_to/created_from/created_to`为可空带时区ISO；`sort=due|updated|errors|created`；`direction=asc|desc`；`reviewable_only=false`。上下限相反422，时间无效422，不接受客户端时钟。时间／次数区间两端包含；due／overdue与B摘要相同，active与新增active_review_count相同，history只读旧题，invalid按detail.data_error，其他状态按对应原字段。
- `ReviewQueries(storage, clock).page(filters, *, limit=30, offset=0) -> dict`返回`items/total/limit/offset/has_more/as_of`；item为`ReviewListItem`：身份三元组、`question_digest/stem/question_type/source_id/source_name/knowledge_label`、B级状态和计数、`created_at/updated_at/read_only_snapshot/data_error`。不返回原答／参考答案／解析。
- `GET /wrongbook/v2/page`；`GET /wrongbook/v2/filter-options?kind=sources|courses&q=&offset=0&limit=30`返回真实有记录的来源／有效显式题目映射课程，最多100，不能从截断前30题生成筛选选项。
- 课程只认当前有效、active、摘要相同的`kg_question_links`和当前课程快照；来源停用／历史题集不算当前课程题。复用现有映射语义，不按知识点同名归课；无映射的记录仍可从全部／资料范围找到。
- `reviewable_only=true`在分页前排除paused、legacy_completed、history、invalid；专注直接使用此筛选，不先取10题再在前端删减，避免后续有题却报空。课程映射集合过大时不拼接超出SQLite3.26参数数目的IN列表，规模测试覆盖此边界。
- `GET /wrongbook/v2/capabilities`返回`write_enabled/rule_version`；不调用模型、不返回身份路径。`getReviewBrowserScope()`复用`publicLLMStatus().credential_scope`现有64位散列，仅用于本机命名空间，失败返回null，不作为认证。
- `GET /wrongbook/v2/receipts/{request_key}`只读现有`review_events.result`，不存在404；作用域仍由服务端身份确定，不接受owner。key沿用B级16–80字符约束，响应no-store。
- 摘要追加`active_review_count`（新规则、active、needs_review/provisional/new）、`saved_review_attempt_count`（新规则purpose为review或early_practice的真实attempt，包含待核对但不称正确）；保持现有全量字段不变。

- [x] 写失败测试：65题跨页、字面`%_`检索、13类多因、全部10种状态、组合日期／次数排序；总数先过滤再limit，新增摘要为0时真实0；第一页全是只读题时reviewable_only仍能找到后续可作答题。
- [x] 写失败测试：课程有效／失效摘要／跨课程隔离、只读旧题、坏JSON或日期；重复／未知参数422、另一个账号404、开关关闭仍可读、所有GET模型调用次数0。
- [x] 执行`./.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_workspace_reads.py -q`，保存预期RED。
- [x] 实现上述DTO与路由；固定路径注册在`/{wrong_id}`前。SQL参数化，日期用B级`filemate_review_time`，来源／课程同名不自动关联；detail补`question_digest`但保留raw question。
- [x] 同命令转GREEN并运行整个`filemate/tests/wrongbook`；同步公共规范，只写实际实现合同。
- [x] 仅暂存本任务路径，提交`feat(wrongbook): 增加工作台只读分页与能力合同`。

## Task 2：共享提交与导航状态

**Files:** 新增`presentation.ts`、`submission.ts`、`browse-state.ts`及`wrongbook-submission.test.mjs`、`wrongbook-browse.test.mjs`；扩展共享类型。

**Interfaces:**
- `presentReviewQuestion(raw: Record<string, unknown>) -> ReviewQuestionView`：`stem/type/options/reference/explanation`，兼容`stem/question`、`analysis/explanation`和数组／键值选项，返回独立展示对象，原始快照不变。不执行HTML或加载远程公式脚本。
- `createReviewSubmission(api, { makeKey, scope, storage, observe? })`：`open(ref, rawQuestion)`、`setAnswer(text)`、`revealAnswer()`、`submit(action='answer')`、`recover()`、`dirty()`、`resetIdentity(scope)`、`dispose()`；`state`含`answer/busy/receipt/error/uncertain/answerRevealed`。B级`ReviewAnswerResult.is_correct=null`始终显示待核对，不做false转换。
- 同题版本＋完整提交body指纹对应同键；点击与Enter并发只发1次，网络／408／5xx保留键；在不确定状态禁止修改body后另建键提交，可查回执或重发原请求。409保留原稿、废弃当前提交资格，先重新读取题目；不得自动替换expected_question。
- `readReviewBrowse(query)`与`reviewBrowseQuery(state)`仅允许`focus/q/status/source_id/course_id/knowledge_q/cause/min_errors/max_errors/due_from/due_to/created_from/created_to/sort/direction/offset/mode`，无正文。focus只显示指定题；404不退到第一条。
- `createReviewPreferences(storage, scope)`仅保存筛选、选中ID、有限滚动位置和最多20个批次引用／attempt ID／请求key及摘要，不保存正文。失效／超界数据丢弃并提示；拒绝本机存储时页内可用。
- 本机待确认请求仅保存key、输入摘要和题目引用；恢复先GET回执。有回执以服务端为准；404仅表示当前未查到，不能声称失败或自动换键。原稿仍在内存时可原样重试；强刷后需重新输入同一内容匹配摘要，或先跳过此题，原未知请求保持待核验。

- [x] 写Node失败测试：双击＋Enter、提交成功后响应丢失、同key重试、409原稿保留、主观NULL、看答案后再清空输入仍为assisted；不确定状态不能变更body重交。
- [x] 写Node失败测试：切题／账号后迟到回执不可应用，旧批次不能在新scope恢复，坏存储／非法URL／重复focus不串题，本机记录没有回答或题目正文。
- [x] 执行`node --test tests/wrongbook-submission.test.mjs tests/wrongbook-browse.test.mjs`（目录`filemate/web`）保存RED，实施上述控制器后同命令GREEN。
- [x] 提交`feat(wrongbook): 统一幂等提交与安全浏览状态`。

## Task 3：浏览复盘工作区与真实证据

**Files:** 新增`workspace-state.ts`、除FocusReview外的组件及`wrongbook-workspace.test.mjs`；修改`Wrongbook.vue`、`.env.example`、README和设计系统页面说明。

**Interfaces:**
- `createReviewWorkspaceController(api, observe?)`：`initialize()`、`loadPage(filters, offset=0)`、`select(id)`、`history(kind, offset=0)`、`loadSource()`、`saveDiagnosis(body)`、`previewSchedule(body)`、`confirmSchedule()`、`resetIdentity(scope)`、`dirty()`、`dispose()`；调用任务1读合同、B级写合同和任务2提交控制器。异步读／写均绑定当前scope、wrong_id与代次。
- 路由`VITE_ENABLE_WRONGBOOK_V2=true`时懒加载新工作区，否则LegacyWrongbook；编译默认关闭。新页面能力关闭显示只读理由、不回落旧写；Legacy页面遇2.0拥有记录只读并给明确入口说明，不能显示可提交而必失败的按钮。
- 桌面内容宽≥900px用目录约28%／主区约72%；更窄用列表→详情，返回保留查询、页码、选中与滚动。标题、概览和唯一“开始本次复习”动作保持主次；额外筛选按需展开，清除有真实作用。
- 主区问题24–28px／正文18px；radio选择、填空输入、主观多行、代码等宽区；不引入新判题类型。原答／参考答案／解析／错因／来源／历史按需展开；历史两次结果与新规则分别解释，不显示相似度或固定置信度百分比。
- 多错因最多3、主因可空、标签最多5、备注300；清除后显示未确定，409保存原草稿。排期及启用新规则先展示before/after和时区，再确认；令牌失效重新预览，重复确认不叠加；撤销不删除作答。
- 来源使用实际`getLearningSource(source_id)`且按需请求；无位置证据显示“资料全文，暂无原题定位”。无来源／历史快照／坏数据有明确状态；不提供空接线AI或同名图谱按钮，图谱精确关联留D级。
- 未提交答案／错因和未确认排期有`canLeave()`；在途写不可用“取消页面”等同取消服务器事务。窄屏历史／排期弹层单开，Escape回触发按钮，焦点约束沿用现有Element弹窗。

- [ ] 失败测试：深链越页仍读指定ID、404不选第一项、后页删除后回退合法offset、详情／历史错误可各自重试，旧请求不能覆盖当前选择。
- [ ] 失败测试：错因清空与409草稿、暂停／恢复／改期／启用／撤销的预览确认、相同确认重试、确认成功但刷新失败应说“已保存，刷新失败”，不能误报写失败再提交。
- [ ] 先运行`node --test tests/wrongbook-workspace.test.mjs`看RED，再实现控制器和页面，运行专项、`npm run build`和`npm run check:bundle`；正文使用语义变量和已有SVG出口。
- [ ] 更新README/API/设计系统中的候选范围与开关，记录源码受影响范围，不把C写成已上线。
- [ ] 提交`feat(wrongbook): 接入目录与单题复盘工作区`。

## Task 4：有界专注批次与恢复

**Files:** 新增`focus-state.ts`、`FocusReview.vue`、`wrongbook-focus.test.mjs`；接入工作区与任务2本机记录。

**Interfaces:**
- `createFocusReviewController(api, submission, preferences, observe?)`：`start(filters, size=10)`、`resume()`、`open(index)`、`skip()`、`next()`、`exit()`、`resetIdentity(scope)`、`dispose()`；size整数1–20，批次来自任务1同一筛选／排序前N个可作答引用，开始后不因列表重排替换题目。
- 过滤paused、legacy_completed、history、invalid；用户可先在浏览模式明确恢复／启用，再开始。没有足够题只用实际数量，不补假题；历史只读不进自动队列。
- 专注DOM不挂原答、解析、参考答案或泄露答案的历史；“查看答案”显式切辅助状态，提交后解释为何不计独立验证。“暂时不会”走真实dont_know；“跳过”仅移动位置、显示未作答，不创建成绩。
- 批次本机只保存引用、digest、位置和已确认attempt IDs。恢复逐题重新核验摘要／只读／删除及服务端回执，不凭localStorage认定完成；异常题显示不可用／跳过，不能移花接木。
- 批次有效期7天为工程默认；过期允许查看已提交记录，重新开批次不重放旧操作。不是服务器学习任务，不增加配额、不自动完成今日任务；跨设备仅保留真实attempt，不承诺同一批次位置同步。

- [ ] RED：默认10／上限20／空批次，开始与跳过0条attempt，回答前DOM数据模型无答案，查看后不可恢复独立标记；成功后才能“下一题”。
- [ ] RED：刷新后回执核验、存储被改伪造完成、题集修订／删除／暂停、身份切换、7天过期；不确定请求恢复先查回执且不自动新键提交。
- [ ] 执行`node --test tests/wrongbook-focus.test.mjs`，实现转GREEN；复跑任务2／3测试及类型检查。
- [ ] 提交`feat(wrongbook): 增加可恢复的专注复习批次`。

## Task 5：三处现有作答入口一致接入

**Files:** 修改`Today.vue`、`LearningArtifact.vue`、`LearningWorkspace.vue`、`course-graph/learning-state.ts`、`types/courseLearning.ts`、`CourseLearning.vue`、`server.py`的今日深链；新增`wrongbook-entrypoints.test.mjs`并更新相应未受保护的既有前端测试。

**Interfaces:**
- 2.0开关开启且服务端允许时，三入口使用任务2同一`createReviewSubmission`与B级submitReviewAnswer；能力未知不发写请求，展示重连。2.0关闭仅对旧可写题保持旧合同，遇2.0拥有／历史题只读；禁止把503、NULL或409转发到旧判题重试。
- `AnswerReceipt.is_correct`显式`boolean | null`，所有消费者按三态展示；看答案、提前练习和待核对不再说“已拿下／匹配度／两次掌握”。今日任务只读真实回执，完成后刷新队列；服务端route=`/wrongbook?focus=<urlencoded wrong_id>`。
- 今日错题使用同一题型输入和完整选项；提交失败保留答案，同题重复事件互斥。回来／页面重新可见时刷新数据，但不覆盖未交输入；原计划勾选保持原合同。
- LearningArtifact暴露`canLeave()/invalidate()`并在KeepAlive停用与卸载清理在途应用；LearningWorkspace将它纳入现有离开保护。题集变化绑定raw快照，历史提示改为真实只读，不再声称可保存旧版复练。
- 图谱练习控制器适配共享提交和可空结果；绑定原course/concept/question代次，失效题先刷新，保持图谱原有证据规则及只读来源边界，不扩展图谱UI或生成算法。

- [ ] 先写RED：四入口（含工作区）相同答案合同；主观NULL不显示错误、2.0题不能被旧算法改写；进入其他题目／账号后旧回执不显示；今日深链定位正确错题。
- [ ] 写RED：KeepAlive切换题集和外部路由均提示原稿、网络不确定沿用原key、参考答案查看后辅助标记真实传输。
- [ ] 跑`node --test tests/wrongbook-entrypoints.test.mjs tests/course-learning-state.test.mjs tests/course-practice-component.test.mjs`，再实施接线转GREEN；后端今日定向测试增加route断言。
- [ ] 提交`feat(wrongbook): 统一今日与课程练习的复习入口`。

## Task 6：真实浏览器、规模与交付

**Files:** 新增隔离fixture和浏览器脚本、`docs/WRONGBOOK_2_0_C_DELIVERY.md`、`docs/audits/wrongbook-2-c-2026-10-26/verification.json`；更新计划checkbox与候选文档。

**Interfaces:**
- fixture：`prepare(data_root: Path, password: str) -> dict`，目录必须绝对且不存在，有合成标记；产生10000错题及选择／填空／主观／超长代码／无来源／历史／坏日期／逾期／暂停样本、第二账号隔离。密码只读环境变量，不输出或提交数据库。
- 浏览器沿用项目已有Playwright通道与实际API；不在真实账号或生产数据执行。断网／503／409使用明确故障注入，业务写入仍经真实隔离服务，测试标明合成工程验收。
- 测桌面1440、1280、1024、768、375px及四主题：目录分页与第10000题搜索、深链／返回位置、作答／待核对、错因持久化、排期预览撤销、专注先答后核对、刷新恢复、两个账号、备份恢复后旧响应失效；收集pageerror、截图、DOM数和请求次数。
- 键盘验收Tab／Enter／Escape，错误焦点、44px目标、正常正文实测对比度≥4.5、缩放200%、减少动态、长文件名／代码／公式；不能只靠源码断言声称浏览器通过。
- 性能分别记录100／1000／10000条的查询与搜索p50/p95、实际API和DOM渲染时间。目标：本机热请求p95≤500ms、浏览器操作反馈≤1s、列表DOM≤30项；属于工程门限不是线上SLA，未达列为失败，不抬高预算。

- [ ] 定向RED→GREEN结束后运行`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`，保存后端／前端／构建／bundle实际输出；不重复跑全套除非有新变更或失败。
- [ ] 用fixture实际起隔离服务并跑新浏览器脚本，保存上述五尺寸、四主题及故障证据到`_working/wrongbook-c-20261026/`；文档仅提交匿名摘要和路径，不提交临时截图／用户资料。
- [ ] 逐项核对本计划及24个受保护测试哈希；C级没有schema变化，B级生产SQLite3.26迁移与恢复仍待E级，不改写其未验收状态。B级间接派生资料删除预览少计事件的Minor仍单列，不顺带隐瞒关闭。
- [ ] 按executing-plans做一次全分支独立审阅，基线e1c97e1；重要问题修复必须有对应失败再通过证据。记录未完成、未执行与已知限制，不用构建成功代替真实交互。
- [ ] 交付报告给出用户变化、公共合同、文件、实测结果、关闭方式、草稿与本机恢复限制；保存提交`docs(wrongbook): 记录C级交互验收与边界`。停止等待用户验收，再讨论D级AI与联动。

## 计划自审（仅文档检查，不是实现验收）

- 设计覆盖：概览／全库筛选→任务1；状态文案与幂等→任务2；目录／单题／错因／排期／来源／历史→任务3；先答后核对与有界恢复→任务4；今日／课程／图谱入口→任务5；可访问性、规模、故障与阶段交付→任务6。
- 五项Review Focus均有归属测试；三态结果、原始expected_question、命名空间与回执函数在邻接任务中保持同一合同。
- 构建器自主选择已明示：不增加schema、本机只保存批次引用与请求摘要、7天过期、≥900px双栏、图谱精确证据留D；没有改变A级七项产品决定。
- 复核范围：这是C级完整计划，当前仅准备文档；所有checkbox均未执行。没有模型／新配额账本／统一OJ排期／生产部署任务。
