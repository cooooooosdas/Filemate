# Knowledge Graph 2.0 B级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付课程内多资料提取、逐项审核、稳定概念融合与证据管理的真实闭环，并保留现役图谱与历史学习记录。

**Architecture:** 在现役租户SQLite内追加课程领域对象，通过独立`filemate/course_graph/`服务查询与短事务写入。旧批次及旧API保持原义；新课程图谱复用Source、分块、模型适配器、授权、确认凭据和备份机制，不自动迁移历史学习记录。B级只加入可操作的课程与审核面板，C级再重构大画布。

**Tech Stack:** 现役Vue3 / TypeScript / FastAPI / Pydantic / SQLite / Python / ECharts；不添加运行时依赖。

**Spec:** [A级设计与已确认决策](../specs/2026-10-21-knowledge-graph-2-design.md)；[用户A—E原始需求](C:/Users/胡希/.codex/attachments/3e20eecc-02f2-4775-b8c7-786e578d61f4/已粘贴的文本.txt)。

状态：2026-10-22用户明确“A级通过”，确认B前五项问题、删除边界，并已审阅本计划、同意继续。**由当前会话逐项实施中，完成后独立审阅；未完成卡保持未勾选。**

## Global Constraints

- “一次只执行一个等级。” 本计划只覆盖B；C工作台重构、D学习状态/训练联动、E图谱Agent及真人实验不实现。
- “模型输出需要结构校验。”“不允许大模型直接写入最终确认图谱。”
- “同一课程内审核后合并；不同课程分别保留，由用户建立联系。” 跨课人工联系已确定留到D，B不提供跨课合并。
- 用户确认：逐项接受/拒绝/修订，再一次确认选中结果；有效候选保留，无效项不可确认；无来源概念保留并标记；B通过且时间足够才考虑C。
- 2026-10-22补充确认：“移出课程”只撤销课程引用，保留Source和学习历史；“彻底删除资料与学习记录”沿用现役明确预览、确认及清除合同。两种动作不得混称。
- “不默认上传完整私人文档。”“不在日志中写入密钥。” 模型只读当前授权来源前20,000字符，按现役LLMClient计入真实额度。
- “重复请求避免重复写入。”“关键写操作保证原子性。” 模型调用在写事务外；确认/融合/撤销在短事务内验证来源版本与预览。
- 回滚优先用兼容新schema的版本关闭新模块；旧二进制不保证识别新迁移头，须单独验证。不得恢复旧备份覆盖上线后新学习记录；本计划不执行生产迁移或部署。
- “不删除历史数据。” 图谱编辑、融合、撤销不改写旧Source、题集、knowledge_key、作答、错题和计划；用户主动确认彻底删除或恢复备份按原隐私合同执行。
- 当前迁移头经代码核对为30；执行任务1时再次检查后追加下一版本，不修改既有迁移，不对真实库试验DDL。
- 当前代码基线`8c84e00`，在现有受管工作区保存计划；执行前复核HEAD、工作树和附属工作区。24个既有测试文件保持原哈希，不暂存它们。
- 冻结日期沿用首轮答复暂记2026-10-23，具体时刻未指定。时间不足保留稳定站及未验收候选，不降低门禁或跨级发布。

## Review Focus

1. 同一Source进入两门课、同词或C++等带符号术语：不跨课合并，规范化不吞掉有意义符号。任务1/5测试。
2. 某份资料失败或部分候选非法：其他结果仍可恢复；无效项不能借“全选”、修订或重放请求入库。任务2/3/7测试。
3. 双窗口、断网重发、取消后迟到响应、提取时原文更新：不重复计费执行、不覆盖新状态，返回明确冲突。任务3/4/6/7测试。
4. 移出课程、多来源删除、旧引用失效：不误删学习历史，不用失效来源支持关系；彻底删除后不被撤销或恢复中的运行任务复活。任务6测试。
5. 合并后出现自环/别名歧义，或撤销碰到后续依赖：保留原始ID与证据，冲突可见，不静默拆除用户后来的编辑。任务5/8测试。

## 文件与职责

