# Knowledge Graph 2.0 C级知识工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付关系图优先、章节逐步展开、来源可定位且手机可读的课程知识工作台，完整保留B级审核与恢复能力。

**Architecture:** 在schema31课程图谱上新增一致快照的只读投影，Vue继续使用ECharts及现有路由／四主题。将纯浏览状态、异步请求、图布局和B管理面板分开；不复制学习记录、不调用模型重建画布。每次写操作仍由B服务负责，C只在成功后刷新读快照。

**Tech Stack:** 现役Python / SQLite / FastAPI / Vue3 / TypeScript / ECharts / node:test；不新增运行时依赖。

**Spec:** [已确认C级设计](../specs/2026-10-22-knowledge-workspace-c-design.md)。读取本计划前先读设计；[B级交付](../../KNOWLEDGE_GRAPH_2_0_B_DELIVERY.md)与[现役API](../../../filemate/docs/API_SPEC.md)是兼容基线。

状态：用户在设计交付后回复“继续”，据此记录设计确认。用户已确认本计划并授权从任务1开始；按八卡连续实施，不部署。沿用B的当前会话逐卡实施、完成后一次独立审阅方式，不重复询问执行方法。工作区为`C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`，分支`codex/knowledge-graph-2-audit`，计划前HEAD `6997788`。

## Global Constraints

- 一次只做C；A/B已通过，C交付后仍等待“C级通过”，不提前做D/E或上线。
- “首次打开课程默认关系图，之后记住该课程上次使用的视图。” 手机首次采用outline，不读取桌面graph偏好。
- “单次画布最多100概念、300条去重后的关系”；概念／搜索列表每页50，参数上限200，offset上限1000000，q上限160字符；输入停止300ms或Enter查询。
- “返回原句前后各最多2000字符及分开的before/quote/after文本”；来源当前版本与保存位置必须再次验证。
- “graph_digest绑定当前课程的章节／归属／概念／关系／证据状态及有效来源版本”；不单凭course.revision。并行读digest不一致仅自动重新读取一次。
- “没有课程只显示一个主动作‘建立课程’”；无资料使用现有/import，不新增上传组件；保留旧资料图谱及旧深链。
- “学习证据”区分资料与个人记录；新课程显示“尚未建立学习记录关联”，不把legacy_node_id提示当已确认映射，不填掌握分数或假练习／路径动作。
- FILEMATE_ENABLE_COURSE_GRAPH / VITE_ENABLE_COURSE_GRAPH缺省仍为0/false；只读接口不接收模型密钥，不修改B请求键／确认token／取消epoch合同。
- 沿用原无衬线、蓝色LOGO、四主题和SVG；正文17–20px、辅助至少15px、交互目标至少44px；文本4.5:1，控件与焦点3:1。中心不足480px收课程栏，避免硬塞三栏。
- 1920×1080、1366×768、1024×768、1180×820、390×844均需真实浏览器证据；减少动画静态，卸载清理请求／Observer／ECharts。
- schema31不修改；不计划新业务表。若性能实测证明需索引，只追加下一实际迁移，并补副本升级、重复初始化、备份恢复验证及文档，不用旧备份覆盖新学习记录。
- 原24份用户测试文件以`D:/FileMate-Project/_working/frontend-depth-20261018/preserved-tests.json`为哈希基线；不修改、不暂存。临时DB、日志、会话放工作区_working，不提交密钥、真实资料或数据库。
- 各卡先运行有针对性的RED→GREEN验证；最终执行scripts/verify.ps1 -IsolateFrontend。文档规划阶段不重复产品全量测试，不把B数量当C结果。

## Review Focus

1. 同概念跨章节／融合后多来源：计数按代表ID去重、原ID可定位，失效来源不参与分组／连线。任务1/2覆盖。
2. 未加载的跨页节点和C/C#/C++/A-B/AB：全课程搜索可达，不能仅搜画布或吞符号；类型筛选不抹掉孤立节点。任务1/2/5覆盖。
3. 同名概念在另一课程、登录切换、迟到详情／备份恢复：不拼接异课程／异身份／异digest数据，不重放写请求。任务3/4/5/7覆盖。
4. 重复引文、Unicode补充字符、来源更新／移出／删除：定位按保存范围核对、无效时明确失败，不使用缓存伪造原文。任务3/7覆盖。
5. 10000节点、超多章节、长文件名、午夜主题与窄屏：有界查询与布局、所有节点可通过列表到达、主动作和引用可读，无模态焦点逃逸。任务1/2/6/7/8覆盖。

---

## 文件职责与冻结的跨卡合同

以下路径均为仓库相对路径。新增文件在对应任务时才创建；不得为计划预建产品代码。

