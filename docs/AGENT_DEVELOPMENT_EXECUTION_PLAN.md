# FileMate 多 Agent 执行开发文档

版本：1.0
基线日期：2026-08-27
代码基线：GitHub `main`，合并提交 `e8584f4`
初步版本截止：2026-08-31
最终版本截止：2026-09-30

## 1. 文档用途

本文是交给其他开发 Agent 的任务总合同。它不替代 `README.md`、`AGENTS.md` 或 API 规范，而是回答四个问题：

1. 当前大创项目还缺什么；
2. 哪些工作必须先做，哪些可以延期；
3. 每个 Agent 可以修改哪些文件、必须交付什么证据；
4. 如何避免多人重复实现、修改同一数据库迁移或把规划功能冒充成已完成。

所有 Agent 开始前必须完整阅读：

1. `AGENTS.md`；
2. `README.md`；
3. 本文；
4. `filemate/docs/API_SPEC.md`；
5. 任务卡列出的源码与测试。

如本文与当前代码、路由、SQLite migration 或 CI 冲突，以最新 `main` 的代码和测试为准，并在 PR 中同步修正文档。

## 2. 当前结论

FileMate 已经不是空原型，现有版本具备可运行的 Vue 3 + FastAPI + SQLite v8 主链，核心可信执行、资料理解、知识库、词法检索、练习、错题、学习计划、今日学习、模拟面试和成长统计已经存在。

距离“大创初步版本”主要还差五类收口工作：

1. 新合入的 `filemate/study/` 出题、判题算法还没有接入现役 `/ai/questions` 和 `/quiz/attempts`；
2. 资料问答虽有引用，但缺少稳定的无依据拒答、引用阈值和更完整的评测集；
3. 知识资料缺少完整的数据删除、托管上传文件清理和隐私生命周期；
4. 六条核心用户流程缺少一套可重复执行的端到端验收；部分页面仍需统一空、错、加载、重试、键盘和移动端体验；
5. 模拟面试和成长画像有功能，但评分证据、评分模式标识、动态计划与真实用户验证尚不充分。

8 月不应优先投入 Neo4j、完整 GraphRAG、多人云同步或付费数字人。它们不会修复当前验收缺口，且会扩大部署、隐私和稳定性风险。

## 3. 当前能力差距矩阵

| 能力 | 当前状态 | 证据入口 | 下一动作 | 优先级 |
|---|---|---|---|---|
| 文件解析、分类、命名、日程 | 已实现 | `server.py`、`perception/`、确认执行测试 | 只修验收发现的问题 | 保持 |
| 归档确认、冲突保护、回滚、撤销 | 已实现并有测试 | `confirmation_executor.py` | 不破坏不变量 | P0 保护 |
| 摘要、卡片、题目、笔记 | 已实现 | `/ai/*`、`AITools.vue` | 统一题目生成/判题合同 | P0 |
| `filemate/study/` 算法 | 已合入但未接线 | `study/generator.py`、`test_study.py` | 接入现役 API，不新建第二套表 | P0 |
| 问答引用 | 部分完成 | `/ai/chat`、`retrieval.py` | 增加拒答、阈值、评测与反馈证据 | P0 |
| 错题与间隔重复 | 已实现基础闭环 | `wrong_questions`、`Wrongbook.vue` | 增强错因与知识点证据，不重建错题表 | P1 |
| 今日学习与计划 | 已实现静态聚合 | `/review/today`、`StudyPlan.vue` | 9 月再做基于薄弱点的动态调整 | P1 |
| 数据删除与隐私 | 部分完成 | 本地目录、匿名反馈 | 增加资料级删除和托管文件清理 | P1 |
| 模拟面试 | 已有文本、浏览器语音和四维评分 | `interview.py`、`Interview.vue` | 增加评分证据、模式标识和盲评接口 | P1 |
| UI/UX | 自然绿主框架已完成 | `filemate/web/` | 全页面状态、可访问性和 375px 验收 | P1 |
| 自动化验收 | 单元/集成/构建已具备 | CI、`scripts/verify.ps1` | 补六条核心流程验收 | P0 |
| 真实用户实验 | 协议和分析脚本已具备 | `REAL_USER_EVALUATION_PROTOCOL.md` | 需要真人参与，Agent 只能准备工具 | 外部依赖 |
| Embedding/向量检索 | 未实现 | 仅存在规划 | 真实词法检索基线不足后再启动 | Stretch |
| 数字人供应商 | 未实现 | 当前仅 2D 状态舞台 | 9 月核心流程稳定后做 Provider 原型 | Stretch |
| Neo4j/GraphRAG/云端账户 | 未实现 | `ARCHITECTURE.md` 目标设计 | 不进入 8–9 月强制范围 | 暂缓 |

