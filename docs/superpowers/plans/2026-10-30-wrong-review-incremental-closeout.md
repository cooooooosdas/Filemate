# 错题增量 C—E 收尾实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 按用户本轮“全部一并完成”授权连续实施，不再重复逐级询问。

**Goal:** 把已完成的推荐、时长预览与只读核验接入真实工作台，完成现有学习联动及新增界面的验收和本地交付。

**Architecture:** 保留两栏和现役作答／计划事务；新预览控制器管理异步请求和失效，不保存答案。开始前经服务端核验，再交给现有专注控制器。D 级优先核验现役联动，只修确有缺口处。

**Tech Stack:** Vue 3、TypeScript、现有 SVG／CSS 令牌、FastAPI、SQLite；不新增依赖、迁移、开关或平行状态库。

**Spec:** `docs/superpowers/specs/2026-10-29-wrong-review-incremental-a-audit.md` 第8节已确认方案；开发文件 `_working/review2-incremental-a-20261029/candidate/CODEX_MASTER_PROMPT.md` C—E；B 合同见 API_SPEC。

## Global Constraints

- 默认到期排序，recommended 显式选择；推荐不是掌握率。
- 预览沿用服务端资格、上海日期和全范围计数，不在浏览器遍历分页或重算资格。
- 最多20题，时长为预估；开始不创建长期计划或作答。
- 保护原24项修改、草稿、未知回执、账号隔离、旧批次恢复与7天期限。
- 保留四主题、无衬线、大字、SVG、44px触控及 reduced-motion；指定宽度375/390/1024/1366/1920。
- 不接触生产库或密钥；生产验收、真实学习研究与工程验收分开。当前只交付候选，不推送部署。

## Review Focus

- 预览／核验晚响应不得复活已变更预算、筛选或身份；任务1测试。
- 部分或乱序核验结果不得偷偷替换选题；任务1测试。
- 开始新批次不得清除未提交回答，或自动回退到另10道题；任务2测试及浏览器验证。
- 刷新继续原批次、已答题不重复提交、完成后概览读到新证据；任务2/3测试。
- 手机当前题靠前，长文不横溢，键盘与四主题可用；任务3浏览器验证。

### Task 1: 有界预览控制器及推荐浏览条件

**Files:** Create `filemate/web/src/wrongbook/session-state.ts`, `filemate/web/tests/wrongbook-session-state.test.mjs`; Modify `wrongbook/browse-state.ts`。

**Interfaces:** Consumes `getReviewSessionPreview`, `checkReviewSession` 和B的DTO；Produces `createReviewSessionController(api,observe)` 的 `state/load(filters,minutes,perQuestion)/check/invalidate/dispose`。check仅返回完整匹配的ready或null。

- [ ] 写测试：recommended网址往返；整数边界；空选；晚预览；晚核验；409失效；网络失败重试；返回引用不全／乱序；销毁。
- [ ] `node --test tests/wrongbook-session-state.test.mjs`：先观察新控制器未定义／推荐未接受的真实失败。
- [ ] 实现共享控制器：每次请求递增代次，条件变更立即清空预览，保持服务端选择顺序，失败不开始批次。
- [ ] 同命令全绿并运行browse测试；提交 `feat(wrongbook): 接入时长预览与核验状态`。

### Task 2: 正式界面与专注批次交接

**Files:** Create `components/wrongbook/ReviewSessionPlanner.vue`; Modify `ReviewWorkspace.vue`, `ReviewList.vue`, `FocusReview.vue`, `review-workspace.css`, `wrongbook/focus-state.ts`; Test `tests/wrongbook-focus.test.mjs`, `tests/wrongbook-component-wiring.test.mjs`。

**Interfaces:** Consumes任务1控制器；Produces专注控制器 `startChecked(refs:ReviewSessionRef[]):Promise<boolean>`，及planner的ready事件；父层确认离开草稿后才替换批次。

- [ ] 写并运行失败测试：准确引用交接不调用getReviewPage；dirty时不替换；重复ID／超过20拒绝；详情变化不替换别题；组件预算变更使预览失效。
- [ ] 接入可见推荐选项与理由、时长预览和明确开始按钮；focus仅恢复原批次或接受已核验引用，不自动创建10题替代。
- [ ] 专注时收起目录头部；窄屏单题时隐藏概览／筛选，保留返回目录。按需证据和现有答案保护保留。
- [ ] 运行上述测试、完整前端测试及build：0失败，vue-tsc和构建返回0；提交 `feat(wrongbook): 完成专注复习引导与移动布局`。

### Task 3: D联动核验、E验收和交付

**Files:** Create `scripts/acceptance/wrongbook_incremental.mjs`, `docs/WRONG_REVIEW_2_0_RELEASE.md`；更新README和当前交付索引；证据放`_working/wrongbook-incremental-closeout-20261030/`，冻结摘要归档docs/audits。

**Interfaces:** Consumes任务2真实界面、现役认证／合成夹具、learning/journey验收工具；Produces可复核报告与本地候选包，不虚构生产或真人结果。

- [ ] 新真实浏览器验收先验证现状失败／缺口；实现后测试推荐、预算、核验冲突、重新预览、作答、刷新、账号边界、空库、失败恢复。
- [ ] 测375/390/1024/1366/1920及四主题、键盘和减少动效，留真实截图及操作说明。
- [ ] 用原创栈队列题运行现役学习联动及故障用例，持久化结果与备份恢复分开记录；无缺口不重建D业务。
- [ ] 运行`scripts/verify.ps1 -IsolateFrontend`；证据真实返回0；源摘要、原24文件摘要一致。
- [ ] 最终一次独立只读审阅本轮范围（BASE=476874b），必要重要修复红绿验证；整理本地包、报告、剩余外部依赖并提交。

## 计划自审

全部新增行为对应任务1/2；D使用现役实现由任务3验证，不引入第二套规则。任务1/2的DTO与B服务一致。用户本轮要求整体完成，覆盖开发文件旧的逐级等待约束；继续沿用当前会话实施及最终一次独立审阅。