- `filemate/course_graph/workspace_models.py`：C查询参数与响应TypedDict，和B models分开。
- `workspace_snapshot.py`：单读快照、批量代表解析／引用有效性／digest／章节树和分组。
- `workspace_query.py`：导航与搜索列表；`workspace_canvas.py`：有界画布／详情；`workspace_source.py`：引用上下文。
- `workspace_api.py`：只读路由，注册到既有课程router；B写入handler保持原义。
- `filemate/web/src/types/courseWorkspace.ts`：C共享响应／状态类型；`services/api.ts`：只读调用和不读取密钥的空间scope查询。
- `course-graph/browse-state.ts`：URL／偏好纯函数；`workspace-state.ts`：带代次／digest的只读控制器；`workspace-layout.ts`：确定性坐标／箭头映射。
- `components/course-graph/CourseWorkspace.vue`：工作台壳；`CourseNavigation.vue`：目录／筛选；`CourseCanvas.vue`：ECharts；`CourseOutline.vue`：分页大纲；`CourseEvidence.vue`：来源／个人记录空态；`CourseSourcePanel.vue`：定位原文；`CourseManager.vue`：B面板适配。
- `styles/course-workspace.css`：仅工作台样式。现有`CourseGraphPanel.vue`、`KnowledgeGraph.vue`仅做必要接线，不重写全站。

### 查询与响应

工程细节在此固定，未改变设计目标。R=`/api/knowledge-graph/courses`。所有C响应带同一格式`graph_digest`（64位hex）、`course_id`；返回仍包在现役`{success,data,error}`。读事务内先核验当前课程，foreign ID 404。

Python `@dataclass(frozen=True) WorkspaceFilter(chapter_id: str|None=None, source_id: str|None=None, relations: tuple[str,...]|None=None)`；chapter_id可为真实章节ID或保留值`@unassigned`／`@no-source`，后两者仅作筛选，不写DB。relations=None表示全部，空tuple表示不显示连线，非空只能为B六类型；HTTP对空tuple编码hide_relations=true，不能与relation同时传入，冲突422；未传hide_relations且无relation时为全部。无效章节／来源404。现役API层未知query或非法枚举422，不把额外参数直接透传SQL。

Python响应TypedDict与TS接口同名，字段以此为准：

- `WorkspaceNode`：id,label,aliases(label/origin),chapter_ids[],source_count,source_status(available/no_valid_source),member_count；轻量节点不含全文引文或能力分。
- `WorkspaceGroup`：id（真实chapter_id或两系统值）,parent_id,title,sort_order,concept_count,child_count。概念去重计数；source无章节进入@unassigned，无有效引用进入@no-source；父子重叠不相加。
- `WorkspaceRelation`：id,from,to,relation,relation_ids[],evidence_count。按代表from/to/type去重，禁止自环与失效依据，箭头原义保留。
- `WorkspaceNavigation`：course_id,name,graph_digest,groups[],group_total,group_offset,group_limit,sources[](source_id,original_name,chapter_id,active),source_total,source_offset,source_limit,total_concepts。
- `WorkspaceConceptPage`：course_id,graph_digest,items[](WorkspaceNode加matched_label),total,limit,offset；非空q搜索当前filter范围，前端的全课程搜索传空章节／来源并保留当前范围在本地用于提示。
- `WorkspaceCanvas`：course_id,graph_digest,mode(groups/concepts),nodes[],edges[],groups[],group_edges[](from_group,to_group,relation_count),total_concepts,total_edges,truncated,node_has_more,edge_has_more,group_total,group_offset,group_limit,requested_id,resolved_id。组汇总不是知识断言；mode=groups时概念数组可空。
- `WorkspaceDetail`：course_id,graph_digest,requested_id,resolved_id,node(WorkspaceNode),source_refs[](evidence_id,source_id,original_name,excerpt,page,chunk_id),total_refs,limit,offset。不带merge_candidates，融合仍用B详情。
- `WorkspaceCitation`：course_id,graph_digest,requested_id,resolved_id,evidence_id,source_id,original_name,page,chunk_id,before,quote,after；动态文本不作为HTML渲染。

导航默认每次200组／50来源，可用group_offset/source_offset分别续页，均最大200，offset上限1000000；章节树只渲染已读节点，缺父章按需取该章路径，不猜测根，单章展开按稳定ID分页。为此`GET /workspace`可带parent_id：缺省全部分页；指定时只列该父章直接子章，虚拟组只在根。`GET /workspace/chapter-path/{chapter_id}`返回真实祖先路径，异常树409 chapter_structure_invalid。

接口：GET `/{cid}/workspace`（上述导航分页）；GET `/{cid}/canvas`（filter+focus+limit=100+group_limit=20［1..20］/group_offset=0）；GET `/{cid}/concepts-page`（filter+q+limit/offset）；GET `/{cid}/workspace/concepts/{nid}`（limit/offset分页引文）；GET `/{cid}/concepts/{nid}/source-evidence/{eid}`（无任意范围参数）。C专用详情额外endpoint用于一致digest与有界引用，不改变B详情，六个只读路径均需API文档和调用方同步。

