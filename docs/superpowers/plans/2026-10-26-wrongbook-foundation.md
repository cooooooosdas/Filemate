# 错题复盘2.0 B级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有课程作答与错题实体上实现有证据、可解释、可恢复的复习基础，保持旧功能可用。

**Architecture:** 追加业务migration35，保留原ID、rowid和历史规则。纯排期引擎与事务Repository分离；复用现有tenant storage、data_actions预览和个人备份机制。新写入口默认关闭，新证据读取及隐私操作不受开关影响。

**Tech Stack:** Python/FastAPI/Pydantic/SQLite；Vue前端合同只补类型和服务，本级不重排页面。

**Spec:** [A级审计与已确认设计](../specs/2026-10-25-wrongbook-2-design.md)。2026-10-26用户明确确认七项推荐及A级通过，授权进入B。

## Global Constraints

- 生产SQLite最低3.26.0；只追加35，不修改v1—v34，不依赖RETURNING、MATERIALIZED或DROP COLUMN。
- 原24个用户修改测试保持逐字节原样；临时证据放`_working/wrongbook-b-20261026/`。
- 间隔1/3/7/15/30天；当场纠正不计延迟验证；至少三次合格独立正确、三个上海日期且首末跨度≥7天才达本轮标准。
- 提前练习、看答案、自查、AI辅助不推进确定状态；历史两次复练不自动改判或塞回队列。
- NULL表示未判定，不用0/false占位；旧数值保持原义；新主观题不使用文本包含规则认定正确。
- `FILEMATE_ENABLE_WRONGBOOK_V2=0`默认；C的布局/专注会话、D的AI/目标建议、E的发布验收不在本级实施。
- 不新增Provider、模型调用、配额账本、用户画像或OJ调度。所有文件/排期覆盖操作先预览确认，可重复回放、可冲突拒绝。

## Review Focus

1. v34迁移及旧备份恢复后，作答rowid、原错答、资料级删除和FK仍正确；Task1/6用真实临时库验证。
2. UTC旧时间、上海午夜、闰日、无效时间、提前练习和同日多次正确不会冒充到期验证；Task2固定时钟测试。
3. 同键换答案、跨连接并发、错误发生于作答与事件之间，必须分别409/单记账/整体回滚；Task3验证。
4. 预览后有新作答/错因修改、恢复备份或跨用户使用token，必须拒绝陈旧确认和撤销；Task4/6验证。
5. 未判定结果不进入成长/图谱/技能正确率，关闭新功能不能回退旧算法改写新状态；Task5验证。

## File Structure

- Create `filemate/wrongbook/{__init__,schema,engine,repository,commands,api}.py`：分别为包、迁移、纯规则、证据事务、排期确认、HTTP合同。
- Modify `filemate/execution/storage.py`：注册迁移、保护新版证据写入、统一旧查询过滤；不重排巨大文件。
- Modify `server.py`：注册同tenant路由、今日全量统计；`study/evidence_profile.py`、`course_graph/learning_evidence.py`、`portfolio/growth.py`、`study/skills.py`：可信证据筛选。
- Modify `filemate/operations/personal_backup.py`（仅在恢复兼容需要时）、`README.md`、`.env.example`、`filemate/docs/API_SPEC.md`：恢复边界及新合同。
- Create `filemate/web/src/types/wrongbook.ts`；Modify `services/api.ts`：新API类型与服务，不改变旧视图。
- Create `filemate/tests/wrongbook/`：真实SQLite/HTTP/规则/迁移回归，不改受保护测试。

### Task 1: 追加迁移与旧记录兼容

**Files:** schema.py、storage.py；tests/wrongbook/test_schema.py。
**Interfaces:** migration35消费v34；产生可空is_correct/score、purpose/judgement/status/version/digest/duration等作答字段；错题revision/schedule/阶段/验证起止/多错因字段；review_events记录before/after及request摘要、可空attempt FK、undo引用。

- [ ] 写测试：用v34迁移脚本构造真实历史数据；迁移后原ID/rowid/答案/时间/索引/FK不变，可保存NULL结果；二次init不变；坏DDL注入后v34原表完整且版本不增加。
- [ ] 运行`.venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_schema.py -q`，观察预期失败（无35或列不支持NULL）。
- [ ] 实现迁移；旧scheduler_version默认legacy-v1，不反推不存在的复习类型或合格次数。重建quiz_attempts显式复制rowid，重建原索引；新增表无反向原表引用循环。
- [ ] 同命令及原错题/存储回归通过后，提交`feat(wrongbook): 追加复习证据兼容迁移`。

### Task 2: 纯状态机与时间规则

**Files:** engine.py；tests/wrongbook/test_engine.py。
**Interfaces:** `transition(state: dict | None, *, correct: bool | None, independent: bool, now: datetime) -> dict`；`parse_time(value) -> datetime | None`；常量RULE_VERSION与INTERVALS。返回状态补丁及eligible/purpose/reason，不访问DB或模型。

- [ ] 写表驱动测试：新错立即到期、纠正+1天、1/4/11天验证、30天封顶、再错重置、早练不延时、同上海日不推进、看答案/待核对不合格；无效排期不可猜测；UTC旧时间与闰日。
- [ ] 运行`pytest filemate/tests/wrongbook/test_engine.py -q`观察行为缺失。
- [ ] 实现固定规则，注入带时区时钟，不从旧review_count推导新次数。
- [ ] 同命令通过后提交`feat(wrongbook): 实现可解释间隔复习规则`。

