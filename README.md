# FileMate

FileMate 是一个面向大学生的本地优先 AI 学习工作台。它把散落的课程资料转化为可追踪、可复习、可验证的学习资产，并通过“资料导入 → AI 理解 → 用户确认 → 学习计划 → 练习与错题 → 复习与成长分析”形成完整闭环。

> 项目类型：国家级大学生创新创业训练计划项目
> 当前版本：`v1.2.0` Reliable Foundation
> 当前基线日期：2026-08-24
> 初步版本截止：2026-08-31
> 最终版本截止：2026-09-30

## 1. 先读这里：项目权威入口

第一次接手项目的人或 AI，请按以下顺序阅读，避免被旧计划或目标架构误导：

1. [`AGENTS.md`](AGENTS.md)：AI 和开发者必须遵守的最小开发规则、命令与边界。
2. 本 README：现役能力、真实技术栈、整体结构、路线图和协作方式。
3. [`filemate/docs/API_SPEC.md`](filemate/docs/API_SPEC.md)：Python 核心接口与 HTTP API 合同。
4. [`PRODUCT.md`](PRODUCT.md)：用户、产品原则、视觉承诺与竞赛证据边界。
5. [`design-system/filemate/MASTER.md`](design-system/filemate/MASTER.md)：自然绿色 UI 设计系统。
6. 与任务直接相关的源码和测试；代码与文档冲突时，以当前 `main` 代码、测试和 CI 为准，并同步修正文档。

以下文档属于长期规划或专项材料，不能当作现役实现清单：

- [`docs/FILEMATE_AI_PRODUCT_MASTER_PLAN.md`](docs/FILEMATE_AI_PRODUCT_MASTER_PLAN.md)：长期产品总规划。
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：FileMate 2.0 目标架构，包含尚未落地的图数据库与 Agent 能力。
- [`docs/FILEMATE_COMPETITION_EXECUTION_OUTLINE.md`](docs/FILEMATE_COMPETITION_EXECUTION_OUTLINE.md)：竞赛方向与阶段任务。

## 2. 当前状态一览

### 2.1 已实现并接入主流程

| 能力域 | 当前能力 | 主要入口 |
|---|---|---|
| 资料导入 | PDF、DOC/DOCX、PPT/PPTX、TXT 上传；单文件最大 25 MB | `POST /process`、`Import.vue` |
| 文件理解 | 文本解析、关键词/LLM 分类、课程与任务实体抽取、多里程碑识别、规范命名 | `filemate/perception/`、`filemate/understanding/` |
| 可信执行 | 草稿编辑、最终确认、目标冲突保护、失败回滚、幂等确认、一键撤销 | `confirmation_executor.py` |
| 日程管理 | 从截止日期和里程碑生成 RFC 5545 `.ics`，确认前只预览 | `scheduler.py`、`Schedule.vue` |
| AI 工具 | 摘要、知识卡、练习题、结构化笔记、基于资料的问答、学习计划 | `ai_tools.py`、`AITools.vue` |
| 个人知识库 | 资料源、AI 产物、聊天上下文持久化；跨资料词法检索与引用 | `storage.py`、`retrieval.py`、`Knowledge.vue` |
| 学习闭环 | 练习作答、自动错题本、掌握状态、间隔重复、今日复习队列 | `/quiz`、`/wrongbook`、`/review/today` |
| 学习计划 | 根据考试日期生成日计划，持久记录每日完成状态，支持 CSV/ICS 导出 | `StudyPlan.vue` |
| 模拟面试 | 求职、竞赛答辩、保研复试；四维评分；模型不可用时本地降级 | `interview.py`、`Interview.vue` |
| 成长数据 | 资料、练习、错题、计划、面试等本地统计；匿名反馈导出 | `Growth.vue`、`evaluation/` |
| 多端工程 | Vue Web、FastAPI Sidecar、Tauri 2 桌面工程、CLI | `filemate/web/`、`server.py`、`main.py` |

### 2.2 已有基础，但仍需完善

| 能力 | 当前边界 | 8–9 月工作重点 |
|---|---|---|
| 检索增强问答 | 当前为本地分块 + BM25 风格词法排序 + 页码/片段引用，不是向量 RAG | 增加可替换 Embedding 适配器、对照评测和稳定引用 |
| 成长画像 | 已有真实行为聚合，不生成虚假数据 | 完善指标解释、时间窗口和空状态 |
| 模拟面试 | 文字回答和四维评分可用；语音依赖浏览器能力 | 加强题库、证据化反馈和真实导师盲评 |
| Tauri 桌面端 | 工程、Sidecar 脚本和图标已具备 | 暂不把安装包作为 8 月初版阻塞项；9 月末视稳定性验收 |
| 真实评测 | 已有离线合成基线和匿名评测管线 | 组织真实学生试用，区分工程基线与真实结论 |

