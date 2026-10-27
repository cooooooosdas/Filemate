# 错题复盘2.0 C级交互工作台交付记录

2026-10-27完成。本地工程验收通过，等待用户C级阶段验收；总体CONDITIONAL PASS。没有推送、合并或生产部署。

## 用户可见变化

- 全库搜索与筛选先执行再分页，目录默认30项；资料／课程选项可继续查询，不把第一页当作全库。
- 大字单题工作区提供完整选择题、填空、简答、代码输入；主观结果显示“已保存，待核对”，不把NULL当错误。
- 原回答、来源原文、错因、真实历史和排期按需展开；暂停、恢复、改期、撤销均先预览再确认。
- 默认10题、最多20题的专注批次先答后核对。查看答案后保留辅助标记；跳过不写成绩。完成标识向服务器核验后才计数。
- 今日、资料练习、图谱练习使用同一幂等提交合同；不确定结果先查询回执，409保留原稿，不回退旧判题。
- 五种宽度与四种既有主题；沿用蓝色、无衬线大字、SVG图标。长代码有界滚动，200%缩放不应横向溢出。

## 合同、代码与关闭方式

延用schema35及B级复习事务，没有C级数据迁移。只读API追加page、filter-options、capabilities、receipts、question-access。题目详情保持原始快照；浏览展示不改写expected_question。

后端`filemate/wrongbook/queries.py`负责有界投影；`api.py`固定路由优先于详情通配路由。前端`services/review-api.ts`复用原认证Axios；`wrongbook/`纯控制器管理提交、批次、导航与身份代次；`components/wrongbook/`负责目录、问题、证据、预览和专注界面；Today、LearningArtifact与CourseLearning接线。验收脚本为`scripts/acceptance/wrongbook_workspace_fixture.py`与`wrongbook_workspace.mjs`。

新工作台需构建时`VITE_ENABLE_WRONGBOOK_V2=true`，服务端新写入需`FILEMATE_ENABLE_WRONGBOOK_V2=1`。均默认关闭。关闭后2.0拥有记录与历史题集保持只读，不让旧判题改写；未升级的旧可写题按原合同继续。图谱练习还依赖现有课程图谱开关。

## 本轮修复的真实交互问题

浏览器暴露并修复了：成功回执被专注模式收起；Vue可选Boolean缺省导致“查看答案”隐藏；核验尚未结束就刷新丢失回执引用；两个偏好控制器互相覆盖批次；排期事件名称与撤销入口不一致；关闭弹窗后的焦点丢失；超长代码撑高页面；200%缩放顶栏溢出；记录window滚动而未记录实际内容滚动容器。每项对应实际浏览器失败日志或先失败再通过的回归测试。

1万条搜索曾实测约700ms、界面反馈约1900ms，未通过原门限。原因是逐行JSON解析跨Python回调；有JSON1时改为原生安全提取，缺少扩展时保留UDF兼容路径。门限仍为API热请求p95≤500ms、操作反馈≤1s、目录DOM≤30，没有放宽。

## 验证结果

- 最终全量门禁exit 0：后端1648通过、22跳过、5按标记排除、3条依赖弃用警告；前端257通过、0失败，Ruff、类型检查、构建及体积检查通过。
- 新版开关开启／关闭构建均通过，首屏gzip分别142888／142929字节，预算143360字节，没有扩大预算或提前载入重模块。
- 真实Edge浏览器21组通过，pageerror为0；五种屏宽×四主题共20组视觉检查，另含375px专注作答、键盘、200%缩放、减少动态。对比度只测题目与阅读面板，不泛称全站无障碍通过。
- 100／1000／10000条真实鉴权API，各丢弃2次预热后记录20次；万条列表p95约45.7ms，搜索p95约71.6ms；实际页面搜索反馈467.8ms、目录搜索结果DOM为1项，默认列表最多30项。
- 此前并行后台回归负载下的1532.6ms页面反馈失败记录仍保留。最终独立运行达到原门限，不能外推为生产高负载SLA。
- 一次全分支独立审阅发现8项Important，全部在同轮以RED→GREEN修复；没有追加复审。详见[审阅与修复](audits/wrongbook-2-c-2026-10-26/review.md)。24个原有修改状态测试逐文件SHA256均未改变；schema仍为35。

匿名机器摘要：[verification.json](audits/wrongbook-2-c-2026-10-26/verification.json)。原始日志／截图仅保存在`_working/wrongbook-c-20261026/`；不提交数据库、密码、截图或真实资料。22项跳过主要涉及Linux分支、可选OCR、缺少样本及符号链接权限；5项真实端到端测试按not e2e排除。

## 已知边界