## 4. 发布目标与范围

### 4.1 2026-08-31：`v1.3.0-alpha`

必须完成任务 A1–A5，并满足：

- 六条核心流程在新环境可重复执行；
- P0 缺陷为 0；
- 题目生成、作答、错题和今日复习使用同一套现役数据模型；
- 问答在无可靠引用时拒答，不制造资料中不存在的依据；
- 用户能删除一份知识资料及其派生产物，并明确知道会删除什么；
- 所有主要页面具备加载、空、错误和重试状态；
- 后端测试不得低于 2026-08-13 的 `314 passed` 基线；
- Ruff、Vue 类型检查、Vite 构建和 GitHub Actions 全绿；
- 本地运行即可验收，安装包不阻塞 Alpha。

### 4.2 2026-09-30：`v1.3.0`

在 Alpha 稳定后完成 B1–B3，并满足：

- 模拟面试评分能指出对应回答证据，并区分 LLM 与本地降级评分；
- 成长画像只展示有样本量和更新时间支持的结论；
- 学习计划可以依据真实错题和计划完成情况给出可解释调整建议；
- 至少完成 10 名种子用户 beta；正式竞赛结论仍以 30 名真实学生协议为准；
- 所有 P0/P1 为 0，接口和 migration 在 2026-09-27 后冻结；
- 是否启用 Embedding 或数字人原型由评测数据和独立负责人决定。

## 5. Agent 协作与 Git 合同

### 5.1 强制规则

- 一个任务卡对应一个分支和一个 PR，不直接向 `main` 推送。
- 分支统一使用 `codex/` 前缀，例如 `codex/a1-quiz-integration`。
- 开始前从最新 `main` 创建分支；提交前再次同步 `main`。
- 提交遵循 Conventional Commit，例如 `feat(study): 接入统一出题与判题合同`。
- 不修改已经发布的 SQLite v1–v8 migration。
- 新 migration 版本必须串行分配。A3 使用 v9；后续 Agent 必须先读取最新 `_MIGRATIONS`，不得自行假定版本号。
- `server.py`、`filemate/execution/storage.py`、`filemate/web/src/services/api.ts` 是高冲突文件。涉及这些文件的任务默认按 A1 → A2 → A3 顺序合并，不并行落库。
- 不提交 `.env`、数据库、用户原文、真实身份、`node_modules`、构建目录和 `_working` 证据。
- 不降低测试阈值、不删除失败测试、不把真实失败改成跳过。

### 5.2 每个 PR 必须提供

1. 用户可见变化；
2. 改动文件和公共合同；
3. 新增或修改的测试；
4. 实际执行的命令与结果；
5. 已知限制；
6. 是否修改 API、schema、环境变量、路由或隐私边界；
7. 截图或机器可读证据的 GitHub Actions 链接（适用时）。

### 5.3 停止条件

Agent 遇到以下情况必须停止并报告，不得猜测：

- 发现 `main` 的 schema 版本已被其他 PR 占用；
- 需要删除或覆盖真实用户文件；
- 需要新的付费服务、API Key、账号或授权数据；
- 产品选择会改变隐私边界、评分口径或用户流程；
- 合并冲突涉及其他 Agent 尚未合入的唯一改动；
- 测试失败无法确认是本次回归还是既有问题。

## 6. 8 月 31 日必须执行的任务卡

## A1：统一题目生成与判题主链

优先级：P0
建议周期：2026-08-13～2026-08-16
分支：`codex/a1-quiz-integration`

### 当前问题

- `/ai/questions` 仍直接使用 `understanding.QuestionExtractor`；
- `/quiz/attempts` 使用 `server.py::_answer_score`；
- 新合入的 `study.generate_questions_with_llm()`、`study.check_answer()` 和规范化逻辑没有进入用户主流程；
- 如果继续同时维护两套算法，题型、答案字段和阈值会逐步分叉。

