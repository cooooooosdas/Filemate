# C级执行取舍与风险

按原始执行顺序完整列出13条Ruling记录；第12条为第11条的重复日志。最终独立审阅产生的处置另见review.md及完整执行日志。

## 1

将新合同回归集中在test_context，原三套并跑；若判断有误，测试组织可能遗漏边界。

Task 1: Ruling: new context, snapshot and receipt regression cases live together in test_context.py; the three existing suites run unchanged alongside them. This keeps the tests together without rewriting existing fixtures; the named plan tests are present.

## 2

沿用预览／撤销30秒、读取15秒；若判断有误，慢命令等待会较久。

Task 2: in_progress; BASE=95326d79bfee5a3d14fc07129209d151121a6f59. Brief read. Ruling: retain existing 30s preview/undo-preview command timeouts; metadata/snapshot/day/operation reads remain15s. Draft tests prepared while Task1 gate ran; copied only after Task1 completion. No implementation before RED.

## 3

仅恢复服务端明确确认的范围，不凭最近偏好猜目标；代价是未确认范围需重选。

Task 3 GREEN:15 initial cases passed; malformed-response regression RED1/15, then complete frontend334/334 and type/build/original bundle PASS. Ruling: restore only the server's explicitly confirmed today scope, not recent-goal/preference recency; no new TodayState fields needed. Pending storage stays per-tab and is preserved on route leave, removed for the known identity on reset. No domain writes or model calls.

## 4

跨日未决可经新预览沿用原键，旧日获胜回执仅显示历史；若判断有误，用户需再次核验范围。

Task 4: in_progress; BASE=6b6101e2e0bfd970c42d304b95196ba3bed34a7d. Brief read; real command module tests observed assertion RED before implementation. Ruling: a fresh explicit preview may resume the same unresolved confirmation key on a newer server day; any older winning receipt is shown as history, not applied to current day. This avoids abandoning a stable key or permanent404 while preserving server authority.

## 5

原入口定位辅助保留在懒加载模块；代价是首次进入需额外加载分块。

Task 5: in_progress; BASE=e25e7284613dd3f9f1d36f5dcd6436b2030edff9. Brief and current domain code inspected. Prior goal turn produced Tasks1-4 commits and gates; subsequent resume only revalidated state. Taking next safe action: behavioral routing tests. Ruling: pure domain locator helpers remain in lazy today/navigation.ts instead of eager App route-state.ts, because initial gzip has137 bytes headroom. The original route-state behavior remains unchanged; route-state tests exercise the real lazy helpers alongside legacy regressions.

## 6

旧错题页仅支持目录时明确回退，失效／歧义ID仍阻止导航；代价是旧页不能精确聚焦。

Task 5 GREEN: initial RED8/10 then18/18. Existing /goals evidence-review route found during source audit, regression RED1 then fixed with exact original goal/task context. Final frontend362/362, type/build/bundle PASS. Ruling: legacy Wrongbook does not support exact-item focus; preserve its original query and disclose directory-only fallback, while invalid/ambiguous IDs block both versions. Pure locators are lazy and used by actual Vue views. Browser click evidence remains Task7.

## 7

新增入口状态辅助也懒加载，保护原gzip预算；代价是入口存在异步加载。

Task 6 GREEN: static A preview rendered in installed Edge, desktop1440x1000/mobile390x844; clearly synthetic layout-only. Navigation/entry/mode RED3/22 then25/25; full frontend365/365, type/build/original bundle PASS (gzip142771/143360). LegacyToday byte-for-byte preserved including leave guards. Initial typecheck caught options function shadowing its prop; renamed helper and reran. Ruling: add a tiny lazy entry-state helper used by shell and GoalPlanner, not an eager App dependency. New workflow uses existing evidence and command controllers; no model calls or second task table. Browser acceptance remains Task7.

## 8

实际浏览器发现今日页过渡卡住，增加稳定DOM根；若判断有误，额外容器可能影响布局。

Task 7: Ruling: real Edge regression waited 5s for actual today root opacity=1 and failed; root retained page-fade-enter-from after loading→lazy component substitution. Keep a stable Today shell element so router transition owns one DOM root. This lifecycle failure is tested in the real browser rather than mirrored in a pure-state unit test. UI document title is also aligned to 今日行动.