### Task 3: 真实作答、诊断与历史事务

**Files:** repository.py、storage.py；tests/wrongbook/test_repository.py。
**Interfaces:** `ReviewRepository(storage, *, clock=None)`；`submit(payload: dict) -> dict`、`detail(wrong_id)`、`history(wrong_id, *, kind, limit, offset)`、`summary()`、`diagnose(wrong_id, payload)`。消费Task1表与Task2规则，返回持久化回执，所有写使用BEGIN IMMEDIATE。

- [ ] 写测试：首次/复习独立记录、原始错答可追溯、同键回放、换正文冲突、跨连接同时提交只有一条、写event失败整事务回滚、历史版本题集保护、多错因修改清除及乐观revision冲突。
- [ ] 运行`pytest filemate/tests/wrongbook/test_repository.py -q`观察缺失接口失败。
- [ ] objective choice/fill规则才生成确定0/1；short_answer与自查使用NULL并记录pending/self_reported；空答案只允许显式dont_know（自述不会不冒充客观错误证据）。同一次请求保存完整question快照摘要；输出判定方法、反馈、原题答案、before/after、下次时间。
- [ ] 请求键16—80且必填、回答最多10000字、note300、固定原因最多3项、标签最多5项且每项30字、可选主因必须包含于已选；诊断清除恢复unconfirmed/0置信度。
- [ ] 历史mastered=1必须先经Task4显式activate才使用新排期；未掌握旧题首次有效新答启用新规则。旧入口遇到2.0记录拒绝改用旧算法；不写两套排期。
- [ ] 所有新增测试通过后提交`feat(wrongbook): 保存幂等作答与错因历史`。

### Task 4: 排期预览、确认和撤销

**Files:** commands.py、repository.py；tests/wrongbook/test_commands.py。
**Interfaces:** `preview(wrong_id, payload)`/`confirm(wrong_id, payload, token)`消费现有data_actions；动作pause/resume/reschedule/activate/undo。预览绑定整题revision、参数、备份epoch；确认结果含review_event_id/revision/affected；撤销只恢复排期，不删除作答。

- [ ] 写测试：暂停排除队列、恢复不升级、前移后移时间、重复确认/撤销只一次、token更换动作/参数/用户拒绝、后续作答或诊断后陈旧撤销拒绝、删源后无事件/孤立任务。
- [ ] 运行`pytest filemate/tests/wrongbook/test_commands.py -q`观察缺失行为。
- [ ] 复用data_actions签发/检查/完成；事务内重读revision再更新，event记前后字段和undo_of；改期要求时区且限制当前至365天；undo不反复恢复旧revision，始终单调递增。
- [ ] 同命令通过后提交`feat(wrongbook): 增加可撤销复习排期操作`。

### Task 5: 隔离API、统计口径与调用合同

**Files:** api.py、server.py、相关证据消费者、前端types/services、README/API_SPEC/.env.example；tests/wrongbook/test_api.py。
**Interfaces:** `/wrongbook/v2/summary`、`/wrongbook/v2/{id}`、`.../{id}/attempts`、`.../{id}/events`只读；POST`/wrongbook/v2/attempts`、PATCH`.../{id}/diagnosis`、POST`.../{id}/schedule-preview|schedule-confirm`新写开关保护。固定路径先注册；复用当前租户context，无自选owner。

- [ ] 写HTTP测试：开关默认关闭写入503/读取可用、严格extra字段与长度422、他空间ID/token404或409、404/409/422分层、坏输入不暴露正文与密钥、未判定回答不进入所有确定结果消费者。
- [ ] 运行`pytest filemate/tests/wrongbook/test_api.py -q`观察缺失路由/行为。
- [ ] 接线并同步类型、API文档；旧接口响应兼容。今日总到期与候选数分开，paused排除，invalid_time单列；新旧已达标准分开命名，成长/技能/图谱排除NULL、自查及不可靠证据。新GET不调用AI。
- [ ] 定向测试与前端类型检查通过后提交`feat(wrongbook): 接入隔离接口与可信统计`。

### Task 6: 迁移恢复、全量门禁与B级交付

**Files:** tests/wrongbook/test_lifecycle.py、审计证据、交付文档/索引。
**Interfaces:** 个人签名备份覆盖新表；旧v34备份恢复得到默认legacy字段；恢复前token作废；删除来源cascade；旧/new写入关闭回滚路径可解释。

- [ ] 写测试：v34备份恢复、新表往返、原资料删除cascade、恢复后确认token不可复用、故障回滚；必要兼容修复先观察失败再实现。
- [ ] 运行`pytest filemate/tests/wrongbook -q`及相关图谱/目标/成长/技能/隐私/面试回归；生产SQLite最低版本兼容使用现有运行时夹具或如实记录未执行。
- [ ] 执行`scripts/verify.ps1`（项目默认完整门禁），保留完整输出与跳过/警告/失败；检查24个原测试哈希不变。
- [ ] 使用executing-plans规定的一次全分支独立代码审阅，重要问题以复现测试修复，不循环重审。
- [ ] 更新B级实际字段/API、验证、限制及C候选；保存提交。B结束后停下等用户验收，不推送部署、不开展C/D。

## Self-review / Execution

六项覆盖任务书5.1—5.5；每个接口由前项定义后被后项消费。复习会话/草稿/页面属C，AI属D；此处提供可用基础API而不冒充完整2.0已完成。用户已确认设计及B范围，按当前会话串行实施，不重复索取同一授权；内部计划仅细化已批准方案。