Focus始终占一个位置，只取该点及一跳邻居（按ID稳定排序）；未指定focus时展示所选章节前100概念；没有过滤且多章或超过100概念时先展示最多20个导航组并提供更多组入口，不将多个组伪装成概念。子图最多300条关系，返回全部计数／截断标识。所有未上画布节点通过分页大纲可达，不后台拼满全图。

## Task 1: 一致快照、章节归属与概念检索

**Files:** Create `filemate/course_graph/workspace_models.py`, `workspace_snapshot.py`, `workspace_query.py`; Test `filemate/tests/course_graph/test_workspace_query.py`。

**Interfaces:**
- Consumes: `SQLiteStorage.read_snapshot()`、`get_source_revision()`、B的`require_course`；批量读取schema31表，不对每个节点再开snapshot。
- Produces: `load_workspace_snapshot(storage: SQLiteStorage, course_id: str) -> CourseWorkspaceSnapshot`（对象保留只读规范化行／指纹，不持有退出后的连接）；`get_workspace(storage, course_id, *, parent_id=None, group_limit=200, group_offset=0, source_limit=50, source_offset=0) -> WorkspaceNavigation`；`get_chapter_path(storage, course_id, chapter_id) -> dict`（course_id/graph_digest/items: WorkspaceGroup[]）；`list_workspace_concepts(storage, course_id, *, filters: WorkspaceFilter, q='', limit=50, offset=0) -> WorkspaceConceptPage`。

- [x] **Step 1: 写查询失败用例。** 复用course_context与B的draft/publish测试工具，确认两份资料后融合，并把来源分别放父章／子章；测试名与断言如下，fixture准备不直接伪造已审核质量结论。

```python
def test_groups_follow_current_sources_not_label(workspace_case):
    nav = get_workspace(workspace_case.store, workspace_case.cid)
    assert nav['total_concepts'] == 3  # 双源栈融合一次，另有队列与DFS
    assert len({n['id'] for n in workspace_case.all_nodes()}) == 3
    assert workspace_case.stack_in_both_chapters(nav)

def test_symbol_search_and_snapshot_digest(workspace_case):
    assert workspace_case.exact_matches('C#') == ['C#']
    before = get_workspace(workspace_case.store, workspace_case.cid)['graph_digest']
    workspace_case.revise_source_text()
    assert get_workspace(workspace_case.store, workspace_case.cid)['graph_digest'] != before
```

另写`test_parent_count_deduplicates_merged_members`、`test_alias_and_member_name_search_survives_merge`、`test_no_source_and_unassigned_are_distinct`、`test_navigation_paging_and_chapter_path`、`test_invalid_chapter_cycle_is_bounded`、`test_digest_changes_on_review_merge_undo_even_without_course_revision`，断言去重、分页稳定、树异常409、course.revision不变时digest仍变。

- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_workspace_query.py -q`；应因新接口不存在失败，不能是环境／fixture错误。
- [x] **Step 3: 实现上述签名与TypedDict。** 批量读概念／关系／证据与章节归属，代表解析在同课程内；来源指纹同次请求缓存；digest按排序后的原始状态＋指纹计算，含引文位置／内容／别名修订，不含筛选或当前时间。q按现役大小写不敏感字面子串匹配，不剥离+/#/-；搜索C可含C#，不宣称精确搜索，测试exact_matches对匹配词精确核对。对大表不调用B的N+1节点投影。
- [x] **Step 4: 跑GREEN。** 同Step2并加入`test_storage.py test_final_regressions.py`；新查询与B存储／身份回归无失败，FK=0，无写入副作用。
- [x] **Step 5: 提交。** 仅暂存本卡文件，`feat(graph): 增加课程工作台一致快照与章节检索`。

## Task 2: 有界章节画布、跨页邻域与一致详情

**Files:** Create `filemate/course_graph/workspace_canvas.py`; Test `filemate/tests/course_graph/test_workspace_canvas.py`；必要时修改Task1模型／只读helper，不改变B projection。

**Interfaces:**
- Consumes: `load_workspace_snapshot`、`WorkspaceFilter`及Task1响应类型。
- Produces: `get_workspace_canvas(storage, course_id, *, filters: WorkspaceFilter, focus: str|None=None, limit=100, group_limit=20, group_offset=0) -> WorkspaceCanvas`；`get_workspace_detail(storage, course_id, concept_id, *, limit=50, offset=0) -> WorkspaceDetail`。

- [x] **Step 1: 写有界行为失败用例。**

```python
def test_focus_outside_first_page_is_kept(large_workspace):
    page = get_workspace_canvas(large_workspace.store, large_workspace.cid,
        filters=WorkspaceFilter(), focus=large_workspace.last_id, limit=100)
    assert page['resolved_id'] == large_workspace.last_id
    assert large_workspace.last_id in {n['id'] for n in page['nodes']}
    assert len(page['nodes']) <= 100 and len(page['edges']) <= 300
    assert page['truncated'] is True