| 新增路径 | 职责 |
|---|---|
| `filemate/execution/course_graph_schema.py` | 新表、约束、索引；只导出`SCHEMA` |
| `filemate/course_graph/__init__.py`、`models.py` | 类型、严格请求模型、`CourseGraphError(code, status_code)`及固定上限 |
| `filemate/course_graph/repository.py` | 课程/章节/来源归属及只读查询，统一事务和操作回执 |
| `filemate/course_graph/extraction.py`、`drafts.py` | 有界本地/模型提取与逐项校验；持久化逐来源运行状态和防迟到写入 |
| `filemate/course_graph/review.py`、`fusion.py` | 逐项审核确认；合并预览/确认、指定操作撤销/恢复 |
| `filemate/course_graph/projection.py`、`privacy.py` | 课程投影、来源支持有效性、删除影响、恢复归一化 |
| `filemate/course_graph/api.py` | 新路由工厂，使用当前请求的真实SQLiteStorage |
| `filemate/web/src/types/courseGraph.ts`、`course-graph/review-state.ts` | 与API同步的类型和可独立测试的交互状态 |
| `filemate/web/src/components/course-graph/CourseGraphPanel.vue`、`CandidateReview.vue`、`MergePreview.vue` | B级课程/资料选择、审核与合并操作；不替换全局导航 |
| `filemate/tests/course_graph/conftest.py`、`test_*.py` | 专属隔离合成数据库、服务/接口/迁移/隐私回归 |
| `filemate/web/tests/course-graph.test.mjs` | 请求重试、切换、选择、确认等状态回归 |

修改位置：`storage.py`仅注册迁移、扩展删除预览/指纹；`server.py`仅注册路由工厂；`request_credentials.py`和`llm-vault.ts`同步模型路径；`services/api.ts`、`types/env.d.ts`、`KnowledgeGraph.vue`增加新面板接线；`personal_backup.py`调用恢复归一化；`scripts/verify.ps1`与`.github/workflows/ci.yml`纳入新包；README、API_SPEC、专项执行记录及环境示例同步。

## 存储与接口决定

以下工程选择已随本计划审阅确认，不冒称用户逐一指定了表名或数值；后续如需调整须记录原因与影响。

### 数据模型

采用8张新表，均在现役身份对应的业务库内；不是另建图数据库：

| 表 | 最小字段/约束 |
|---|---|
| `kg_courses` | course_id随机稳定UUID、name、revision、archived、创建/更新时间；request_key唯一且绑定输入摘要 |
| `kg_chapters` | chapter_id稳定UUID、course_id、title、sort_order、parent_id；复合外键保证父章节同课，服务检查无环 |
| `kg_course_sources` | course_id/source_id唯一、chapter_id可空、active、revision；Source删除级联此归属，移出课程只设active=0 |
| `kg_extractions` | extraction_id、draft_id、course_id/source_id、source_revision、mode、extractor_version、request_key/input_digest、status、epoch、lease_until、payload、error_code；一行一来源；Source删除级联正文候选 |
| `kg_concepts` | concept_id稳定UUID、course_id、label、受限aliases JSON、status/revision、canonical_id可空；复合自引用限定同课；原ID不物理合并删除 |
| `kg_relations` | relation_id、course_id、from_id/to_id、受控type、status/revision；两端复合FK同课；无动态SQL字段或任意关系类型 |
| `kg_evidence` | evidence_id、course_id、source_id/source_revision、concept_id或relation_id（二选一CHECK＋各自复合FK）、legacy_node_id、excerpt、chunk_id/page/字符范围、extraction_id、status；概念引用同时承担旧键出现映射 |
| `kg_changes` | operation_id、course_id、kind、request_key/input_digest、status、受影响对象ID/版本及最小可逆元数据、时间；不存正文、引文、回答、密钥或完整模型输出 |

`kg_extractions.payload`存有界的候选/逐项决策/失败原因，按来源级联清除；不另建每个候选的表。别名最多20个/概念，各最多120字符；歧义别名可属于不同概念，只推荐候选、不强行唯一。旧键映射按course/source/revision/legacy_node_id唯一，防止同一课一个旧节点被重复映射；关系引文可多来源。引用必须绑定实际Source及版本，定位失败不补造页码；已确认引用不随显示名修订而改写。

索引覆盖课程/状态/分页、source_id/revision、关系两端、证据target/source、draft_id/创建时间、操作request_key；主键和唯一索引已有前缀则不重复创建。外键约束失败和同课程校验均须事务回滚。概念/关系不直接CASCADE到某一Source，失去来源后仍保留ID和“无有效来源”状态投影。

### 固定输入与运行上限