### 目标

建立一条唯一主链：资料解析 → 文档切片 → 结构化出题 → Artifact 持久化 → 统一判题 → 错题更新。

### 允许修改

- `filemate/study/`
- `filemate/understanding/ai_tools.py`
- `server.py`
- `filemate/tests/test_study.py`
- `filemate/tests/test_server_persistence.py`
- `filemate/docs/API_SPEC.md`
- 必要时同步 `filemate/web/src/services/api.ts` 和 `AITools.vue`

### 禁止事项

- 不新建 `documents/questions/wrong_book_items` 等第二套数据库表；
- 不恢复旧 Gradio `StudyService`；
- 不改变 `artifacts`、`quiz_attempts`、`wrong_questions` 的现役所有权；
- 不把模型失败伪装成成功生成模板题。

### 实现要求

1. 统一题型枚举与字段：`type/question/options/answer/explanation`；
2. 模型结构异常时给出明确错误或可审计的规范化结果；
3. 选择、填空、简答判题均拒绝空答案；
4. 每道题保留 `knowledge_point`，可选保留来源片段标识；
5. 答错后重置已掌握状态；连续答对逻辑保持现役间隔重复策略；
6. API 继续返回统一 `{success,data,error}`；
7. 旧 Artifact 仍可作答，不做破坏性数据迁移。

### 验收

- 新增选择、填空、简答、空答案、重复题干、模型无效 JSON 测试；
- 新增“生成题目 → 提交错误答案 → 错题出现 → 连续正确后掌握 → 再答错后重新进入复习”集成测试；
- `uv run pytest filemate/tests/test_study.py filemate/tests/test_server_persistence.py -q` 通过；
- 完整 `scripts/verify.ps1` 通过。

### 交给 Agent 的提示词

```text
执行 docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md 的 A1，且只执行 A1。
从最新 main 创建 codex/a1-quiz-integration。先写失败测试，再接入现役
Source/Artifact/QuizAttempt/WrongQuestion 数据模型。禁止恢复旧 StudyService
或创建第二套题目/错题表。完成后运行 A1 定向测试和 scripts/verify.ps1，
用 PR 报告 API 兼容性、测试结果和已知限制。
```

## A2：可追溯问答与无依据拒答

优先级：P0
依赖：A1 合并后执行
建议周期：2026-08-17～2026-08-20
分支：`codex/a2-grounded-retrieval`

### 当前问题

- 本地 BM25 风格检索与页码引用已经存在；
- 当检索没有命中时，聊天可能退回整篇上下文继续作答；
- 没有经过评测确定的最低相关阈值；
- 离线集合只有 12 个合成用例，不能支持真实准确率宣传。

### 目标

让每次资料问答都处于“带可核对引用回答”或“明确拒答”之一，并保存足够的匿名反馈证据。

### 允许修改

- `filemate/understanding/retrieval.py`
- `server.py` 的知识检索和 `/ai/chat` 路由
- `evaluation/run_evaluation.py`
- `evaluation/datasets/retrieval_cases.json`
- `filemate/tests/test_retrieval.py`
- `filemate/tests/test_server_persistence.py`
- `Knowledge.vue`、`AITools.vue` 的引用/拒答显示
- API 规范与评测基线文档

### 实现要求

1. 定义机器可测试的 `answerable` 判定，不在路由里散落魔法数字；
2. 无可靠片段时不调用生成式回答，返回稳定拒答和空 citations；
3. 有答案时 citations 至少包含 source、页码/片段、excerpt、score；
4. Prompt 要求回答只依据提供引用，不添加未给出的事实；
5. 扩充合成回归集到至少 30 个问题，覆盖可回答、不可回答、同义表达、多页冲突；
6. 保留词法回退，不在本任务引入向量数据库；
7. 指标继续标记为合成工程基线。

### 验收

- Recall@1、Recall@3、MRR 和无依据拒答率进入机器可读报告；
- 不可回答用例的生成模型调用次数为 0；
- 引用反馈仍不保存原问题和原文；
- 定向测试、完整验证和前端构建通过。

### 交给 Agent 的提示词

```text
执行开发文档 A2，只处理可追溯检索与无依据拒答。不得引入 Chroma、
Neo4j 或外部 Embedding。先扩充离线数据与失败测试，再调整 retrieval 和
/ai/chat；确保拒答不会调用 LLM，引用结构向后兼容。最后更新评测口径，
明确所有指标是合成工程基线。
```