```

另写`test_groups_are_not_semantic_nodes`、`test_cross_group_summary_requires_valid_evidence`、`test_relation_filter_retains_isolated_nodes`、`test_zero_relation_selection_hides_edges_only`、`test_group_canvas_pages_twenty_at_a_time`、`test_merged_original_id_resolves_representative`、`test_focus_outside_filter_returns_conflict`、`test_no_source_relations_are_suppressed`、`test_detail_refs_are_paged`。明确默认groups模式、300边上限、system组和10000节点分页访问，不把只看第一页当全图。

- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_workspace_canvas.py -q`，新查询缺失失败。
- [x] **Step 3: 实现签名。** 用代表成员索引和有效证据批量构造邻接、章节计数和group_edges；去重边前先核验两端支持及关系引文。所有超限返回node_has_more/edge_has_more，不无声截断；source_id与chapter_id取交集，focus过滤冲突409 focus_outside_filter。detail不因搜索／画布分页丢掉原ID，返回50引用和total_refs；不读取旧作答／画像。
- [x] **Step 4: 跑GREEN。** `uv run pytest filemate/tests/course_graph/test_workspace_query.py filemate/tests/course_graph/test_workspace_canvas.py filemate/tests/course_graph/test_fusion.py -q`，无失败；大夹具证明预算内返回且余下节点列表可达。
- [x] **Step 5: 提交。** `feat(graph): 接通有界章节画布与跨页概念邻域`。

## Task 3: 原文定位、HTTP权限与共享合同

**Files:** Create `filemate/course_graph/workspace_source.py`, `workspace_api.py`; Modify `filemate/course_graph/api.py`, `filemate/docs/API_SPEC.md`, `filemate/web/src/services/api.ts`; Create `filemate/web/src/types/courseWorkspace.ts`; Test `filemate/tests/course_graph/test_workspace_api.py`, `test_workspace_source.py`。

**Interfaces:**
- Consumes: Task1/2服务、B当前租户Store依赖和CourseRoute。
- Produces: `get_workspace_citation(storage, course_id, concept_id, evidence_id) -> WorkspaceCitation`；`register_workspace_routes(router: APIRouter, storage_provider: Callable[[], SQLiteStorage]) -> None`注册六路径及同开关；TS响应字段与上方同名类型一致。`getCourseWorkspace(cid, options, signal?)`、`getCourseCanvas(cid, filters, focus?, groupOffset=0, signal?)`、`getCourseChapterPath(cid, chapterId, signal?)`、`getCourseConceptPage(cid, options, signal?)`、`getCourseWorkspaceDetail(cid, nid, offset=0, signal?)`、`getCourseCitation(cid,nid,eid,signal?)`均返回对应Promise，不读密钥；`getCourseBrowserScope(): Promise<string|null>`只读publicLLMStatus的64hex credential_scope，失败返回null，不打开／读取浏览器密钥库。

- [x] **Step 1: 写引用和边界失败用例。**

```python
def test_unicode_duplicate_quote_uses_saved_range(citation_case):
    result = get_workspace_citation(citation_case.store, citation_case.cid,
        citation_case.node_id, citation_case.second_quote_evidence_id)
    assert result['quote'] == citation_case.quote
    assert result['before'].endswith(citation_case.unique_before_second)
    assert len(result['before']) <= 2000 and len(result['after']) <= 2000
```

另写`test_source_revision_change_is_not_fuzzy_repaired`（409 citation_unavailable）、`test_removed_source_is_unavailable`（409）、`test_deleted_or_foreign_evidence_is_404`、`test_merged_member_reference_is_valid`、`test_read_routes_tenant_isolation_and_flag_off`、`test_strict_filters_and_limits`（重复未知relation／多余参数422）、`test_read_routes_do_not_accept_model_credentials`、`test_old_b_graph_contract_unchanged`。真实租户fixture沿用既有test_api.py，禁止把同一个store用于两身份测试。
- [x] **Step 2: 跑RED。** `uv run pytest filemate/tests/course_graph/test_workspace_source.py filemate/tests/course_graph/test_workspace_api.py -q`，预期新路径404／函数缺失，非注册全局失败。
- [x] **Step 3: 实现引用与路由签名。** 先验证当前课程、已确认概念／成员及evidence归属，再核对active会员、source_revision、raw_text[start:end]==excerpt；不把失效引文藏成成功。Python切分Unicode上下文，page/chunk仅用真实字段，不按内容推断页码。query用受控类型与显式禁止extra，复用B错误包、开关、no-store，SQLite错误503，关闭默认不泄露私有数据。
- [x] **Step 4: 同步API_SPEC、TS类型及services。** 用URLSearchParams.append处理重复relation，其他ID路径encodeURIComponent，读timeout=15000，AbortSignal可传。HTTP请求不夹带写入header／allow_external_model；只允许现役模型白名单处理密钥。文档把上述六路径记为实施后状态，保留B历史快照标题。
- [x] **Step 5: 跑GREEN。** 上述用例＋原`test_api.py`、`test_privacy.py`；`npm --prefix filemate/web run build`及原前端测试无类型回归。断言无新业务表，schema31稳定；若另有迁移须按Global Constraints补验。
- [x] **Step 6: 提交。** `feat(graph): 增加工作台只读API与准确引用定位`。