- 一组1–10份已导入Source；本地/模型均逐来源提取，每份最多20,000字符、80节点、120关系；客户端一次最多1个提取请求，刷新可查询已保存结果。
- 模型每次实际提取仅1次调用，`timeout=45,retry=1,max_tokens=6000`；持久认领60秒。格式/供应商失败不自动换成本地成功，不自动循环修复；用户重试失败来源仍受现役累计/并发额度控制。
- 规范化只做Unicode NFC、strip、连续空白与casefold；保留`+/#/-`等术语符号。节点label≤120、引文/定义≤1000字符；超限根数组整份标失败，合法数组里的坏项单独不可确认。
- 分页默认50、最多200、q最多160字符；按稳定ID排序。每个审核组最多2,000决策，一次确认只发布明确接受的项。融合预览2–20个同课概念；前置依赖检查最多10,000节点/30,000关系，超限明确拒绝此操作，不截断后宣布无环。
- 所有请求模型`extra='forbid', strict=True`；request_key为16–80位字母/数字/下划线/连字符；同键不同内容409。确认复用`data_actions`900秒预览凭据和事务回执，不自造第二套确认系统。

候选返回字段固定为`nodes/edges/issues/coverage`。nodes和edges保留原始顺序，各项含`item_id/kind/validation/error_codes/original/parsed/decision`；validation只允许`valid/needs_semantic_review/invalid`，非法项parsed可空但有稳定item_id，decision初始pending。coverage含`input_characters/source_truncated`。原始项只保留有界字段供用户核对，不保存不可解析的供应商全文；issues使用item_id＋固定错误码，不把原文塞进异常字符串。

### 新API合同

统一前缀`/api/knowledge-graph/courses`，响应仍为`ApiResponse`；旧`/api/knowledge-graph`合同不改。默认关闭新后端开关`FILEMATE_ENABLE_COURSE_GRAPH=0`及前端`VITE_ENABLE_COURSE_GRAPH=false`，旧图谱可单独继续运行。只有用户验收并授权发布才改变线上开关。

| 路由 | 行为 |
|---|---|
| `GET/POST /courses`；`PUT /courses/{cid}/chapters/{chapter_id}` | 分页课程；创建课程；新建/修改稳定章节（前端先生成UUID，提交带expected_revision） |
| `POST /courses/{cid}/sources` | 挂接已导入来源及章节，不产生第二上传入口 |
| `GET /courses/{cid}/sources/{sid}/remove-preview`；`POST .../remove` | 预览并确认移出课程；确认只设归属inactive，生成可撤销操作 |
| `POST /courses/{cid}/drafts`；`GET /courses/{cid}/drafts/{did}` | 一次保存分组与逐来源快照，不在此请求调用模型；跨会话读取进度与候选 |
| `POST /courses/{cid}/drafts/{did}/sources/{sid}/extract`；`POST /courses/{cid}/drafts/{did}/cancel` | 认领并执行一份提取；取消未完成来源，递增epoch、拒绝迟到写入；取消不承诺撤回供应商已消耗额度 |
| `POST /courses/{cid}/drafts/{did}/decisions`；`POST .../review-preview`；`POST .../confirm` | 保存审核、预览选中结果、一次确认；invalid不可接受，未选中项仍待审核 |
| `GET /courses/{cid}/graph`；`GET /courses/{cid}/concepts/{nid}` | 当前有效课程图及按需来源详情，明确页内关系数/全量计数；无来源节点保留但不支持推荐 |
| `POST /courses/{cid}/merges/preview`；`POST .../confirm` | 显示目标ID、来源、别名、受影响记录、自环/冲突，用户确认后逻辑融合 |
| `GET /courses/{cid}/operations`；`POST .../{oid}/preview`；`POST .../{oid}/{action}` | 分页历史；action只允许undo/restore，预览绑定受影响版本，重复操作幂等 |

表中`/courses`指上述前缀，`...`只省略同一行已写出的父路径，非匹配任意URL。新模型凭据白名单**仅**包含实际`extract`路由；GET、审核、融合、移出、取消及任意相似路径不接收浏览器模型密钥。本地提取不附加该密钥。新路由沿用当前身份、CSRF/Action检查、资源scope、异常处理；不存在或其他身份资源404，未授权模型422，版本冲突409，配额/并发使用现役错误合同，关闭503。

## Task 1: 课程边界与增量迁移

**Files:** Create `filemate/execution/course_graph_schema.py`、`filemate/course_graph/__init__.py`、`models.py`、`repository.py`、`filemate/tests/course_graph/conftest.py`、`test_storage.py`; Modify `filemate/execution/storage.py`、`scripts/verify.ps1`、`.github/workflows/ci.yml`中Ruff显式清单。

**Interfaces:** `CourseGraphRepository(storage: SQLiteStorage)`；`create_course(name: str, request_key: str) -> dict[str, Any]`；`put_chapter(course_id: str, chapter_id: str, title: str, parent_id: str | None, sort_order: int, expected_revision: int) -> dict[str, Any]`；`attach_sources(course_id: str, source_ids: list[str], chapter_id: str | None, expected_revision: int) -> dict[str, Any]`。`CourseGraphError(code: str, status_code: int=409)`统一向上抛出。