## A3：知识资料删除与本地数据生命周期

优先级：P1
依赖：A2 合并后执行
建议周期：2026-08-20～2026-08-23
分支：`codex/a3-data-lifecycle`

### 当前问题

- 用户可查看和编辑 Source/Artifact，但没有完整资料删除流程；
- 上传到 `.filemate-data/inbox` 的托管文件缺少用户可控清理；
- 删除行为涉及原文件、托管副本、Artifact、Chunk、Context、Quiz 和 WrongQuestion，必须避免误删用户外部文件。

### 目标

提供“预览删除影响 → 用户确认 → 删除托管数据”的安全资料生命周期。

### 允许修改

- `filemate/execution/storage.py`
- `server.py`
- `filemate/web/src/services/api.ts`
- `filemate/web/src/types/`
- `Knowledge.vue`
- 对应存储/API 测试和 API 文档

### schema 约束

- 如果需要 migration，A3 预留 v9；
- 开工时必须再次读取 `_MIGRATIONS`，若 v9 已被占用则停止并请求重新分配；
- 不修改 v1–v8 SQL。

### 实现要求

1. 删除前接口返回受影响的 Artifact、Chunk、Context、Quiz/Wrong 数量和托管文件状态；
2. 只有位于 `FILEMATE_UPLOAD_DIR` 内的托管副本才允许随删除清理；
3. 用户原始外部文件、归档文件和其他 Source 引用文件不得被误删；
4. 删除操作幂等，部分失败返回可理解错误；
5. UI 必须二次确认，并明确“不会删除外部原文件”；
6. 覆盖 Windows 路径、符号链接/路径逃逸、文件已不存在和重复删除测试。

### 验收

- 新库、v8 升级、重复 migration 通过；
- 删除一份 Source 后其派生数据不可查询；其他 Source 不受影响；
- 非托管外部文件仍存在；
- 完整验证通过。

### 交给 Agent 的提示词

```text
执行开发文档 A3。实现知识资料删除预览与确认，只允许删除 FileMate 托管
上传副本，绝不能删除用户外部原文件。若 migration v9 已被占用立即停止。
为级联关系、路径边界、幂等和部分失败写测试；同步 FastAPI、Vue 客户端、
Knowledge 页面和 API 文档。
```

## A4：全页面 UI/UX 状态与可访问性收口

优先级：P1
依赖：A1–A3 的 API 合同稳定后执行
建议周期：2026-08-23～2026-08-27
分支：`codex/a4-ui-reliability`

### 当前问题

- 主体已经使用自然绿亮色设计；
- 部分旧样式仍含紫色 AI 色值和偏暗卡片；
- 页面之间的加载、空状态、错误、重试和成功反馈不完全统一；
- 尚无正式的 375px、键盘焦点和 `prefers-reduced-motion` 验收记录。

### 允许修改

- `filemate/web/src/`
- `design-system/filemate/MASTER.md`
- 前端 README
- 不修改后端业务算法和数据库

### 实现要求

1. 审核 13 个现役路由；每页记录 loading/empty/error/retry/success 状态；
2. 移除暗色主卡、紫粉渐变、Emoji 功能图标和硬编码非设计系统色；
3. 所有表单有 label，按钮有禁用态，异步结果有 `aria-live`；
4. 焦点样式可见，状态不只靠颜色；
5. 375px、768px、桌面宽度无横向溢出；
6. 尊重减少动画偏好；
7. 不重写视觉方向，不引入第二套组件库。

### 验收

- `npm run build` 通过；
- 使用真实运行页面验证所有路由，无控制台错误；
- 输出桌面和 375px 截图到 CI/PR 证据，不提交本地截图垃圾；
- 在 PR 中附 13 路由状态矩阵。

### 交给 Agent 的提示词

```text
执行开发文档 A4。先读 design-system/filemate/MASTER.md，审计全部 13 个 Vue
路由的加载、空、错、重试、焦点和移动端状态。保持浅色自然绿，不重做产品
架构，不添加暗色主题、紫粉渐变、Emoji 图标或第二套组件库。用实际浏览器
验收 375px 与桌面页面，并提供截图和路由状态矩阵。
```