## Task 4: URL、逐课程偏好与身份隔离

**Files:** Create `filemate/web/src/course-graph/browse-state.ts`; Modify `types/courseWorkspace.ts`; Test `filemate/web/tests/course-workspace-browse.test.mjs`。

**Interfaces:**
- Consumes: Task3的opaque scope；Storage仅getItem/setItem/removeItem三方法，注入以便node:test。
- Produces: `resolveGraphScope(query: Record<string,unknown>, enabled: boolean): 'source'|'course'`；`readCourseBrowse(query, saved: CoursePreference|null, mobile: boolean): CourseBrowse`；`courseBrowseQuery(state: CourseBrowse): Record<string,string|string[]>`；`createCoursePreferences(storage: PreferenceStorage, scope: string|null)`返回`get(courseId,mobile)`, `set(courseId,mobile,view)`, `lastCourse()`, `forget(courseId)`, `clearMemory()`。CourseBrowse字段scope/courseId/view/nodeId/chapterId/sourceId/relations/notice；view=graph|outline|evidence，relations为RelationKind[]|null（null全部、[]不显示连线）。CoursePreference={desktop?: WorkspaceView,mobile?: WorkspaceView}；PreferenceStorage精确定义三项同名Storage方法。TS WorkspaceFilter={chapter_id?:string,source_id?:string,relations?:RelationKind[]|null}，服务层将[]转换hide_relations=true，不发空字符串类型；URL也允许hide_relations，和relation互斥。所有page/digest/node类型定义均使用Task3统一的courseWorkspace.ts，不在组件另造近似字段。

- [x] **Step 1: 写纯状态失败用例。**

```javascript
test('url_wins_and_mobile_does_not_reuse_desktop_graph', () => {
  assert.equal(readCourseBrowse({}, { desktop: 'graph' }, true).view, 'outline')
  assert.equal(readCourseBrowse({ view: 'evidence' }, { desktop: 'graph' }, false).view, 'evidence')
  assert.equal(resolveGraphScope({ node: 'old-id' }, true), 'source')
  assert.equal(resolveGraphScope({ graph_scope: 'course', node: 'new-id' }, true), 'course')
  assert.equal(resolveGraphScope({}, false), 'source')
})
```

另写`storage_denied_and_corrupt_fall_back_to_memory`、`two_scopes_do_not_share_courses`、`query_round_trip_excludes_private_text`、`missing_course_clears_preference_without_selecting_another`。无scope仅页内记忆；localStorage不含引文／文件名／密钥。
- [x] **Step 2: 跑RED。** 在filemate/web执行`node --test tests/course-workspace-browse.test.mjs`，预期模块缺失。
- [x] **Step 3: 实现签名。** key=`filemate-course-workspace-v1:{scope}`，最多100课程偏好且只存course_id／desktop/mobile view和最近course_id。显式graph_scope优先；无scope参数但有旧source/node则source；其余enabled时course。显式非法view回安全默认并在CourseBrowse.notice说明，不接受数组伪装标量。关系筛选加入URL白名单，q不入URL；未知／非法参数仅产生安全回退notice，不触发写操作。
- [x] **Step 4: 跑GREEN。** 本卡node:test与现有`course-graph.test.mjs`通过；URL往返、隐私和禁存储断言全部成立。
- [x] **Step 5: 提交。** `feat(graph): 保存分空间浏览偏好并兼容旧图谱深链`。

## Task 5: 读快照控制器与迟到／故障恢复

**Files:** Create `filemate/web/src/course-graph/workspace-state.ts`; Modify `types/courseWorkspace.ts`; Test `filemate/web/tests/course-workspace-state.test.mjs`。