- [x] **Step 1 — 写失败测试。** `test_30_upgrade_preserves_legacy_ids_and_history`在只应用现役迁移的副本中保存Source/旧批次/作答，升级后逐行值相同；`test_reopen_is_idempotent`重复初始化不增迁移/课程；`test_cross_course_fk_and_chapter_cycle_rejected`跨课父章节/关系直接SQL也无法写入；`test_symbol_labels_not_collapsed`断言`normalize_term(' C++ ') == 'c++'`且不等于`normalize_term('C')`。conftest仅建tmp_path库并yield后close，不复用真实库。
- [x] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_storage.py -q`；预期新包/接口不存在而失败，保存输出。
- [x] **Step 3 — 最小实现。** 按上表冻结DDL与复合外键、索引；再次确认迁移头30后追加31注册。实现`normalize_term(value: str) -> str`并保留有意义符号。所有方法校验当前租户Source存在，stable UUID不取label；显式同键输入摘要检查。课程名称1–80、章节标题1–120，父章节禁止环；不自动回填旧数据课程。
- [x] **Step 4 — 验证绿灯。** 跑上述文件及`uv run pytest filemate/tests/test_storage.py filemate/tests/test_graph_storage.py -q`；要求全部通过、FK=0、integrity=ok，失败迁移不登记版本且旧数据仍可读。
- [x] **Step 5 — 提交。** 仅本任务文件；`feat(graph): 新增课程边界与增量存储`。

## Task 2: 逐项有效性与提取适配

**Files:** Create `filemate/course_graph/extraction.py`、`filemate/tests/course_graph/test_extraction.py`; Modify `models.py`。旧`study/knowledge_graph.py`的批次校验合同保持不变。

**Interfaces:** `normalize_term(value: str) -> str`定义在models；`extract_local_course(text: str) -> dict[str, Any]`复用旧规则并识别原文明示别名；`validate_candidates(payload: Any, text: str, source_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]`返回`nodes/edges/issues/coverage`；`CourseGraphProvider(client: Any).extract(text: str) -> dict[str, Any]`只调用现役`call_structured`，带有界JSON envelope Schema，再逐项严格校验。

- [x] **Step 1 — 写失败测试。** `test_partial_invalid_keeps_valid`输入一合法节点、一伪造引文节点，断言合法数1、invalid数1、后者不可接受；`test_cooccurrence_is_not_prerequisite`对“栈和队列都是线性结构。”的栈→队列前置边判invalid；`test_explicit_direction_and_negation`正确保留“栈是DFS的前置知识”方向，拒绝否定/可能句的确定边；`test_literal_aliases_only`仅原文`Stack（栈）`支持模型别名，不按常识补BFS翻译；`test_envelope_limits_and_missing_pages`检查81节点整份失败、无页码仍为null。

  核心断言示例（仅计划，未运行）：

  ```python
  payload = {"nodes": [{"label": "栈", "excerpt": "栈：后进先出。"},
                       {"label": "队列", "excerpt": "伪造引用"}], "edges": []}
  result = validate_candidates(payload, "栈：后进先出。", "synthetic-source", [])
  assert [item["validation"] for item in result["nodes"]] == ["valid", "invalid"]
  ```
- [x] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_extraction.py -q`；预期新函数未定义，保存输出。
- [x] **Step 3 — 最小实现。** 原始术语与逐字引用不可被显示名编辑覆盖；定义必须是引用内的连续原文。关系列明“规则支持/需语义核对/无效”，已知共现不支持依赖、悬空两端、反向/否定冲突不能确认；复杂但有效引文仍须用户逐项核对，不宣传机器已证明语义。根结构/超限失败；坏项保留有界原因，不输出供应商异常正文。新Prompt版本`course-graph-b1`，不让资料指令改授权。
- [x] **Step 4 — 验证绿灯。** 上述文件及`uv run pytest filemate/tests/test_knowledge_graph.py -q`全部通过。固定Provider替身仅作合成回归，单列真实模型质量待测。
- [x] **Step 5 — 提交。** `feat(graph): 增加逐项引用与关系候选校验`。

## Task 3: 多资料提取的持久状态与恢复

**Files:** Create `filemate/course_graph/drafts.py`、`filemate/tests/course_graph/test_drafts.py`; Modify `repository.py`、`models.py`。