### 2.3 尚未实现，不得对外宣称已完成

- Neo4j 知识图谱、Chroma/其他向量数据库和完整 GraphRAG。
- 用户注册、云端账户同步、多人协作权限体系。
- 可替换的数字人供应商和实时口型驱动。
- Docker/云端生产部署、正式监控告警和多租户隔离。
- 大规模真实用户实验结论；当前 100% 离线指标只代表小型合成回归集。

## 3. 两个月交付规划

规划原则：完成比堆功能重要；8 月先形成稳定初版，9 月再用真实反馈和质量证据打磨最终版。任何扩展功能不得破坏“资料—练习—错题—计划—复习”的主闭环。

### 3.1 里程碑定义

| 里程碑 | 截止日期 | 版本建议 | 目标 |
|---|---|---|---|
| 初步版本 | 2026-08-31 | `v1.3.0-alpha` | 队友可一键本地运行；六条核心流程完整；无 P0 阻塞缺陷 |
| 最终版本 | 2026-09-30 | `v1.3.0` | 完成真实用户试用、质量加固、接口冻结和交付文档；形成可持续迭代基线 |

### 3.2 2026-08-10 至 2026-08-31：初步版本

| 时间 | 主题 | 必须完成 | 交付与验收 |
|---|---|---|---|
| 08-10～08-16 | 合同与工程收口 | README/API/数据模型对齐；统一错误响应；清理页面假数据和失效入口 | 新成员只看 README 与 AGENTS 即可启动；CI 绿 |
| 08-17～08-23 | 核心闭环联调 | 文件确认/撤销、知识库、问答引用、学习计划、作答错题、今日学习、面试全部串通 | 六条核心用户流程逐条演示；重启后数据仍可恢复 |
| 08-24～08-28 | UI/UX 与可靠性 | 移动端适配、加载/空/错/重试状态、键盘焦点、错误文案、数据导出 | 375px 与桌面宽度可用；主流程无死路；WCAG AA 基础检查 |
| 08-29～08-30 | 冻结与回归 | 停止新增 P2 功能；集中修复 P0/P1；准备匿名演示数据 | 后端测试、Ruff、前端构建、离线评测全部通过 |
| 08-31 | 初版验收 | 打标签、更新版本说明、录制内部演示 | `v1.3.0-alpha` 可由队友在新环境启动并完成验收清单 |

#### 8 月 31 日初版必须通过的六条流程

1. 导入资料 → 自动解析/分类/命名 → 用户编辑 → 最终确认归档 → 撤销恢复。
2. 导入资料 → 生成摘要/知识卡/笔记 → 产物进入个人知识库 → 重启后可查看。
3. 导入资料 → 分块检索 → 提问 → 返回答案与可核对引用。
4. 生成练习 → 提交答案 → 形成错题 → 到期后进入今日复习 → 更新掌握状态。
5. 生成考试学习计划 → 勾选每日任务 → 今日队列自动汇总 → 导出 CSV/ICS。
6. 创建模拟面试 → 连续回答 → 四维反馈 → 成长数据页查看真实统计。

#### 8 月 31 日完成定义（Definition of Done）

- Windows 队友执行 `scripts/dev.ps1 -Setup` 后可启动前后端。
- 所有高影响文件操作必须先预览确认，不覆盖已有目标，并可撤销。
- 数据写入 SQLite v8，关闭并重启后仍能读取。
- 非 e2e 后端测试不得少于当前 `330 passed` 基线；新增功能必须新增测试。
- `npm run build`、CI 静态检查和离线评测通过。
- P0 缺陷为 0；P1 缺陷必须有负责人、复现步骤和明确截止日期。
- README、API 文档和实际路由一致；不把计划功能写成已实现。
- 安装包不是本里程碑阻塞项，本地运行成功即可验收。

### 3.3 2026-09-01 至 2026-09-30：最终版本