## A5：六条核心流程自动验收与 Alpha 冻结

优先级：P0
依赖：A1–A4 全部合并
建议周期：2026-08-27～2026-08-31
分支：`codex/a5-alpha-acceptance`

### 六条必须验收的流程

1. 导入 → 分类/命名编辑 → 确认归档 → 撤销恢复；
2. 导入 → 摘要/知识卡/笔记 → 知识库 → 重启恢复；
3. 导入 → 检索/提问 → 带引用回答或拒答；
4. 生成题目 → 答错 → 错题 → 今日复习 → 掌握/再答错回退；
5. 生成学习计划 → 完成每日任务 → 今日队列更新 → CSV/ICS 导出；
6. 创建面试 → 完成五轮回答 → 四维反馈 → 成长统计更新。

### 允许修改

- `filemate/tests/`
- `scripts/`
- `.github/workflows/ci.yml`
- 必要的测试钩子、匿名 seed 和验收文档
- 只修验收暴露的 P0/P1，不新增产品范围

### 实现要求

1. 优先使用 FastAPI 集成测试覆盖持久化和重启；
2. 至少提供一条真实浏览器冒烟覆盖主导航和关键交互；
3. 测试数据全部匿名生成，不依赖私人课件和真实 API Key；
4. 需要模型的能力用合同 Stub；另保留可选 e2e 标记；
5. 输出机器可读验收 JSON，包含 commit、日期、步骤和结果；
6. 2026-08-29 起停止新增 P2 功能。

### 验收

- 六条流程全部通过；
- `scripts/verify.ps1` 与 GitHub Actions 使用同一门禁范围；
- `314 passed` 只是最低基线，新增测试后以新的实际数量更新 README；
- P0 为 0；所有未完成 P1 有负责人、复现步骤和截止日；
- 更新版本说明和 Alpha 验收报告，不在本任务制作竞赛 PPT。

### 交给 Agent 的提示词

```text
执行开发文档 A5。目标是冻结 v1.3.0-alpha，不新增功能。为六条核心流程建立
可重复的 API/浏览器验收，使用匿名 seed 和模型 Stub，输出机器可读证据。
发现 P0/P1 可在本分支修复，P2 只记录 backlog。确保本地 verify 与 CI 门禁
一致，并更新真实测试数量和 Alpha 验收报告。
```

## 7. 9 月 30 日最终版任务卡

## B1：模拟面试评分证据与专家校准

优先级：P1
建议周期：2026-09-01～2026-09-10
分支：`codex/b1-interview-evidence`

### 目标

- 每个维度返回对应回答原句或短证据；
- 明确 `scoring_mode=llm|local_fallback` 和评分版本；
- 本地回退不再只以回答长度包装成专家结论；
- 提供匿名专家评分导入格式和 Spearman 相关性分析，不伪造导师数据。

### 验收

- 模型异常、JSON 缺字段、空回答、网络失败均有测试；
- UI 显示评分来源和证据；
- 没有真实导师数据时显示“待校准”；
- 如需 migration，必须在最新 `main` 上重新申请版本号。

## B2：证据化学习画像与动态计划建议

优先级：P1
建议周期：2026-09-10～2026-09-20
分支：`codex/b2-evidence-profile`

### 目标

- 从 QuizAttempt、WrongQuestion、StudyPlan 和 Interview 聚合画像；
- 每项画像包含样本数、更新时间和计算依据；
- 样本不足显示“待评测”；
- 计划调整先生成建议，用户确认后才修改计划；
- 不创建虚假雷达图百分比。

### 验收

- 相同输入得到稳定聚合；
- 新错误能影响薄弱点建议；完成复习后能更新建议；
- 无数据、少量数据、旧数据和异常值均有测试；
- 画像结论可以追溯到匿名行为记录。

## B3：Beta 工具、真实用户研究与最终冻结

优先级：P1 + 人工协作
建议周期：2026-09-20～2026-09-30
分支：`codex/b3-beta-release`

### Agent 可以完成

- 完善匿名任务记录、前后测、SUS 数据校验和导出；
- 对输入 CSV 做 schema、范围、重复参与者和缺失值验证；
- 生成带样本量、日期、置信区间和 `sample_kind` 的报告；
- 建立 RC 验收与版本说明。

### 必须由团队完成