**Interfaces:** `DraftService(storage: SQLiteStorage, provider_factory: Callable[[], Any], clock: Callable[[], datetime])`；`create_group(course_id: str, source_ids: list[str], mode: str, request_key: str) -> dict[str, Any]`；`snapshot(course_id: str, draft_id: str) -> dict[str, Any]`；`extract_source(course_id: str, draft_id: str, source_id: str, request_key: str, allow_external_model: bool) -> dict[str, Any]`；`cancel(course_id: str, draft_id: str, request_key: str) -> dict[str, Any]`。

- [x] **Step 1 — 写失败测试。** `test_one_failed_source_does_not_drop_others`三份来源只有第二份模型失败，第一份候选仍可重开；`test_two_connections_claim_once`两连接同键只调用Provider一次；`test_stale_or_cancelled_result_never_commits`阻塞Provider时更新正文/取消，再释放，断言无迟到候选；`test_reload_expired_claim_is_interrupted`模拟60秒lease过期，状态可重试、不自动启动模型；`test_completed_same_input_reuses_result`相同来源集合/内容/模式复用已完成组，不增加提取或调用AI；不同来源集合中的已完成来源可复用结果并标明缓存来源，最终确认不复制概念。
- [x] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_drafts.py -q`；预期服务缺失或认领语义不满足。
- [x] **Step 3 — 最小实现。** 分组请求只持久化至多10份Source引用，`kg_extractions`逐来源记录状态pending/running/ready/partial/failed/interrupted；同组/同键绑定完整输入摘要，相同组输入复用既有分组。不同组重复来源时可保存标明cache_origin的候选副本，不再次调用AI；概念/旧键映射仍按确认唯一约束去重。失败允许明确重试；认领事务结束后再调用Provider，完成时校验epoch、lease、Source revision和课程归属。同步HTTP逐份执行，不建后台任务系统，不持久化请求密钥；取消不能删除已确认结果。
- [x] **Step 4 — 验证绿灯。** 上述文件全部通过；用`resource_scope`及假供应商验证额度拒绝时Provider调用0次、失败记录脱敏；其他身份和其他学习页不受全局锁阻塞。
- [x] **Step 5 — 提交。** `feat(graph): 持久化多资料提取与失败恢复`。

## Task 4: 逐项审核与原子确认

**Files:** Create `filemate/course_graph/review.py`、`filemate/tests/course_graph/test_review.py`; Modify `models.py`、`repository.py`。

**Interfaces:** `ItemDecision(item_id, verdict: Literal['accept','reject','revise'], label: str | None, aliases: list[str], relation: str | None, semantic_checked: bool)`，from/to修订作为显式可选字段；`save_decisions(storage, course_id, draft_id, expected_digest: str, decisions: list[ItemDecision]) -> dict[str, Any]`；`preview_review(storage, course_id, draft_id) -> dict[str, Any]`；`confirm_review(storage, course_id, draft_id, request_key: str, confirmation_token: str, confirmed: bool) -> dict[str, Any]`。预览取服务端已保存决策，客户端不能在确认时悄悄替换选择。

- [x] **Step 1 — 写失败测试。** `test_only_accepted_items_publish`接受一个节点、拒绝一个、留一个待审核，只发布第一个；`test_invalid_or_unchecked_relation_cannot_publish`非法引用/known unsupported边即便伪造accept也拒绝，需语义核对项未勾核对也拒绝；`test_revision_and_token_prevent_stale_confirmation`另一窗口改决策或资料后旧token=409；`test_confirm_retry_is_idempotent`同键同请求只产生一份结果和审核事件；`test_edge_with_unaccepted_endpoint_is_blocked`禁止确认缺端点边。
- [x] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_review.py -q`；预期新审核接口不存在。
- [x] **Step 3 — 最小实现。** 状态pending/confirmed/rejected/revoked均持久化；显示名修订保留原术语及来源引用，人工别名标明origin=user，不能冒充原文别名。每次修订from/to/relation均用原始术语与当前Source快照重新校验，不沿用修订前valid；无效引文不能只改显示名变成有效。预览digest绑定Source、决策、course和候选版本；复用`data_actions`发证。确认事务重新校验全部选中项、写稳定概念/关系/来源映射和同一操作回执；旧批次不复制为“已审核”，不向旧API可确认批次写入新候选。
- [x] **Step 4 — 验证绿灯。** 上述文件及旧graph存储回归通过；注入写入中断，无半套节点/证据或成功回执。相同旧节点再确认不无限复制；重复原文但两个不同概念不得只按label静默融合。
- [x] **Step 5 — 提交。** `feat(graph): 实现逐项审核与确认事务`。

## Task 5: 同课程融合与指定操作撤销

**Files:** Create `filemate/course_graph/fusion.py`、`projection.py`、`filemate/tests/course_graph/test_fusion.py`; Modify `repository.py`、`models.py`。