| 时间 | 主题 | 必须完成 | 可选扩展 |
|---|---|---|---|
| 09-01～09-07 | Alpha 反馈修复 | 至少 5 名队内/种子用户走完核心流程；修复全部 P0 和高频 P1 | 引导式新手任务 |
| 09-08～09-14 | 检索与学习证据 | 扩充检索数据集；对比整篇截断与分块检索；完善引用和错因证据 | Embedding 适配器，保留本地词法回退 |
| 09-15～09-21 | 个性化与面试 | 学习画像解释、计划动态调整、面试题库与评分证据、匿名导出 | 语音输入优化；数字人供应商接口原型 |
| 09-22～09-26 | 稳定性与隐私 | 性能、数据库迁移、异常恢复、敏感数据说明、可访问性与响应式复核 | 手动执行 Tauri 安装包验收 |
| 09-27～09-29 | Release Candidate | 冻结接口；全量回归；真实用户报告；使用与开发文档冻结 | 演示视频和竞赛材料接口预留 |
| 09-30 | 最终验收 | 发布 `v1.3.0`；归档机器可读证据；形成下一阶段 backlog | 是否进入 FileMate 2.0 由验收结果决定 |

#### 9 月 30 日完成定义

- 至少 10 名真实学生完成 beta 试用，记录匿名任务完成率、耗时与 SUS；样本不足时必须标记为待评测。
- 正式竞赛结论仍遵循 [`docs/REAL_USER_EVALUATION_PROTOCOL.md`](docs/REAL_USER_EVALUATION_PROTOCOL.md) 的 30 人门槛，不能用 10 人 beta 冒充正式实验。
- P0、P1 缺陷均为 0；P2 有清晰 backlog，不阻塞主要流程。
- 核心接口冻结，数据库迁移可从旧版本幂等升级。
- 检索、面试、学习计划至少各有一组可复现评测和机器可读报告。
- 新机器按 README 能在 30 分钟内完成安装、配置、启动和首个学习任务。
- GitHub Actions 全绿；版本标签、变更说明、用户说明和开发接手文档齐全。

### 3.4 优先级边界

| 优先级 | 内容 | 处理原则 |
|---|---|---|
| P0 | 数据丢失、错误覆盖文件、无法启动、数据库不可升级、核心流程中断 | 立即停止新增功能并修复 |
| P1 | 结果错误、状态无法恢复、主要页面不可用、引用不可信 | 当前周内修复，不能带入最终版 |
| P2 | 动画、次要统计、题库扩充、视觉细节、非核心导出 | 不得挤占 P0/P1 时间 |
| Stretch | 数字人、知识图谱、向量数据库、云同步、多人协作 | 核心闭环稳定且有独立负责人后才启动 |

## 4. 现役系统架构

```mermaid
flowchart LR
    U["用户"] --> V["Vue 3 学习工作台"]
    U --> C["CLI / Watch 模式"]
    V --> A["FastAPI 本地服务"]
    T["Tauri 2 桌面壳（工程已建立）"] --> A
    C --> P["处理 Pipeline"]
    A --> P
    P --> R["感知层：文件解析 / OCR"]
    P --> N["理解层：分类 / 抽取 / 命名 / AI 工具"]
    N --> L["StepFun 等 OpenAI 兼容模型"]
    A --> E["确认执行器：预览 / 确认 / 回滚 / 撤销"]
    A --> K["学习服务：检索 / 练习 / 错题 / 计划 / 面试"]
    E --> F["本地文件系统 / ICS"]
    P --> S["SQLite v8"]
    E --> S
    K --> S
```

### 4.1 核心数据流

```text
文件上传
  → 保存到 .filemate-data/inbox/<随机目录>
  → FileParser 提取文本和元数据
  → Classifier / EntityExtractor / MilestoneDetector / Namer
  → Session 草稿写入 SQLite
  → 前端展示分类、命名和日历预览
  → 用户修改并最终确认
  → ConfirmationExecutor 原子归档并按需生成 ICS
  → 写入 execution_records 与 operation_log
  → 用户可查询历史或执行撤销
```

### 4.2 学习闭环数据流

```text
Source（原始资料）
  → document_chunks（可引用片段）
  → Artifact（摘要/知识卡/题目/笔记/学习计划）
  → QuizAttempt（作答证据）
  → WrongQuestion（错题与间隔重复状态）
  → TodayReview（今日队列）
  → Analytics（真实行为聚合）
```

### 4.3 可信执行不变量

- 分析阶段只生成草稿，不移动原文件、不写入日历文件。
- 最终确认前允许用户修改分类、课程、名称和日历开关。
- 目标文件或日历已经存在时拒绝覆盖。
- 文件移动或日历生成任一步失败时，尽可能恢复到执行前状态。
- 重复确认和重复撤销必须幂等，不重复修改文件系统。
- 文件扩展名不可通过重命名伪造，目录和文件名必须通过路径安全校验。
- Session、执行记录与审计日志保持一致，可从 SQLite 恢复。