- 招募参与者并完成知情说明；
- 获得课程资料授权；
- 组织教师/导师盲评；
- 确认哪些结果允许用于大创/竞赛材料。

### 禁止事项

- 不把示例 CSV 当真实实验；
- 不让 Agent 生成参与者、问卷或导师评分；
- 10 人 beta 不能冒充 30 人正式实验。

## 8. 条件扩展任务

以下任务必须同时满足“Alpha 稳定、P0/P1 清零、有独立负责人、有评测计划”才能启动。

### C1：Embedding 混合检索

启动条件：真实检索数据证明词法检索对同义表达明显不足。
要求：定义 `EmbeddingProvider`；保留本地词法回退；记录延迟、成本、召回变化；不得直接绑定单一供应商。

### C2：数字人 Provider 原型

启动条件：文本模拟面试和评分证据已稳定。
要求：文本模式独立可用；数字人只负责呈现与语音，不拥有评分真相；记录首字/首音延迟、中断恢复和成本；密钥只读环境变量。

### C3：Neo4j/GraphRAG/云同步

不属于 2026-09-30 强制交付。只有真实需求证明 SQLite + 本地检索无法满足时才立项，且必须单独完成隐私、迁移、离线回退和部署方案评审。

## 9. 总控 Agent 执行顺序

```text
A1 统一题目主链
  ↓
A2 可追溯问答
  ↓
A3 数据生命周期
  ↓
A4 UI/UX 收口
  ↓
A5 六流程验收与 Alpha
  ↓
种子用户 beta / 修复
  ↓
B1 面试证据
  ↓
B2 画像与动态计划
  ↓
B3 真实评测工具与最终冻结
  ↓
按数据决定是否启动 C1/C2
```

不要让 A1、A2、A3 同时修改 `server.py` 和 `storage.py`。如果必须并行，只允许领域 Agent 先提交不触碰公共入口的纯函数与测试，由单独集成 Agent 串行接线。

## 10. 总控 Agent 提示词

下面内容可以直接交给负责执行某一阶段的 Agent：

```text
你是 FileMate 的开发执行 Agent。完整阅读 AGENTS.md、README.md、
docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md 和 filemate/docs/API_SPEC.md。

只执行我指定的任务卡，不扩展到其他任务。开始时：
1. 确认当前分支来自最新 main；
2. 核对任务卡的现状是否仍与代码一致；
3. 先写或更新失败测试；
4. 实现最小完整改动；
5. 同步 API、schema、Vue 客户端和文档中真正受影响的部分；
6. 运行任务卡验收与 scripts/verify.ps1；
7. 创建小而可审查的 PR。

严格遵守：不创建第二套数据模型；不修改已发布 migration；不提交密钥、
数据库或真实用户资料；不伪造指标、画像或用户研究；不降低测试门禁；
不删除其他人的改动。遇到 schema 版本冲突、外部账号/授权数据、破坏性
删除或无法裁决的产品选择时停止并报告。

最终报告必须包含：用户影响、文件、合同变化、测试结果、CI 链接、已知限制、
下一任务依赖。没有全部通过时不得写“完成”。
```

## 11. 每个 Agent 的交接模板

```text
任务卡：A?/B?/C?
分支 / PR：
基线 main commit：

已完成：
-

用户可见变化：
-

公共合同变化：
- API：
- schema：
- 环境变量：
- 路由：

测试：
- 命令：
- 结果：
- GitHub Actions：

未完成 / 待确认：
-

已知限制和回滚方式：
-

建议下一任务：
-
```

## 12. 项目负责人验收清单

合并每个 Agent PR 前，负责人至少确认：

- 改动确实属于该任务卡；
- 没有平行创建新的 Source/Artifact/Quiz/Wrong 数据表；
- 没有修改已发布 migration；
- 错误、空数据和模型不可用路径有真实行为；
- 新增 UI 没有假数据、暗色主界面或虚假指标；
- 测试覆盖用户结果，不只覆盖函数能运行；
- 文档没有把计划功能写成已实现；
- CI 全绿，PR 没有未解决审查意见；
- 需要人工评测的结论仍标记为“待评测”。

如果某个 Agent 交付质量不足，应保留其 PR 和失败证据，不直接在 `main` 上继续堆补丁；由负责人决定退回修改、关闭 PR，或基于本任务卡重新建立干净分支。