**Interfaces:** `merge_candidates(storage, course_id: str, concept_id: str, limit: int=20) -> list[dict[str, Any]]`；`preview_merge(storage, course_id: str, concept_ids: list[str], target_id: str) -> dict[str, Any]`；`confirm_merge(storage, course_id: str, concept_ids: list[str], target_id: str, confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]`；`preview_operation(storage, course_id: str, operation_id: str, action: Literal['undo','restore']) -> dict[str, Any]`；`transition_operation(storage, course_id: str, operation_id: str, action: str, confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]`；`course_graph(storage, course_id: str, limit: int=50, offset: int=0, q: str='') -> dict[str, Any]`。合并确认重传相同concept_ids/target_id，服务端以当前对象版本重算摘要并校验预览凭据，不能仅凭token猜测未持久化的选择。

- [ ] **Step 1 — 写失败测试。** `test_same_course_merge_keeps_original_ids_and_quotes`两份资料的栈预览合并后单个可见代表、两个原始ID/引用仍在；`test_stack_queue_and_cross_course_never_auto_merge`栈/队列/优先队列不按共现自动融合，跨课合并409；`test_undo_specific_merge_preserves_quiz_and_plan`撤销一个不相关操作之后仍可撤销指定融合，旧作答/题集/计划逐行不变；`test_dependent_edit_blocks_unsafe_undo`后续编辑依赖相同对象则409，展示依赖操作，不静默覆盖；`test_merge_cycle_and_self_edge_are_explicit`检查前置环与融合自环。
- [ ] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_fusion.py -q`；预期新合并接口不存在。
- [ ] **Step 3 — 最小实现。** 相同规范化术语/已确认别名只产生建议，合并必须预览确认。合并写同课一层canonical代表关系，保留成员ID及原边；展示去重时保留全部出处，融合自环不展示为推荐边并明确计数。prerequisite/反向depends_on合成有向依赖图做有界环检查。操作最小逆变更仅保存ID/状态/版本/归属；撤销或恢复验证受影响对象指纹，有后续依赖明确409。移出来源/隐私删除后的旧引用不能由恢复重新造出。
- [ ] **Step 4 — 验证绿灯。** 本文件通过；两连接相同确认只生成一个operation；跨课程投影0泄漏。B投影只返回知识关系/来源与尚未评测提示，不生成新掌握率或冒充D学习分析。
- [ ] **Step 5 — 提交。** `feat(graph): 支持课程内融合与可追溯撤销`。

## Task 6: 来源生命周期、备份与隐私

**Files:** Create `filemate/course_graph/privacy.py`、`filemate/tests/course_graph/test_privacy.py`; Modify `storage.py`删除预览/指纹、`personal_backup.py`恢复接线；任务5的operation接入移出课程。

**Interfaces:** `source_impact(storage, source_id: str) -> dict[str, Any]`返回新增行数、受影响概念/关系ID与保留/失去支持数；`source_revision_fragment(storage, source_id: str) -> dict[str, Any]`供现役删除指纹调用；`preview_remove_source(storage, course_id: str, source_id: str) -> dict[str, Any]`；`remove_source(storage, course_id: str, source_id: str, confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]`；`normalize_restored_course_graph(conn: sqlite3.Connection) -> None`。

- [ ] **Step 1 — 写失败测试。** `test_remove_course_source_preserves_learning_history`移出后Source/原作答/错题/计划逐行保留；`test_other_source_support_survives_purge`彻底删除一个来源后另一出处继续有效，概念保留；`test_last_support_is_unavailable_not_deleted`最后来源移出或删除后节点标无来源、关系不用于当前依赖；`test_updated_text_or_chunks_invalidates_all_course_mappings`同Source两课程都按revision失效，不影响其他来源；`test_backup_30_and_new_roundtrip`旧备份可读、新备份能还原，运行中的extract状态归一为interrupted且旧epoch不能完成；`test_delete_token_covers_graph_changes`预览后改图谱，旧删除凭据409。
- [ ] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_privacy.py -q`；预期新影响计数或保留行为未实现。
- [ ] **Step 3 — 最小实现。** 引用有效性实时检查归属active＋Source revision＋审核状态，不靠可能漏触发的更新钩子。扩展现役彻底删除预览、摘要和事务影响，FK清理候选/引用但保留课程概念；不另改旧表CASCADE合同。新图谱日志不存被删除正文/答案；Source当前正文与revision不是历史原文恢复库。复用个人备份动态表枚举；归一化extract租约/epoch并清除失效确认，不重放AI/旧操作。
- [ ] **Step 4 — 验证绿灯。** 上述文件及`uv run pytest filemate/tests/test_p1_privacy_boundary.py filemate/tests/test_p1_personal_backup.py filemate/tests/test_backup.py -q`通过。备份在副本演练，失败不覆盖现有数据；账户/空间删除不留新库或侧写文件。
- [ ] **Step 5 — 提交。** `feat(graph): 联通来源生命周期与个人备份`。