## 5. 真实技术栈

| 层 | 现役技术 | 说明 |
|---|---|---|
| Web 前端 | Vue 3.5、TypeScript 6、Vite 8 | 单页应用与按路由懒加载 |
| UI 与状态 | Element Plus 2、Pinia 4、Vue Router 4、ECharts 6 | 自然绿色亮色设计系统 |
| 本地 API | FastAPI、Uvicorn、Pydantic | 默认监听 `127.0.0.1:8001` |
| 桌面壳 | Tauri 2、Rust | 工程已建立；安装包仅手动验收 |
| 核心语言 | Python 3.10+ | 推荐 3.11/3.12；统一 UTF-8 |
| 数据存储 | SQLite WAL，schema v8 | 本地优先、版本迁移、线程连接管理 |
| 文件解析 | PyPDF2、pdfplumber、python-docx、python-pptx | PaddleOCR 为可选依赖 |
| 检索 | 本地分块 + BM25 风格词法评分 | 支持页码/片段引用；无外部向量库 |
| LLM | OpenAI 兼容 HTTP API；当前主要为 StepFun | 通过 `LLMClient` 和 Provider 适配层接入 |
| 测试与质量 | pytest、Ruff、vue-tsc、GitHub Actions | e2e 模型测试与普通离线测试分离 |

计划中的 Neo4j、Chroma、BGE、数字人和云端部署不是当前运行依赖。新增外部能力必须通过适配层接入，并保留本地可运行的降级路径。

## 6. 目录结构与职责

```text
FileMate/
├── AGENTS.md                         # AI/开发者最小项目规则
├── README.md                         # 项目现役总入口与两个月规划
├── PRODUCT.md                        # 产品定位、原则与证据边界
├── DESIGN.md                         # UI 设计系统摘要
├── pyproject.toml                    # Python 包、依赖、pytest、Ruff 配置
├── uv.lock                           # Python 可复现依赖锁
├── server.py                         # FastAPI 本地服务与 HTTP 路由
├── main.py                           # CLI、watch 模式和处理阶段链
├── 启动FileMate.bat                   # Windows 队友入口
├── scripts/
│   ├── setup-dev.ps1                 # 首次安装开发依赖
│   ├── doctor.ps1                    # 环境诊断
│   ├── dev.ps1                       # 启动 FastAPI + Vue
│   ├── stop-dev.ps1                  # 停止本次开发服务
│   ├── verify.ps1                    # Ruff + pytest + 前端构建
│   └── seed_demo_data.py             # 生成匿名演示数据
├── filemate/
│   ├── core/                         # Session、Pipeline、Agent 协调与注册表
│   ├── llm_client/                   # LLM 配置、Provider 和统一调用封装
│   ├── perception/                   # 文件解析、OCR、watcher、解析器注册
│   ├── understanding/                # 分类、实体、里程碑、命名、检索、AI 工具、面试
│   ├── study/                        # 文本切片、题目规范化、判题与复习排期纯函数
│   ├── execution/                    # SQLite、文件操作、日历、归档、确认执行和撤销
│   ├── ui/                           # 旧 Gradio 兼容入口与后端桥接；非主前端
│   ├── tests/                        # 单元、集成、压力和可选 e2e 测试
│   ├── docs/                         # API、Prompt 与开发接口文档
│   └── web/
│       ├── src/                      # Vue 页面、路由、API 客户端、Pinia
│       └── src-tauri/                # Tauri 2 配置、Rust 壳与桌面图标
├── evaluation/                       # 离线评测、用户研究与匿名反馈分析
├── docs/                             # 产品规划、竞赛、验收与目标架构文档
├── design-system/filemate/           # UI 设计规则真身
└── .github/workflows/ci.yml          # 后端、前端 CI；安装包仅手动触发
```

### 6.1 模块边界

| 模块 | 可以负责 | 不应该负责 |
|---|---|---|
| `perception` | 文件格式判断、正文和元数据提取、OCR 回退 | 分类、文件移动、UI 状态 |
| `understanding` | 分类、实体、命名、检索、AI 学习内容和评分 | 直接写磁盘或直接操作 HTTP |
| `study` | 可复用的切片、出题结果规范化、判题和复习排期算法 | 自建重复数据库表或直接绑定某个 UI |
| `execution` | 持久化、文件归档、日历、事务式确认和撤销 | Prompt 和页面渲染 |
| `core` | Session 状态、Pipeline 编排、Agent 协调、注册表 | 具体业务页面与外部供应商细节 |
| `server.py` | HTTP 合同、参数校验、服务编排、统一错误 | 重复实现底层领域算法 |
| `web` | 用户交互、状态反馈、响应式布局、API 调用 | 直接读取 SQLite 或本地任意路径 |