- 所有数据是原创合成工程样本；没有真实学生实验、模型调用、学习效果或长期记忆结论。
- 未提交回答仅留在页面内存；离开／刷新会提示，仍应自行复制需要保留的原稿。跨浏览器与清理本机存储不能恢复草稿。
- 本机批次仅存题目引用、摘要、位置和回执标识，7天到期；最多20题。请求恢复仅存幂等键与摘要，不保存回答正文；身份命名空间不可用时只保留页内状态。
- 批次完成回执仅查本题最近100次记录，过旧标记保守显示待核验，不据本机数据生成成功结论。
- 无有效来源、历史只读、题目修订、无效日期及已删除记录会保留说明；不静默切成另一道题。
- 本机SQLite回归不代替生产SQLite3.26执行。未验证生产迁移／恢复，JSON1缺失时兼容查询性能也需现场测量，继续列入E级。
- B级保留Minor：通过kg_learning_artifact_sources间接依赖的资料删除预览，可能少计review_events；实际级联删除有效。本轮未改动该边界。
- D级授权AI诊断／预算、图谱精确证据联动及E级整体验收不在本轮；没有推送、合并或部署。

## 执行裁定记录

以下逐行保存执行裁定及代价，含后来被替代的方案；完整账本见[执行记录](audits/wrongbook-2-c-2026-10-26/execution-record.md)。

- Ruling: No new worktree or dependency reinstall — existing isolated worktree and installed runtimes are the tested B environment — cost if wrong: baseline dependency drift, checked by baseline and final verify.

- Ruling: move review HTTP implementations to services/review-api.ts with lazy services/api.ts facades — build measured 144014 gzip > 143360 budget; preserve public call signatures and shared auth interceptors — cost if wrong: lazy import or cycle errors, covered by enabled build and real browser.

- Ruling: direct route-only services/review-api.ts over named lazy facades; all callers retain the shared authenticated Axios client. New UI split the Vue runtime and added gzip overhead; group its interdependent runtime modules in Vite. Enabled build now 142786 / 143360 gzip bytes, without widening budget or excluding static imports. Cost if wrong: shared-runtime regressions, covered by full gate/browser.

- Ruling: add scoped question-access read endpoint before legacy submissions — artifact/index entries do not carry wrong_id, so client cannot otherwise know 2.0 ownership before a rejected POST; no schema or writes added. Cost if wrong: extra bounded GET per question; measured in browser and full regression.

- Ruling: use optional SQLite JSON1 for native stem search with guarded malformed JSON and UDF fallback when unavailable — measured 10000-row Python callbacks exceeded 500ms; no schema/runtime upgrade — cost if wrong: compatibility fallback may miss the performance target on SQLite without JSON1, explicitly remains an E/runtime measurement dependency.

- Final: Ruling: production SQLite3.26 migration/restore and JSON1-free performance remain E dependencies — local functional and timing checks cannot prove production runtime behavior — cost if wrong: production-only migration/performance failure; not approved for deployment here.

- Final: Ruling: D AI analysis, precise graph links and incremental goals stay outside C — preserving the approved stage boundary — cost if wrong: those desired integrations remain unavailable until D.

- Final: Ruling: no real-student learning or live-model claim — synthetic engineering checks only — cost if wrong: effectiveness and live service reliability remain unproven.

- Final: Ruling: retain B derived-source deletion-preview undercount as the existing Minor — actual deletion works; C does not change this B boundary — cost if wrong: a user sees an understated review-event deletion count.

- Final: Ruling: do not add cross-device batch sync or forced-close answer recovery — contract keeps unsent text only in memory and gives leave guards — cost if wrong: forced closure still loses unsent text.

- Final: Ruling: course code-reading uses the existing supported short_answer type with a code field, displayed as code and saved pending — a synthetic fixture incorrectly used unsupported question_type=code and correctly received 422; do not expand the course grading contract or execute code — cost if wrong: code responses remain ungraded until evidence-based review; unified OJ stays a separate card.

- Task 6: Ruling: task-done uses a closeout command that checks the just-completed mandatory full verify receipt, pinned source hashes and 21-check browser receipt, then reruns the complete frontend suite — avoid repeating the long backend run without a new source change — cost if wrong: stale evidence could be accepted; exact exit receipts and unchanged source hashes gate completion.

保留轻微项：B级间接派生资料删除预览少计review_events；实际级联删除正确。独立审阅没有新增C级Minor。


## 收尾修复与实际边界

独立审阅后补齐多作答组件共享恢复、回执题目与版本核验、刷新后原答／原动作重试、手机专注样式、资料切换及刷新保护、资料页身份／恢复失效、作答后的详情修订刷新，以及图谱连续切题的一次性离开许可。读取最新详情失败时保留成功回执，禁止继续用旧revision写入，可点“重新读取详情”。

课程代码阅读沿用short_answer＋code字段，支持完整代码文本输入与待核对保存；没有把课程练习当作OJ执行。合成备份恢复覆盖错题工作台与资料练习两处，实际执行签名ZIP预览确认，应用恢复通知属于显式注入，不代表完整隐私面板或生产恢复验收。

清理本轮`.superpowers/sdd/2026-10-26-wrongbook-workspace`临时目录时，自动审批审查返回“被策略拦截”，未给出进一步原因；删除未执行，没有改用其他方法删除。该目录继续保留，不影响已提交代码、验收和原始证据。
