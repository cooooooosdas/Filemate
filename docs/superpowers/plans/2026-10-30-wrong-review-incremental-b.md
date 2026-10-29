# 错题增量B级：可信推荐与本次复习预览

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在既有错题状态和真实作答合同上增加可解释推荐、只读时间预算预览与开始前核验，不创建第二套状态机。

**Architecture:** 复用ReviewQueries/ReviewRepository、现役身份SQLite和1—20题专注批次引用。推荐只取当前筛选内可复习且到期的题，SQL先排序再分页；预览/核验均只读，不建长期计划。UI布局及正式入口在C级实施。

**Tech Stack:** Python>=3.10、FastAPI/Pydantic、SQLite>=3.26、Vue/TypeScript现有服务合同。

**Spec:** docs/superpowers/specs/2026-10-29-wrong-review-incremental-a-audit.md；原增量包CODEX_MASTER_PROMPT的B1—B4；用户2026-10-30明确“ A级通过，开始B级、”。沿用当前会话逐项实施、最终一次独立审阅。

## Global Constraints

- 默认仍sort=due；显式sort=recommended才使用推荐，推荐分数不等于掌握率。
- 推荐规则review2-priority-v1：min(上海逾期天数,30)*3 + min(已保存的历史错答次数,10)*4 + 人工确认错因4分；仅作排序启发式，不声称学习效果。
- 推荐固定按分数降序、到期时间升序、wrong_id升序；direction不改变此顺序，服务合同明确说明。原四类排序保持原义。
- 推荐与预算候选取原筛选和“active、到期、有效记录、非历史只读、非旧版已完成”的交集；V2已达本轮标准但再次到期仍可入选。
- 同一服务端as_of贯穿筛选、排序与响应；上海日界，旧无时区时间继续按UTC解释。异常/溢出日期不拖垮整页。
- available_minutes为严格整数0..1440；minutes_per_question严格整数1..60、默认4，仅为“本次短练预估”，不替换今日学习的10—15分钟完整复盘建议。批次最多20题。
- 预览只读；开始前核验题集版本、wrong_id/修订号/到期时间、暂停/来源/只读/权限；缺失或陈旧返回409，禁止静默换题或建任务。
- 不新增迁移、状态表、模型调用或密钥外发，不修改掌握/排期/幂等算法。V2开关维持原缺省。
- 不触碰原有24份测试的字节或用户资料。所有合成库/日志放独立_working/review2-incremental-b-20261030。
- 本轮仅B；C的可见控件和布局、D/E后续验收及发布不得冒称已完成。

## Review Focus

1. 筛选与前30条之外的高优先级题：必须全范围排序后取页；Task2固定一个位于远页的最高分题。
2. 预览后题目/排期/身份变化：核验不能沿用过期引用；Task3覆盖暂停、修订、删除和另一空间相同外观数据。
3. 时间跨上海午夜及极端偏移日期：Python解释和SQL排名一致；Task2对午夜与越界时间有独立断言。
4. 相同输入的重复预览/核验：不得写任务、attempt或event；Task3比较表计数和状态摘要。
5. 用户时长为0、布尔、浮点或超界，及旧达标/暂停/只读：不能产生虚构候选或500；Task2/3覆盖精确类型与资格交集。

## Task 1: 修复证据工具的最低版本兼容

**Files:** scripts/acceptance/wrongbook_learning_evidence.py；新增filemate/tests/wrongbook/test_acceptance_compat.py。

**Interfaces:** source_hashes() -> dict[str,str]合同保持；遍历仍排除web/缓存/依赖并纳入既有前端文件。

- [x] 写test_source_hashes_without_path_walk：在临时树放一份Python、一个web/node_modules诱饵和一份Vue；替换ROOT并让Path.walk调用失败，断言只有合约要求文件参与摘要。
- [x] 运行`.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_acceptance_compat.py -q`，Expected：旧实现因Path.walk失败。
- [x] 用兼容的os.walk和pathlib.Path替换Path.walk，不提高项目版本门槛；运行上述测试，Expected：通过。
- [x] 用现有uv管理的Python3.11.15真实调用source_hashes，Expected：成功；记录未安装3.10的边界，检查静态py310规则。
- [x] 提交`fix(audit): 兼容旧Python的源码摘要遍历`，task-done复跑该文件。

## Task 2: 透明推荐及有界查询

**Files:** 新增filemate/wrongbook/insights.py、filemate/tests/wrongbook/test_insights.py；修改queries.py及test_workspace_reads.py；按实测需要在page中先取排序键/ID再取本页正文。

**Interfaces:** priority_details(row:dict, *, now:datetime) -> dict，返回priority_score/overdue_days/reason/rule_version；ReviewFilter.sort增加recommended；ReviewQueries.page保持普通页合同，推荐页items增加priority，顶层给priority_rule_version和recommendation_scope。不暴露参考答案。