## 7. SQLite v8 数据模型

数据库由 `schema_migrations` 管理，`init_schema()` 必须保持幂等。不要直接修改已经发布的迁移；新增字段或表必须增加新版本迁移和升级测试。

| 版本 | 主要表/变化 | 用途 |
|---:|---|---|
| v1 | `sessions`、`processed_files`、`operation_log`、`user_rules` | 文件处理、去重、审计、用户规则 |
| v2 | `workspaces`、`sources`、`artifacts`、`document_contexts` | 知识资料、AI 产物和连续问答 |
| v3 | `execution_records` | 确认执行、失败、撤销和幂等 |
| v4 | `document_chunks`、`quiz_attempts`、`wrong_questions` | 检索、作答和错题闭环 |
| v5 | `interview_sessions`、`interview_turns` | 模拟面试过程与评分 |
| v6 | `study_plans` | 学习计划和每日完成状态 |
| v7 | `product_feedback` | 匿名正负反馈和统计 |
| v8 | 错题间隔重复字段与索引 | 下次复习时间、间隔、难度因子、复习次数 |

关键关系：

- `Source` 是原始学习资料的统一身份。
- `Artifact` 是由 Source 派生的摘要、题目、笔记或计划。
- `Context` 保存连续问答上下文。
- `QuizAttempt` 和 `WrongQuestion` 保存学习证据，不能只存在前端内存。
- `ExecutionRecord` 是文件副作用的审计与撤销依据。

## 8. HTTP API 总览

所有业务接口统一返回：

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

参数错误使用 `400/422`，资源不存在使用 `404`，执行冲突使用 `409`，模型上游失败使用 `502`。前端读取 `error`，不要依赖 FastAPI 默认 `detail`。

### 8.1 健康与文件处理

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | Web/桌面壳探测本地服务版本 |
| POST | `/process` | 上传并处理资料，返回 Session 草稿 |
| GET | `/sessions` | 查询处理历史 |
| GET | `/sessions/{id}` | 查询单个 Session |
| PATCH | `/sessions/{id}` | 保存分类、名称或实体草稿，无文件副作用 |
| POST | `/sessions/{id}/confirm` | 最终执行或跳过 |
| POST | `/sessions/{id}/undo` | 撤销已应用的文件操作 |
| GET | `/sessions/{id}/executions` | 查询执行历史 |
| GET | `/sessions/{id}/ics` | 获取日历内容 |

### 8.2 AI 学习工具与知识库

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/ai/summarize` | 生成摘要并持久化 Artifact |
| POST | `/ai/knowledge-cards` | 生成知识卡 |
| POST | `/ai/questions` | 生成练习题并建立题目资产 |
| POST | `/ai/notes` | 生成结构化笔记 |
| POST | `/ai/chat` | 基于资料分块连续问答，返回引用 |
| GET | `/knowledge/sources` | 列出资料源 |
| GET | `/knowledge/sources/{id}` | 获取资料正文和元数据 |
| GET | `/knowledge/sources/{id}/artifacts` | 查询资料派生产物 |
| GET/PATCH | `/knowledge/artifacts/{id}` | 查看或修改学习产物 |
| GET | `/knowledge/search?q=...` | 跨资料本地检索 |

### 8.3 学习闭环、面试和评测

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/ai/study-plan` | 生成并保存学习计划 |
| GET | `/study-plans` | 列出学习计划 |
| PATCH | `/study-plans/{id}/days/{index}` | 更新每日完成状态 |
| POST | `/quiz/attempts` | 提交作答并更新错题 |
| GET | `/wrongbook` | 查询未掌握/已到期错题 |
| GET | `/review/today` | 聚合今日计划与到期错题 |
| POST | `/interviews` | 创建模拟面试 |
| GET | `/interviews/{id}` | 获取面试进度 |
| POST | `/interviews/{id}/answers` | 提交回答并评分 |
| GET | `/analytics/overview` | 获取真实学习行为统计 |
| POST | `/evaluation/feedback` | 保存匿名产品反馈 |
| GET | `/evaluation/feedback/summary` | 获取反馈摘要 |
| GET | `/evaluation/feedback/export.csv` | 导出匿名反馈 |

完整字段和边界见 [`filemate/docs/API_SPEC.md`](filemate/docs/API_SPEC.md)，交互调试访问 `http://127.0.0.1:8001/docs`。

## 9. 前端页面与对应能力