## 9

实际浏览器发现错题返回卡住，同样增加稳定根；若判断有误，额外容器可能影响原页布局。

Task 7: Ruling: actual wrongbook answer saved with HTTP200, but clicking 返回今日行动 left only the app shell; its conditional fragment root prevented out-in route transition completion. Real browser return/navigation assertion was RED. Wrap Wrongbook in one stable root and rerun the same journey; preserve inner domain guards and data.

## 10

默认npm ci文件锁失败如实保留，改用已有隔离门禁；旧计划缺可选topics仅做读取兼容。代价是增加验证目录，其他异常旧数据仍需单独验证。

Task 7: Ruling: full verify default npm ci collided with the owned running Vite native binary (EPERM); backend suite completed first. Archive this failed integration run, restore pinned packages after stopping only owned Vite, and use the existing -IsolateFrontend option for the final full gate (same tests/build/budgets). Browser also exposed an existing valid minimal plan without optional topics crashing render; keep stored data and guard missing topics, then rerun exact day navigation. No speculative npm or dependency version change.

## 11

实体手机输入法与实际200%缩放明确未测，仅测等效视口；代价是仍需真实设备验证。

Task 7: actual Edge final evidence archived; 74 browser assertions across 14 phases (computed total in browser.json is authoritative), 368 frontend tests, type/build and unchanged bundle limits PASS. Other goal full-record hash and original completed plan index0 preserved; index2 completion is intentional actual-domain navigation. No real student data or deployment. Ruling: physical mobile IME and physical browser zoom are NOT RUN; test reduced-height input and equivalent CSS viewport only, so no hardware claim. Entire default verify failure retained rather than called PASS. Task8 owns final isolated gate.

## 12

与上一条完全相同，为执行日志重复记录，不构成另一项决定；相同设备验证依赖保留。

Task 7: actual Edge final evidence archived; 74 browser assertions across 14 phases (computed total in browser.json is authoritative), 368 frontend tests, type/build and unchanged bundle limits PASS. Other goal full-record hash and original completed plan index0 preserved; index2 completion is intentional actual-domain navigation. No real student data or deployment. Ruling: physical mobile IME and physical browser zoom are NOT RUN; test reduced-height input and equivalent CSS viewport only, so no hardware claim. Entire default verify failure retained rather than called PASS. Task8 owns final isolated gate.

## 13

调度严格全表指纹；恢复仅将明确面试安全列单列验证版本轮换，其余业务字段仍逐项相同。若判断有误，新安全归一化变化必须更新证明，不能整表排除。

Task 8: Ruling: nonempty interview fixtures exposed intentional backup normalization, not score loss. Scheduling still requires the full all-table fingerprint unchanged. For restored snapshots compare every business field, with only the two documented safety-state column sets separately asserting exact revision+1, consent+1/revocation, cleared digest, and nondecreasing update time. All original scored turns, confirmed relations/evidence, review answers/events and completed plans are also compared verbatim after personal restore. Cost if wrong: a newly introduced safety normalization must change this explicit proof; it cannot silently be excused by an entire-table skip.

## 最终审阅的五条处置与代价

- Final: Ruling: D/E model coach, deployment and real-student effects remain outside C — approved staged scope retained — cost if wrong: those product outcomes require later authorized work.
- Final: Ruling: physical IME/zoom, other engines and production load remain NOT RUN — static review cannot certify devices — cost if wrong: device or production-only issues may remain.
- Final: Ruling: 23 prior user tests and later audit files are outside independent code range — preserve hashes and separately validate author evidence — cost if wrong: independent review does not certify those artifacts or a clean-checkout full suite.
- Final: Ruling: unrelated legacy domain designs remain outside C review — connected restore contracts were included — cost if wrong: unrelated historical bugs remain possible.
- Final: Ruling: invalidate unused undo authority at the issue-day boundary, while fresh explicit history undo and successful replay remain valid — preserves prior history behavior without retaining stale permission — cost if wrong: history actions still need careful user confirmation.