- [ ] 先写纯函数与查询测试：同分稳定；上海同日不逾期；无效/溢出时间拒绝；暂停、只读、坏记录、未来题排除；旧mastered排除但V2 criterion_met到期保留；跨页最高分先出；普通due结果不变；新原因不是掌握率。
- [ ] 运行新测试，Expected：缺少insights/recommended合同或断言失败。
- [ ] 用当前受控只读快照、现役parse_time和版本状态实现；错误计数非非负整数的记录不纳入推荐，不虚构次数。冻结as_of，排序使用同一规则常量且结果最多limit条。
- [ ] 在全新四规模合成库记录cProfile/EXPLAIN和HTTP四并发基线；若SQL宽行排序占用突出，采用排序键/ID有界物化后按ID取正文。原500ms门槛不变，不以优化意图关闭E-P2-01。
- [ ] 测试SQL和Python原因的一致性、JSON1与兼容分支、全范围过滤和别的身份；运行`.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_insights.py filemate/tests/wrongbook/test_workspace_reads.py -q`，Expected：通过。
- [ ] 提交`feat(wrongbook): 增加基于证据的可解释推荐`，task-done复跑上述文件。

## Task 3: 只读时间预算预览与开始前核验

**Files:** 新增filemate/wrongbook/session_preview.py、filemate/tests/wrongbook/test_session_preview.py；修改api.py、services/review-api.ts、types/wrongbook.ts；新增前端合同测试wrongbook-session-api.test.mjs。

**Interfaces:** ReviewSessions.preview(filters:ReviewFilter, *, available_minutes:int, minutes_per_question:int=4) -> dict；ReviewSessions.check(refs:list[dict]) -> dict。新增`GET /wrongbook/v2/session-preview`和`POST /wrongbook/v2/session-check`，均受现有V2开关、认证和Origin保护；服务端不接受客户端now或user_id。

预览参数复用page筛选加available_minutes/minutes_per_question；最多20条，返回status=preview_only、scope=filtered_eligible_due、as_of/day_zone、eligible_count/selected_count/deferred_count、estimated_minutes/available_minutes、items（每项ref含wrong_id/artifact_id/question_index/question_digest/revision/next_review_at，另含简短题干与priority）。不返回原答或参考答案。sort默认仍due，recommended才采用推荐。

核验JSON为严格对象`{refs:[...]}`，1—20条，不接受重复wrong_id。任一身份不符/不存在/版本变化/排期变化/失去资格均409统一安全提示，无部分开始；成功返回status=ready和原refs及server as_of，无数据库写入。真正作答仍由既有attempt端点独立处理。

- [ ] 写预览类型/边界/预算/有界/全范围测试；核验前后无任务、作答、事件变化；预览后暂停、源删除、题目替换、revision变化、跨空间均拒绝；先测RED。
- [ ] 实现只读服务，复用同一read_snapshot内筛选/推荐逻辑，禁止从第一页拼全库；开始前比对当前题集原始题目摘要。重复预览/核验保持只读。
- [ ] 注册静态路由在`/{wrong_id}`之前；GET白名单允许新增预算字段且拒绝重复/未知键；POST严格类型/体积/数量，不引入模型凭据入口；V2关闭503，其余历史路由不变。
- [ ] 补类型和服务端调用函数getReviewSessionPreview/checkReviewSession，不挂载UI；测试请求路径/参数/方法、共用客户端、无密钥头。
- [ ] 运行`.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_session_preview.py -q`与前端该合同测试，Expected：通过。同步API_SPEC/README，提交`feat(wrongbook): 提供本次复习预览与只读核验`。

## Task 4: B级串联验收、故障与交付

**Files:** 新增filemate/tests/wrongbook/test_incremental_b_flow.py、B级交付/证据与账本；必要的同范围回归修复，不扩展C界面。

**Interfaces:** 前三任务的真实只读HTTP和现役attempt/schedule/today合同。

- [ ] 编写同一合成身份串联测试：收录真实错答→推荐/时长预览→核验→同键重放作答仅一次→状态更新→今日队列→新客户端刷新读取；无效输入/数据库故障/另一身份均不泄漏或修改状态。
- [ ] 运行该文件与全wrongbook目录，Expected：通过；补API损坏记录降级和题集版本冲突，不把AI候选当客观判定。
- [ ] 执行`scripts/verify.ps1 -IsolateFrontend`，Expected：退出0；所有跳过和未执行项明示。新运行性能四规模/列表搜索/四并发，原样保留超标结果；未达标不关闭P2。
- [ ] 一次新上下文审阅本B增量，Important一轮RED/GREEN修复，不派重复复审；Minor按规则记录。
- [ ] 保存本轮新源码摘要及证据，不重写上轮E冻结清单；更新索引/README/API与B交付，区分已实现后台合同、未挂载的C入口和真实研究依赖；本地提交归档，不推送或部署。