| 路由 | 页面 | 主要职责 |
|---|---|---|
| `/` | 学习工作台 | 汇总核心任务、资料和学习状态 |
| `/today` | 今日学习 | 聚合逾期/当日计划和到期错题 |
| `/import` | 导入文件 | 上传、处理进度与错误恢复 |
| `/classification` | 分类预览 | 修改分类和课程信息 |
| `/naming` | 命名预览 | 修改最终文件名 |
| `/schedule` | 日程预览 | 查看里程碑和日历内容 |
| `/history` | 历史记录 | Session、执行状态和撤销 |
| `/ai-tools` | AI 工具箱 | 摘要、卡片、题目、笔记、问答 |
| `/study-plan` | AI 学习计划 | 生成、查看和完成每日任务 |
| `/wrongbook` | 错题复盘 | 错题、掌握状态和复习安排 |
| `/interview` | 模拟面试 | 场景、回答、四维评分与反馈 |
| `/growth` | 成长数据 | 真实行为统计与匿名反馈导出 |
| `/knowledge` | 个人知识库 | 资料、产物、跨资料检索和编辑 |

视觉必须遵循“日光学习台”：浅色、低饱和自然绿、真实数据优先；不使用暗色主界面、紫粉 AI 渐变、Emoji 功能图标、虚构准确率或无意义机器人视觉。

## 10. 本地开发与运行

### 10.1 环境要求

- Windows 11 为主要开发平台；macOS/Linux 可运行 Web 与 CLI。
- Python 3.10+，推荐 3.11/3.12。
- Node.js 24（与 CI 对齐）。
- `uv`、Git；桌面端开发另需 Rust stable/MSVC。

### 10.2 Windows 一键启动

```powershell
# 首次：安装 Python 与前端依赖并检查环境
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup

# 后续：启动 FastAPI 和 Vue
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1

# 不自动打开浏览器
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -NoBrowser

# 停止本次启动的服务
powershell -ExecutionPolicy Bypass -File scripts/stop-dev.ps1

# 仅诊断环境
powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1
```

也可双击 `启动FileMate.bat`。启动后：

- Web：`http://127.0.0.1:5173`
- API：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`

### 10.3 手动启动

```powershell
# 项目根目录
uv sync --extra dev
Copy-Item .env.example .env
# 编辑 .env，填入真实 LLM 配置

# 终端 1
uv run python server.py

# 终端 2
Set-Location filemate/web
npm ci
npm run dev
```

### 10.4 CLI

```powershell
uv run python main.py <文件路径>
uv run python main.py <文件路径> --no-calendar
uv run python main.py --watch-dir <监控目录>
uv run python main.py --check --db _working/check.db
```

## 11. 环境变量与本地数据

不要提交真实 `.env`、API Key、个人资料、数据库或用户导出文件。

| 变量 | 默认值/要求 | 用途 |
|---|---|---|
| `LLM_PROVIDER` | `auto` | 根据 Base URL 选择 Provider |
| `LLM_API_KEY` | AI 功能需要 | 模型密钥 |
| `LLM_BASE_URL` | 例如 StepFun `/v1` | OpenAI 兼容 API 地址 |
| `LLM_MODEL` | 由供应商决定 | 模型名称 |
| `FILEMATE_DATA_DIR` | `<项目>/.filemate-data` | 本地应用数据根目录 |
| `FILEMATE_UPLOAD_DIR` | `<DATA_DIR>/inbox` | 上传暂存目录 |
| `FILEMATE_DB_PATH` | `<DATA_DIR>/filemate.db` | SQLite 文件 |
| `FILEMATE_ARCHIVE_DIR` | `<项目>/archive` | 最终归档目录 |
| `FILEMATE_SHUTDOWN_TOKEN` | 桌面宿主注入 | 只允许本机优雅关闭 Sidecar |
| `FILEMATE_INTERVIEW_LOCAL_ONLY` | `1` 时强制本地评分 | 面试隐私/离线模式 |

未配置模型密钥时，Web、历史、持久化和部分本地功能仍可启动；需要模型的能力应返回明确配置提示，不能静默伪造结果。

## 12. 测试、质量门禁与评测

```powershell
# 推荐：一次完成 Ruff、后端测试和前端生产构建
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1

# 后端非 e2e 测试
uv run pytest filemate/tests -q -m "not e2e"

# SQLite 多线程压力测试
uv run python filemate/tests/stress_test_storage.py

# 前端类型检查与生产构建
Set-Location filemate/web
npm run build