**Interfaces:**
- Consumes: Task3 API函数经`WorkspaceApi`注入，Task4 CourseBrowse；状态由Vue调用方用reactive/shallowRef观察，控制器本身可在node:test运行。
- Produces: `createCourseWorkspaceController(api: WorkspaceApi)`返回`state`, `open(browse)`, `selectNode(id)`, `openCitation(eid)`, `closeCitation()`, `search(q)`, `selectSearchResult(item)`, `setView(view)`, `setFilters(filters)`, `refresh()`, `invalidateAfterMutation()`, `resetIdentity(scope)`, `dispose()`。state至少含browse/navigation/canvas/detail/citation/searchPage/loading/error/stale/notice/generation；大快照按替换更新，不深层修改。

- [x] **Step 1: 写代次和一致性失败用例。**

```javascript
test('late_old_course_and_digest_mismatch_cannot_mix', async () => {
  const old = deferred()
  const api = workspaceApi({ oldCourse: old.promise, digests: ['a', 'b', 'c', 'd'] })
  const controller = createCourseWorkspaceController(api)
  const pending = controller.open(browse('old'))
  await controller.open(browse('new'))
  old.resolve(oldSnapshot); await pending
  assert.equal(controller.state.browse.courseId, 'new')
  assert.equal(api.automaticRereads, 1)
  assert.equal(controller.state.stale, true)
})
```

另写`search_locates_unloaded_node_and_clears_only_conflicting_filters`、`search_debounce_enter_cancels_pending_timer`、`network_error_keeps_only_same_identity_snapshot`、`identity_reset_clears_detail_and_aborts_reads`、`revoked_node_clears_selection`、`mutation_refresh_failure_never_replays_write`；用可控promise和时钟，不硬等300ms。WorkspaceApi以Task3六个读方法和浏览scope方法组成；测试注入同名方法（不能使用未定义的getGraph别名），无任何post函数，证明不会重放AI／确认。getCourseChapterPath可按需读路径，不参与每次主bundle。
- [x] **Step 2: 跑RED。** `node --test tests/course-workspace-state.test.mjs`，模块缺失为预期。
- [x] **Step 3: 实现签名。** generation与AbortController同时保护读请求；nav/canvas/detail digest一致后才提交同一bundle，第一次不一致全部重读一次，第二次只报需要刷新。搜索全课程结果和现有范围对照；选中范围外结果清chapter/source，不清relation，并提示条件变化。401／filemate:session-expired由壳调用resetIdentity；不同身份没有旧快照回退。浏览改动不重新提取。openCitation也受当前course/identity/generation约束；迟到旧引用丢弃，引用digest变化时关闭旧引用并提示刷新，不把它拼到旧详情下。
- [x] **Step 4: 跑GREEN。** 本卡＋Task4 tests，逐个验证所有迟到promise及计时器在dispose后不改状态、不发新读。故障后的旧快照标记stale，来源打开仍走服务端新核对。
- [x] **Step 5: 提交。** `feat(graph): 增加一致读状态与跨课程故障恢复`。

## Task 6: 三栏工作台、关系画布和大纲

**Files:** Create `components/course-graph/CourseWorkspace.vue`, `CourseNavigation.vue`, `CourseCanvas.vue`, `CourseOutline.vue`, `CourseEvidence.vue`, `course-graph/workspace-layout.ts`, `styles/course-workspace.css`; Modify `views/KnowledgeGraph.vue`; Test `filemate/web/tests/course-workspace-layout.test.mjs`。

**Interfaces:**
- Consumes: Task4/5控制器与Task3响应；现有ECharts GraphChart/CanvasRenderer、主题token与SVG导出。
- Produces: `layoutWorkspaceCanvas(data: WorkspaceCanvas): {nodes: PositionedWorkspaceNode[], edges: WorkspaceRelation[]}`，PositionedWorkspaceNode=WorkspaceNode加x/y:number；groups模式另用WorkspaceGroup生成明确kind=group的ECharts显示对象，不冒充概念响应。`CourseCanvas` props=data/selectedId/reducedMotion，events=select(id)/openGroup(groupId)/expand(id)；CourseNavigation events=course/filter/openManager，CourseOutline events=select/page，CourseEvidence events=openCitation/openManager。CourseWorkspace公开`canLeave(): Promise<boolean>`供路由壳调用。

