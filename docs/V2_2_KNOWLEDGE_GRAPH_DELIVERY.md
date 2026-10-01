# V2.2 个人知识图谱与学习画像交付报告

日期：2026-10-01。范围：V2.2 知识图谱与学习证据加固。验收分支 `codex/v2-2-knowledge-graph` 基于 `origin/main` 的 `a523b36`，在独立 worktree `_working/release-v22` 验证；本报告只证明该快照，不把原工作区已有 V2.3/V2.4 草稿当作本阶段已完成能力。已提交 [PR #45](https://github.com/cooooooosdas/Filemate/pull/45)，已于2026-10-01合并到main（9d6d4cb）；生产网站与安装包未升级。最新远端检查以该PR的Checks为准。

## 用户可以做什么

访问 `/knowledge-graph`，选择已导入资料，以本地规则或授权后的模型生成带原文的草稿，核对后确认加入图谱。图谱支持缩放、拖动、搜索和键盘列表，点击知识点可查看出处、相关练习、作答状态和错题，再预览并确认学习路径。草稿、确认批次和本模块生成的计划均可撤销/恢复，原资料和学习证据保留。

本轮基于已有实现补充了学习画像：已练习/待评测知识点、有效作答数、待复习错题、复习关注点及前置知识依据。画像从现役 QuizAttempt/WrongQuestion 动态计算，不写回用户核心画像、不生成未经校准的能力分数。正确率明确限定为每个知识点最近10次有效作答；无样本保留待评测，学习时长保留空值。

## 本次完善

- 薄弱点按未掌握错题、最近作答正确率和30天无作答触发，点击即可查看资料、题目和证据；前置建议保留确认关系的原句。
- 支持教材中的两种明确自然语言关系句式；过滤否定/不确定词造成的肯定关系误提取。
- 按实际时间排序不同格式的时间戳；异常/未来时间和非法判题字段排除并展示数量。
- 已恢复知识点按当前待复习错题及状态着色，完整历史错误次数仍保留。
- 加载响应使用请求序号，避免旧响应覆盖新数据；刷新使旧计划预览失效。确认弹窗打开前锁定操作，防止重复弹窗。
- 模块读写请求使用有限超时，网络失败保留已加载图谱和可重试操作；计划保存完成后同步历史。
- 损坏JSON/字段结构批次暂停进入图谱，返回友好异常状态，允许撤销和重新提取；不覆盖损坏原始数据。
- 最近100条操作事件可在页面查看；事务失败回滚、重复确认/撤销/恢复/计划保存不会重复记录。
- 关闭前端模块后，历史 `/knowledge-graph` 地址转入学习工作区。
- 修改已有作答的题目正文时，旧题集、旧成绩与旧错题原子保存为只读历史快照；新题与新错题不继承旧知识点成绩、诊断或错误次数。
- 仅改标题保留证据边界；所有答题入口发送原始题目快照，过期页面与“判题过程中修改题目”均返回409且不写入错误成绩。
- 历史题集可导出与复练；知识库保存后刷新历史列表，图谱和学习工作区明确标注历史题集。

此前已有的 Source/Artifact/Context、模型客户端、题目判题、错题间隔重复、StudyPlan、匿名身份隔离与图谱草稿合同均被复用。

## 修改文件

| 文件 | 本阶段改动 |
|---|---|
| `filemate/study/knowledge_graph.py` | 学习画像、薄弱点、时间与数据异常处理、限定句式、相关路径证据指纹 |
| `filemate/execution/storage.py` | v21迁移、事务内事件、损坏批次隔离、资料删除预览计数、题集历史快照与并发判题保护 |
| `filemate/web/src/views/KnowledgeGraph.vue` | 画像和关注点、统计口径、事件历史、加载与操作保护、异常展示 |
| `filemate/web/src/types/knowledgeGraph.ts` | 补全节点证据、画像、事件与异常状态类型 |
| `filemate/web/src/services/api.ts` | 图谱请求与资料列表超时、删除计数类型、原始题目快照传递 |
| `server.py`、`LearningArtifact.vue`、`Knowledge.vue`、`AITools.vue`、`Today.vue`、`Wrongbook.vue` | 题目修订/提交冲突合同、历史只读提示、各答题入口边界与历史列表刷新 |
| `filemate/web/src/router/index.ts` | 模块关闭时旧路由重定向 |
| `filemate/tests/test_knowledge_graph.py` | 8种关系、边界、时间异常、恢复、前置路径与循环 |
| `filemate/tests/test_graph_api.py` | 画像闭环、身份隔离、取消与幂等、空/长输入、模型失败、数据异常 |
| `filemate/tests/test_graph_storage.py` | 事件与事务回滚、并发幂等、级联删除、损坏数据原样保留 |
| `filemate/tests/test_storage.py` | v21版本合同及v20升级保留资料/草稿、不补造历史 |
| `filemate/tests/test_digital_human.py` | 数据库版本断言随v21同步，数字人功能不变 |
| `scripts/acceptance/knowledge_graph.mjs` | 真实资料与真实UI/API完整闭环、响应式、网络故障注入 |
| `scripts/acceptance/seed_graph_exercise.py` | 仅向项目临时库添加一题自编练习，不预填作答 |
| `scripts/acceptance/knowledge_graph_disabled.mjs` | 独立关闭模块的页面/接口验收 |
| `scripts/acceptance/fixtures/hello_algo_heap_excerpt.txt` | 带出处、作者和许可的公开教材节选 |
| `README.md`、`filemate/docs/API_SPEC.md`、`scripts/acceptance/README.md` | 数据库、响应合同、边界、复现实验说明 |

原工作区已有数字人、目标口头复练、今日教练等未提交基础，以及后续模块草稿。本阶段复用必要基础构成可运行的独立快照；原稿均保留，不整体覆盖原工作区。`server.py` 图谱路由沿用已有实现，题目修订与判题合同按本次加固同步。

## 数据库与接口

- 从v20追加v21 `knowledge_graph_operation_events`，新增 `knowledge_graph_events`；未改写v1–v20迁移。
- 事件只保存来源/目标标识、操作、时间、状态变化、证据指纹、错误类型；不复制正文、答案、供应商错误详情或密钥。
- 事件与对应写入在同一事务提交；随 Source 删除级联清理，删除预览增加事件计数。
- 没有新增HTTP路径。`GET /api/knowledge-graph` 增加 `profile`、`events`；节点补充最近样本/排除样本/复习间隔/待复习数；批次增加 `data_error`。详见API规范4.10。
- 确认学习计划仍写入现役StudyPlan和Artifact；相关证据变化需重新预览，无关关系变化不再使预览失效。

## 真实学习资料验收

资料：[《Hello 算法》8.1 堆](https://www.hello-algo.com/chapter_heap/heap/)，作者靳宇栋及贡献者，按仓库的 [CC BY-NC-SA 4.0 许可](https://github.com/krahets/hello-algo/blob/main/LICENSE) 节选两句原文，来源声明与采集日期一起导入。只用于本地非商业学习验收；没有导入第三方题库。

验证链路：

1. 从学习工作区上传TXT，经真实文件解析与分块保存为Source。
2. 使用真实本地提取器得到“堆”“完全二叉树”“优先队列”3个节点、属于/应用于2条关系；草稿确认前不进入图谱。
3. 确认后页面渲染，节点原句与分块引用均能回查原文。
4. 为该Source添加一题明确标注“自编验收练习”的持久化Artifact，未冒充AI生成。
5. 在真实练习UI回答“数组”，真实判题写入失败作答与错题；画像变成1个已练习知识点、1道待复习错题、正确率0%。
6. 预览并确认学习路径，实际生成StudyPlan；撤销/恢复后进度仍保留。
7. 在真实错题UI连续回答“完全二叉树”两次，累计3次作答、最近正确率2/3、完整历史错误1次；待复习错题变为0，复习关注点移除。
8. 取消弹窗不写入；撤销/恢复批次后3次作答依然存在；重复恢复只记录一次变更。

以上为真实教材输入和真实系统操作的工程验收，不是真实用户研究，也不是模型提取准确率评测。外部LLM未在该闭环中调用。

## 测试结果

| 检查 | 结果 |
|---|---|
| 图谱领域/API/存储专项 | 30 passed |
| 真实教材、UI、画像、计划、取消/恢复、网络重试 | 8/8 passed |
| 模块关闭边界 | 16/16 passed：4页面、9图谱接口503、3原接口200 |
| 375 / 768 / 1024 / 1440响应式 | 无水平溢出，图谱/画像/证据截图已核对 |
| 浏览器运行异常 | 0 |
| 原工作区同步后完整门禁 | 567 passed / 18 skipped / 5 deselected；12项前端测试、Ruff、Vue类型检查及构建通过；包含后续草稿，不代表后续模块已独立验收 |
| 新增Python及测试/辅助脚本Ruff | 通过 |
| 全项目 `scripts/verify.ps1 -IsolateFrontend` | 两轮退出码0；最后一轮：Ruff、520 passed / 18 skipped / 5 deselected、npm ci、9项前端测试、Vue类型检查和生产构建通过 |

完整门禁通过。前端隔离复制避免 npm ci 删除正在运行的 Vite 原生库；数字人回归版本断言同步为v21。18项跳过来自可选OCR、缺失DOCX/PDF/PPT测试样例及Windows符号链接权限，不计为通过。构建保留既有公共包大于500kB提示，不影响退出码。三处独立实验发现的题目修订缺陷均加入真实存储/HTTP回归：改知识点后新错题漏挂、首次只改标题丢失证据、读旧题→编辑→提交旧判题成绩。

首轮GitHub Linux CI暴露了图谱模型合同测试依赖本机密钥的问题：仅替换模型响应，构造客户端仍触发真实凭据校验。测试fixture现独立提供配置/Provider替身，并断言不得调用外部模型；正式模型客户端与密钥校验未放宽。本地该API专项8项通过，远端复核由PR Checks记录。

单元/集成回归中的课程片段与模型失败响应属于合成测试；网络中断由Playwright显式故障注入，结果标为 `MOCK_network_fault_real_api`。教材、解析、知识提取、数据库、题目判题、作答、错题、画像和学习计划使用真实实现。

证据均在临时目录，未提交数据库、真实用户资料或密钥：

- `_working/acceptance/final/results.json`：最终8项浏览器闭环。
- `_working/acceptance/final/graph-profile-*.png`、`graph-*.png`、`graph-evidence.png`：画像、图谱与出处。
- `_working/acceptance/disabled-current/results.json`：16项模块关闭检查。
- `_working/acceptance/verify-final.log`：最后一轮完整工程门禁（`verify-current.log` 为前一轮，也通过）。
- 原工作区的 `_working/verify-synced-20261001.log`：同步后完整工程门禁，路径相对于 `D:/FileMate-Project`，不属于独立快照的520项结果。
- `_working/acceptance/question-history.png` 与 `.playwright-cli` 快照：真实页面仅改标题后堆的3次作答不变；改为“优先队列”后堆仍3次、新点0次；历史题集自动出现在列表，只显示导出而无编辑按钮。
- `_working/graph_revision_independent_validation.py` 及其合成 SQLite：保留初始缺陷复现，不作为修复后通过证据。
- 以上路径均相对于独立验收 worktree；首轮CORS失败与后续run2现场原样保留，不删除复核证据。

## 已知限制与待优化

- 本地规则仅识别有限明确句式，不能测量一般教材提取召回率。外部模型Provider已接入并有失败/幻觉格式拒绝测试，尚未完成真实外部模型质量/超时/限流测量。
- 仍复用现役PDF/DOCX/PPTX/TXT解析；扫描件需可用OCR，旧版Office、图片、代码和Markdown扩展名未在本阶段增加上传支持。
- 图谱节点按资料区分，跨资料同名概念不自动合并。题目必须与知识点标识匹配才进入该节点画像；未匹配练习不纳入统计。
- 没有可靠学习时长、心理/能力测量、学科总体评分或真实用户长期趋势；显示待评测。
- 知识状态和30天回忆提醒来自公开规则，属于辅助反馈；小样本不能据此断言掌握程度。
- 图谱批次完整保留，事件接口只返回最近100条；大量资料/批次的长期性能尚未实测。
- 本阶段未加入Neo4j、向量数据库、GraphRAG或V2.3代码执行沙箱。

## 回滚方式

1. 运行时设置 `FILEMATE_ENABLE_KNOWLEDGE_GRAPH=0`，重启后端：图谱全部接口503，其余学习接口可用。
2. 前端构建/开发启动时设置 `VITE_ENABLE_KNOWLEDGE_GRAPH=false`：隐藏入口，旧地址跳转学习工作区。
3. 用户可在历史中撤销/恢复批次与图谱学习计划；不删除Source、QuizAttempt、WrongQuestion或计划完成进度。
4. 代码回退前先备份数据库；v21是附加表，关闭模块无需删除表。若要求数据库也回到旧版本，应恢复对应备份，不直接DROP表或修改已应用迁移。

## 下一版本建议

完整五模块目标仍在进行中。本阶段验收后顺序核对原工作区已有V2.3草稿的隔离执行Provider、C++编译运行、测试点和AC/WA/TLE/RE/CE，再进入后续模块；禁止把宿主机直接执行用户代码当作沙箱。真实外部模型评测、生产发布、全部版本/EXE同步和真人试用尚未完成。