# 离线产品评测
Set-Location ../..
uv run python evaluation/run_evaluation.py --output _working/evaluation-report.json
```

2026-08-24 发布基线：

- 后端：`330 passed, 17 skipped, 5 deselected`。
- SQLite 压力测试：10 线程、5000 次操作、0 错误。
- Vue 类型检查和 Vite 生产构建通过。
- GitHub Actions 后端与前端任务通过。
- 安装包任务只在 `workflow_dispatch` 手动触发，不阻塞当前功能开发。

离线检索基线是小型合成数据，只用于工程回归。真实用户结论必须报告样本量、日期、数据属性和置信区间，禁止把示例 CSV 或演示数据冒充实测。

## 13. 如何扩展功能

### 13.1 新增文件解析器

1. 在 `filemate/perception/parsers/` 新建单一格式解析器。
2. 返回稳定的 `raw_text` 和 `metadata`。
3. 在解析器注册表中注册后缀；同步 `server.py` 上传白名单。
4. 增加正常文件、空文件、损坏文件和大文件测试。
5. 更新 README 支持格式与 API 文档。

### 13.2 新增 AI 学习工具

1. 在 `filemate/understanding/ai_tools.py` 或独立领域模块实现纯业务逻辑。
2. 通过 `LLMClient` 调模型，不在业务代码硬编码供应商或密钥。
3. 明确输入、结构化输出、失败降级和内容长度边界。
4. 在 `storage.py` 复用 Source/Artifact/Context；需要 schema 时新增迁移。
5. 在 `server.py` 增加统一响应路由，在 `api.ts` 增加类型化客户端。
6. 新增 Vue 页面/组件、路由、加载/空/错/重试状态和测试。

### 13.3 新增前端板块

1. 在 `src/views/` 建页面，在 `router/index.ts` 注册懒加载路由。
2. API 调用只放 `src/services/api.ts`，共享类型放 `src/types/`。
3. 复用 Pinia 状态，不把持久数据只放组件局部变量。
4. 遵循自然绿色设计系统，使用 `@element-plus/icons-vue`。
5. 验证桌面、900px 和 375px；状态不能只靠颜色表达。

### 13.4 新增 LLM/Embedding/数字人供应商

1. 先定义最小 Provider 协议和统一返回结构。
2. 在适配层实现，不让业务模块依赖供应商 SDK 类型。
3. 密钥只从环境变量读取；日志不得打印密钥、完整敏感资料或原始回答。
4. 提供超时、重试、错误翻译和本地/离线回退。
5. 用 contract test 验证替换供应商不会改变上层 API。

### 13.5 新增数据库迁移

1. 不修改已经发布的 v1–v8 迁移内容。
2. 新增 `_MIGRATIONS` 版本、幂等升级逻辑和索引。
3. 测试新库初始化、旧库升级、重复执行和失败回滚。
4. 更新 API_SPEC、README 数据模型和导出/删除边界。

## 14. 团队协作规则

### 14.1 建议分工

| 方向 | 主要路径 | 当前负责人/协作方式 |
|---|---|---|
| 总体架构、LLM、集成与发布 | `core/`、`llm_client/`、CI | 胡希统筹 |
| 感知与解析 | `perception/` | 汤新阳主责 |
| 理解、Prompt 与学习算法 | `understanding/` | 张金宝主责 |
| 执行、存储和可靠性 | `execution/` | 徐书和主责 |
| Vue UI/UX | `filemate/web/` | 余恒主责 |
| 产品、评测与跨模块联调 | `docs/`、`evaluation/`、各模块 | 杨乐及全体协作 |

实际任务以负责人最新分配为准；表格用于告诉 AI 从哪里找代码，不作为权限系统。

### 14.2 Git 与提交

```text
main
 ├─ feat/<模块>-<能力>
 ├─ fix/<模块>-<问题>
 └─ docs/<主题>
```

- 从最新 `main` 建短分支，提交小而完整的改动。
- Conventional Commit：`type(scope): 中文简述`。
- 不提交 `.env`、数据库、真实用户资料、`node_modules`、构建产物或 `_working`。
- 修改公共 API、schema、环境变量或路由时，必须同步代码、测试、README/API 文档和调用方。
- 合并前执行 `scripts/verify.ps1`；需要真实密钥的 e2e 测试单独标记。

## 15. AI 辅助开发接手模板

队友可以把下面内容直接交给 AI，再补充具体任务：

```text
你正在协助开发 FileMate（大学生本地优先 AI 学习工作台）。

开始前必须：
1. 完整阅读根目录 AGENTS.md、README.md。
2. 阅读 filemate/docs/API_SPEC.md，以及任务相关源码和测试。
3. 用当前 main 代码、SQLite migration、Vue 路由和测试核对文档，不把目标架构当现役实现。