- [x] **Step 1: 写布局失败用例。** 断言`deterministic_layout_preserves_direction`同数据多次坐标相同；prerequisite布局a在b之前、depends_on按依赖前置排名但连线from/to不改；related_to环不参与拓扑；`isolated_and_long_label_nodes_stay_selectable`、`duplicate_group_members_keep_same_concept_id`、`node_budget_remains_100`。损坏依赖环回安全网格并给错误状态，不卡死或删数据。
- [x] **Step 2: 跑RED。** `node --test tests/course-workspace-layout.test.mjs`。
- [x] **Step 3: 实现纯布局与三个视图。** 使用ECharts layout=none、确定性章节／层级坐标、16px常用标签，选中描边／箭头与关系文字；缩放0.3–3、拖拽仅页内、重置/回概览。多组概览不是语义节点；点击读取所选子图，不从前端并发拼满分页。大纲明确“按资料所属章节整理”，重复出现的同一ID不重复计数。学习证据视图显示资料引文与个人关联空态；不渲染假分数或D动作。
- [x] **Step 4: 完成壳与响应式。** 一个搜索、一个视图切换、一个整理动作；章节／来源条件可清除，进入默认course模式且保留source切换。内容宽≥1080px用220/剩余/320三栏，<1080收目录抽屉，<820详情改覆盖，<640列表主界面；中心不足480px时进一步收栏。这些是工程起点，实测1366含全局导航的实际宽度，不以视口数值强制三栏。组件变化清Observer/事件/实例，主题和reduced-motion同步选中状态。
- [x] **Step 5: 跑GREEN并浏览器核对。** 本卡node:test、`npm run build`；用原创B资料核对初始画布可见、放大/拖拽/复位、章节展开、搜索画布外节点、三视图选中ID一致。暂缺Task7原文和管理时不可出现假按钮，保留明确尚未接线状态，仅作开发候选。
- [x] **Step 6: 提交。** `feat(graph): 实现课程三栏工作台与章节关系画布`。

## Task 7: 原文／详情面板与B审核管理整合

**Files:** Create `components/course-graph/CourseSourcePanel.vue`, `CourseManager.vue`; Modify `CourseWorkspace.vue`, `CourseEvidence.vue`, `CourseGraphPanel.vue`, `course-graph/review-state.ts`（仅必要失效通知）, `styles/course-workspace.css`; Test `filemate/web/tests/course-workspace-manager.test.mjs`。

**Interfaces:**
- Consumes: Task3 citation/detail API；Task5 `invalidateAfterMutation`；B `createCourseReviewFlow`, `CourseGraphPanel.canLeave()`。
- Produces: CourseManager props=courseId/sources，events=changed(courseId)/closed；公开canLeave()。嵌入B面板新增optional initialCourseId、managed（缺省false），changed仅在成功确认／融合／移出／撤销／恢复／章节归属写入后发出。父壳成为唯一C路由离开guard；managed=false保留B原行为，不能叠加两次确认。

- [x] **Step 1: 写管理及失效测试。** `unsaved_review_blocks_close_until_user_choice`、`successful_commit_emits_once_failed_refresh_does_not_reconfirm`、`closing_manager_does_not_cancel_or_restart_saved_work`、`restoring_backup_invalidates_preview_and_read_bundle`、`one_modal_at_a_time_restores_focus`。B token／请求键／epoch保持原义，重复成功回执只刷新读，不再次提交。
- [x] **Step 2: 跑RED。** 新node:test先因适配接口缺失失败；真实焦点／屏幕布局不用字符串测试替代，放Step5浏览器验证。
- [x] **Step 3: 整合管理。** CourseManager打开覆盖工作区、窄屏全屏，B状态在关闭／重开期间保留且不静默丢失dirty；未保存离开按原确认，正在提取有停止按钮与后台结果说明，不能卸载重开导致第二次AI请求。更换课程前统一canLeave。写入成功→清C旧详情/引用→一次读刷新；备份恢复或身份变更清所有预览，不能复活旧token。修改review-state仅补确定的invalidations，原B tests保留。
- [x] **Step 4: 整合详情／原文。** 分页引用50条，显示双源文件名／真实页码。每次点击原文经控制器openCitation读取Task3新结果，转义before/quote/after，quote用原生mark高亮；失效不显示缓存成功。返回选中节点并恢复触发按钮焦点。AI问答仅“打开资料问答”→/ai-tools?source=实际来源，维持原授权；无数据不放可执行练习／任务按钮。
- [x] **Step 5: 跑GREEN与浏览器。** 前端新旧course tests、后端B全子集通过；浏览器完成B提取审核融合指定撤销恢复、来源移出与原文失效、长文件名/重复Unicode引用、Escape/Tab焦点约束、手机列表详情返回；宽屏和平板不横向溢出，四主题实际测对比度。保留截图与请求计数，无自动模型调用。
- [x] **Step 6: 提交。** `feat(graph): 整合知识详情原文定位与B级审核恢复`。

## Task 8: 规模／故障实测与阶段交付

**Files:** Create `scripts/acceptance/course_workspace_benchmark.py`, `filemate/tests/course_graph/test_workspace_benchmark.py`, `docs/KNOWLEDGE_GRAPH_2_0_C_DELIVERY.md`; Modify B fixture仅必要可选章节样本、README、`docs/KNOWLEDGE_GRAPH_2_0_EXECUTION.md`、API_SPEC、design-system/filemate/MASTER.md；脱敏证据放`docs/audits/knowledge-graph-2-c-2026-10-22/`，原始DB/trace/log仅`_working/kg-c-20261022/`。