## Task 7: HTTP合同、身份、密钥与失败恢复

**Files:** Create `filemate/course_graph/api.py`、`filemate/tests/course_graph/test_api.py`; Modify `server.py`、`filemate/llm_client/request_credentials.py`、`filemate/web/src/services/llm-vault.ts`、`filemate/docs/API_SPEC.md`、`.env.example`、`deploy/.env.production.example`；VITE构建变量的说明沿用根`.env.example`，不假定已有web专用环境示例。

**Interfaces:** `create_router(storage_provider: Callable[[], SQLiteStorage]) -> APIRouter`；server提供`_course_graph_storage() -> SQLiteStorage`，按`_tenant_context`选当前真实storage，不能在注册时缓存一个用户。请求DTO和路由完整实现上表；GET图谱不返回整份候选payload，详情按需加载。

- [ ] **Step 1 — 写失败测试。** `test_anonymous_and_account_course_isolation`两个匿名/登录身份交叉读写均404；`test_model_consent_and_browser_key_context`模型未授权422，传入的合成假密钥仅当前extract请求可读、退出后清空；`test_non_model_routes_and_similar_paths_never_receive_key`GET/confirm/merge/恶意后缀不在白名单；`test_switch_off_preserves_legacy_graph`新模块503、旧图谱200；`test_http_retry_and_parameter_boundaries`同键同体幂等、异体409、11来源/非法relation/多余字段422；`test_provider_error_redacts_and_preserves_graph`供应商异常不泄漏假密钥/正文、不覆盖确认图。
- [ ] **Step 2 — 验证红灯。** `uv run pytest filemate/tests/course_graph/test_api.py -q`；预期新路径404或合同缺失，不把失败误报为已部署结果。
- [ ] **Step 3 — 最小实现。** 同步前后端白名单精确正则，前端只有mode=llm时才注入key；LLMClient在请求resource_scope内调用，保留现役配额/usage/同源限制。错误码映射CourseGraphError，外部异常只写类型/固定码；不把模型异常原文返回页面。API_SPEC逐路由写请求/响应、来源与确认失效、分页、开关和旧合同边界。
- [ ] **Step 4 — 验证绿灯。** 上述API测试、`uv run pytest filemate/tests/test_graph_api.py -q`、`npm --prefix filemate/web test`通过；确认旧页面不需要新开关/课程即可工作。没有改动原24测试文件。
- [ ] **Step 5 — 提交。** `feat(graph): 接通课程图谱接口与授权边界`。

## Task 8: B级真实审核界面

**Files:** Create 前述3个Vue组件、`types/courseGraph.ts`、`course-graph/review-state.ts`、`web/tests/course-graph.test.mjs`; Modify `KnowledgeGraph.vue`、`services/api.ts`、`types/env.d.ts`。

**Interfaces:** API函数统一在`services/api.ts`，分别以`listGraphCourses/createGraphCourse/putGraphChapter/attachGraphSources/createCourseDraft/getCourseDraft/extractCourseSource/cancelCourseDraft/saveCourseDecisions/previewCourseReview/confirmCourseReview/getCourseGraph/getCourseConcept/previewCourseMerge/confirmCourseMerge/getCourseOperations/previewCourseOperation/changeCourseOperation/previewCourseSourceRemoval/removeCourseSource`对应路由。`createCourseReviewFlow(api)`提供`loadCourse/selectSources/extract/saveDecisions/preview/confirm/cancel`，state包含courseId、draftId、epoch、busy、error、pendingCommand；重试沿用request_key。