开发约束：
- 保持 FastAPI + SQLite + Vue 3/Tauri 的现役技术栈。
- 所有高影响文件操作先预览确认，并保持冲突保护、回滚、幂等和撤销。
- AI 结果必须落到 Source/Artifact/Context 或学习证据中，不能只停留在前端内存。
- 新外部供应商必须走适配层，密钥只读环境变量，并有失败降级。
- 不制造虚假数据、准确率、画像或用户研究结果。
- 修改 API/schema/路由时同步客户端、测试和文档。
- 使用 apply_patch 修改文件；保留用户已有改动；不要删除无关文件。

完成前执行：
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1

最终报告：改动文件、用户影响、测试结果、已知限制、后续接口依赖。
```

## 16. 安全、隐私与产品边界

- 默认数据保存在本机 `.filemate-data` 和归档目录；模型请求仍可能把必要文本发送到配置的第三方模型，必须向用户说明。
- 上传文件名使用 basename，限制格式和 25 MB 大小，隔离同名上传目录。
- API 仅默认监听本机回环地址；桌面关闭接口需要随机令牌并限制本机来源。
- 文件操作必须防止路径穿越、Windows 保留名、非法字符、扩展名伪造和静默覆盖。
- 匿名反馈只保存哈希和必要上下文，不保存姓名、学号、联系方式或原始敏感文本。
- 真实评测资料必须获得授权；导出前进行脱敏。
- 不把规则评分包装成教师/招聘专家结论，不把合成集指标包装成真实准确率。

## 17. 已知限制与风险

| 风险/限制 | 当前处理 | 后续动作 |
|---|---|---|
| 模型网络或额度不可用 | 返回明确错误；部分功能有本地降级 | 增加 Provider 健康检查和成本记录 |
| 词法检索无法覆盖语义同义表达 | 返回可解释分数和引用 | 评测后再引入可替换 Embedding |
| OCR 在 Windows 为可选依赖 | 无 OCR 时跳过并提示 | 建立独立 OCR Sidecar 或云端适配层 |
| SQLite 适合单机，不适合多人并发 | WAL、busy timeout、写锁 | 只有多人协作需求确认后才评估 PostgreSQL |
| 面试本地评分较粗 | 明示降级，保留四维结构 | 与教师/导师盲评做相关性验证 |
| 桌面安装包尚未作为当前门禁 | 手动 workflow 保留 | 9 月稳定后决定是否纳入最终验收 |

## 18. 项目文档索引

| 文档 | 用途 | 状态 |
|---|---|---|
| [`filemate/docs/API_SPEC.md`](filemate/docs/API_SPEC.md) | 核心 Python 接口、HTTP API、可信执行合同 | 现役 |
| [`docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md`](docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md) | 其他 Agent 的分阶段任务卡、文件边界与验收合同 | 现役执行计划 |
| [`design-system/filemate/MASTER.md`](design-system/filemate/MASTER.md) | UI 色彩、布局、组件和禁止项 | 现役 |
| [`docs/PHASE0_ACCEPTANCE_REPORT.md`](docs/PHASE0_ACCEPTANCE_REPORT.md) | 可信执行与工程门禁证据 | 现役证据 |
| [`docs/FILEMATE_EVALUATION_BASELINE.md`](docs/FILEMATE_EVALUATION_BASELINE.md) | 离线可复现评测口径 | 现役证据 |
| [`docs/REAL_USER_EVALUATION_PROTOCOL.md`](docs/REAL_USER_EVALUATION_PROTOCOL.md) | 真实用户实验流程与门槛 | 待执行 |
| [`docs/FILEMATE_AI_PRODUCT_MASTER_PLAN.md`](docs/FILEMATE_AI_PRODUCT_MASTER_PLAN.md) | 学习、科研、竞赛、求职和数字人长期规划 | 长期规划 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Neo4j、GraphRAG、Agent 等 2.0 目标架构 | 目标设计，非现役 |
| [`evaluation/README.md`](evaluation/README.md) | 离线评测与用户研究脚本说明 | 现役 |
| [`filemate/web/README.md`](filemate/web/README.md) | Web/Tauri 开发与数据目录说明 | 现役 |

## 19. 当前团队

- 负责人：胡希
- 成员：汤新阳、张金宝、徐书和、余恒、杨乐

项目的核心评价标准不是“功能数量”，而是学生能否基于自己的资料完成一个可恢复、可解释、可持续复习的真实学习任务。