**Interfaces:**
- Consumes: 所有Task1–7接口；B备份恢复／默认关闭机制。
- Produces: CLI `uv run python -m scripts.acceptance.course_workspace_benchmark --output-root <新的绝对目录> --sizes 100 1000 10000`，只创建专用合成SQLite并写带synthetic=true的JSON；生成层可通过原审核服务分批发布，直接播种规模夹具须明确标注“性能构造，不证明提取质量”。禁止使用真实用户库，目标已存在则拒绝覆盖。

- [x] **Step 1: 写基准准备安全用例。** `test_existing_or_relative_output_refused`、`test_requested_sizes_are_exact_and_identity_isolated`、`test_benchmark_results_distinguish_unmeasured_browser_fields`；不存在浏览器数值时为null，不能填0伪装测量。
- [x] **Step 2: 跑RED→实现脚本→GREEN。** `uv run pytest filemate/tests/course_graph/test_workspace_benchmark.py -q`；脚本只生成新临时合成环境，报告DB/WAL一并计空间、版本/机器/开关/总节点和实际返回规模，不把分页延迟当全图布局。
- [x] **Step 3: 执行100／1000／10000规模。** 每项冷1次热5次，保存查询服务和真实HTTP的workspace、搜索、focus邻域时间、响应字节、首次有界画布可交互、选择/缩放长任务与浏览器内存；浏览器实测不可用的内存指标明确记未测及原因。热门路径5次最大HTTP≤2秒、初始可交互≤3秒、交互样本无>200ms主线程长任务；不声称总体P95。若失败先定位查询／布局瓶颈，修复同卡并保留失败记录，不能以静态截图通过。
- [x] **Step 4: 完整用户／故障链。** 新合成账户导入数据结构两份和Python一份→B审核→章节分组→检索另页符号概念→邻域→双来源Unicode定位→切三视图→刷新/返回→管理融合撤销恢复→导出个人备份→移出来源保留历史→预览恢复→重新读digest；FK=0。断网、模拟503、来源正文变更、选中概念撤销、两身份迟到响应和默认关闭各独立留结果，所有成功／错误状态有可达恢复。不开真实相机／语音，不把合成记录作学习效果结论。
- [x] **Step 5: 真实五尺寸／四主题复验。** 窄屏长名称、空数据、超量节点/来源、键盘／减少动画／焦点、无溢出、主动作44px及文字对比度；保存截图、浏览器错误、每场关键请求计数与开关关闭时旧深链200/新接口503证据。
- [x] **Step 6: 最终门禁。** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`退出0；核对原24份测试SHA256、diff范围、schema/备份兼容、未提交敏感文件。记录确切passed/skipped/warnings，不硬编码预期通过总数。
- [ ] **Step 7: 收尾交付与独立审阅。** 更新C交付的逐项完成状态、真实截图／性能／故障证据、未测与已知限制；native执行结束按executing-plans要求进行一次独立整分支审阅，修复重要问题并复验受影响范围。未完成项不能勾选为通过；交付等待“C级通过”，不推送、不部署、不进入D。
- [x] **Step 8: 提交。** 仅暂存本卡实际交付文件，`test(graph): 保存C级工作台功能性能与恢复证据`。

## 自审与执行交接

本计划自身不代表上述Task已执行。全部复选框初始未勾选。

- 设计1–3目标／入口→Task4/6/7；设计4三视图→Task1/2/6/7；设计5搜索筛选→Task1/2/4/5；设计6来源→Task3/7；设计7查询预算→Task1/2/3/8；设计8状态与隐私→Task3/4/5/7；设计9响应式／无障碍→Task6/7/8；设计10故障兼容→Task3/5/7/8；设计11性能门禁→Task8；设计12阶段边界→本计划Global Constraints和Task8。
- 类型／接口名跨卡统一：WorkspaceFilter→WorkspaceCanvas/Detail/Citation→WorkspaceApi→CourseBrowse→控制器→组件；C详情使用独立endpoint，避免篡改B含merge_candidates详情语义。所有新文件均由相应任务创建，不残留未归属setup卡。
- Review Focus五类均有命名测试与浏览器／性能验证，不新增只证明样式文本存在的镜像测试。
- 路径／合同／参数为本轮工程决定；具体SQL、组件内部组织在这些合同内由实施者决定。需要变更公共合同则同步调用方和文档，不能绕过原来源有效性、身份或有界查询约束。
- 当前只提交计划和设计确认记录；文档链接／格式及原用户文件哈希校验不替代产品测试。计划待用户审阅确认后，再按保存的native方式进入Task1；无需再次选择执行方法。