- [ ] **Step 1 — 写失败测试。** Node测试`late_course_result_does_not_replace_selection`、`confirm_disabled_for_invalid_or_unsaved_decisions`、`retry_reuses_key_and_stale_digest_requires_preview`、`cancel_stops_next_source_and_keeps_ready_results`、`new_course_panel_off_keeps_legacy_route`；前后端均检查来源文件名/引用按文本渲染、不执行HTML。测试每项断言对应状态，不用只检查函数源码字符串代替行为。
- [ ] **Step 2 — 验证红灯。** `node --test filemate/web/tests/course-graph.test.mjs`预期新状态模块缺失；保存输出。
- [ ] **Step 3 — 最小界面实现。** 在现有图谱页加入开关控制的“课程图谱”面板，复用已有资料选择，不新增上传入口。课程/章节→多资料提取→逐项核对→确认→合并→来源/历史；有效和无效项分组，默认不全选，确认有数量、出处和语义核对。dirty切换/退出先提示；进度逐来源显示，失败可重试，刷新恢复已保存草稿。原无衬线、SVG、17px正文、44px操作、四主题和键盘焦点；C级再改大布局。
- [ ] **Step 4 — 验证绿灯。** `node --test filemate/web/tests/course-graph.test.mjs`、`npm --prefix filemate/web test`、`npm --prefix filemate/web run build`及`npm --prefix filemate/web run check:bundle`通过。实际浏览器验证新面板和旧图谱均可进入，取消后不会继续下一份提取。
- [ ] **Step 5 — 提交。** `feat(graph): 接入课程资料审核与融合面板`。

## Task 9: 整体回归、真实模型与B级交付

**Files:** Create `scripts/acceptance/course_graph_fixture.py`、`docs/KNOWLEDGE_GRAPH_2_0_B_DELIVERY.md`; Modify README、API_SPEC、专项执行记录及必要的验收清单；原始截图/数据库/日志留本轮`_working`，仅脱敏摘要与必要截图入docs。

**Interfaces:** `course_graph_fixture.py --data-root <本次新建绝对目录>`只准备原创TXT、隔离数据根及测试账号，拒绝既有目录，不修改真实用户库或输出密钥/cookie。复用现有个人导出/恢复与Playwright；不新增生产演示假数据路径。

- [ ] **Step 1 — 准备真实操作断言。** 浏览器流程必须看到数据结构两份原创TXT、Python第二课程隔离、逐项拒绝/修订、两份栈融合后引用仍各可打开、刷新持久、指定合并撤销/恢复、移出来源保留学习历史。并发/迟到/供应商失败/断网注入后可恢复；直接SQL和真实HTTP证据互相核对。失败保留原输出，不通过改产品结果来迎合固定节点数。
- [ ] **Step 2 — 执行全量门禁。** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`；要求Ruff/后端非e2e/前端/类型/构建/体积均通过，记录新的实际数量与跳过原因。没有新增疑点不重复跑全量。
- [ ] **Step 3 — 浏览器与迁移恢复验证。** 在隔离账户实际完成Step1及导出、移出和副本恢复；测1920×1080、1366×768、1024×768、1180×820、390×844、空态/错误/长文件名。迁移副本从30升级、重复执行、新旧数据可读、FK=0、失败恢复；新模块开关关闭后旧资料/练习/图谱可用。只停本次启动的服务，保留失败现场与最终截图。
- [ ] **Step 4 — 真实模型与独立审阅。** 使用已授权原创资料及可用配置实际调用新链，记录供应商/模型、范围、逐项校验、人工核对与真实usage（未提供则未知），不提交密钥。不可用则明确“模型链待验证”，不拿替身结果冒充真实模型通过。对完整B分支作一次独立审阅，修复重要问题并定向复验；没有合格模型证据不得宣称完整模型提取质量已验收。
- [ ] **Step 5 — 保存交付并停止。** 补B级8项报告、迁移/恢复证据、README与专项账本，显式提交`docs(graph): 记录B级闭环验收与未验证边界`；**等待B级通过，不推送部署、不进入C**。若只完成部分卡，明确“B未完成”，不能因比赛截止提前勾选其余任务。

## 验收与计划自审

覆盖映射：B1单/多资料、课程/章节、历史→任务1/3/8；B2结构化模型/定义/别名/引用→任务2/3/7/9；B3候选融合/预览/撤销→任务5；B4逐项状态/编辑/审核→任务4/8；B5持久化/去重/隔离/删除→任务1/3/6/7/9。全部B任务才构成本级候选，任何单卡通过不算B整体通过。

执行验证时为每项记录命令、退出码、通过/失败/跳过、是否合成、截图及未测试范围。A级1312/140/39/浏览器7组是历史基线，不复制为本阶段新结果。B暂无真实运行截图或通过数量，本文中的测试名称与预期均是待执行计划。

自审已核对：9项任务覆盖B1—B5；声明的接口在所属任务定义；每项Review Focus有对应失败测试；先写红灯、保存失败、最小实现、绿灯再提交；Source当前正文/版本指纹、移出与彻底删除、模型密钥白名单、恢复中的运行状态均有明确合同。稳定ID不被标签替换，候选、课程图谱与旧学习事实不建立平行“掌握度真相”。

**按executing-plans逐卡实施；不重复询问已确认的五项方向、删除边界或执行方式。全部完成后仍须等待用户明确“B级通过”。**
