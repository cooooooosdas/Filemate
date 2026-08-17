# FileMate 2.0 目标架构设计（规划）

> 版本：v1.1 | 作者：胡希 | 日期：2026-08-09
>
> 本文描述 2.0 长期目标，不是当前部署清单。现役架构以根目录 `README.md`、`server.py`、SQLite migrations 和 Vue 路由为准。当前使用 Vue 3 + FastAPI + SQLite v8 + 本地词法检索；Neo4j、向量数据库、GraphRAG、完整 Agent、认证、WebSocket 和云部署仍属于规划能力。

---

## 1. 系统整体架构

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        用户层                                                 │
│  ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐        │
│  │    Vue 3 Web 端       │     │   桌面端（Tauri）     │     │    命令行模式        │        │
│  │  - 自然绿亮色 UI      │     │  - 本地文件监听       │     │  - 单文件处理        │        │
│  │  - 实时状态展示       │     │  - 系统托盘           │     │  - watch 模式        │        │
│  │  - 知识图谱可视化     │     │  - 通知中心           │     │  - batch 处理        │        │
│  └──────────┬───────────┘     └──────────┬───────────┘     └──────────┬───────────┘        │
│             │                            │                            │                   │
│             └────────────────────────────┼────────────────────────────┘                   │
│                                          ↓                                                  │
│                               ┌─────────────────────┐                                      │
│                               │    API Gateway      │                                      │
│                               │  - FastAPI REST    │                                      │
│                               │  - WebSocket       │                                      │
│                               │  - 认证/鉴权        │                                      │
│                               │  - 限流/监控        │                                      │
│                               └──────────┬──────────┘                                      │
│                                          │                                                  │
└──────────────────────────────────────────┼──────────────────────────────────────────────────┘
                                           ↓
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       应用层                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              Pipeline 编排层                                          │   │
│  │  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐    ┌────────────────┐   │   │
│  │  │  文件入口      │ →  │  任务队列      │ →  │  Worker 消费   │ →  │  结果回调      │   │   │
│  │  │  - 批量导入    │    │  - asyncio    │    │  - 多阶段处理  │    │  - 通知用户    │   │   │
│  │  │  - 实时监控    │    │  - 优先级      │    │  - 错误重试    │    │  - 写入存储    │   │   │
│  │  │  - API 提交    │    │  - 并发控制    │    │  - 进度回调    │    │  - 触发后续    │   │   │
│  │  └────────────────┘    └────────────────┘    └────────────────┘    └────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                           ↓
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       核心处理层                                              │
│                                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │    感知层       │  │    理解层       │  │   知识图谱层    │  │    Agent 层     │          │
│  │  Perception    │  │  Understanding │  │  Knowledge Graph│  │    Agent       │          │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤          │
│  │                │  │                │  │                │  │                │          │
│  │ FileParser     │  │ Classifier     │  │ GraphBuilder   │  │ AgentCore      │          │
│  │ - PDF          │  │ - 规则引擎      │  │ - 实体识别     │  │ - 规划器       │          │
│  │ - Word         │  │ - LLM 分类      │  │ - 关系抽取     │  │ - 推理引擎     │          │
│  │ - PPT          │  │ - 置信度计算   │  │ - 知识融合     │  │ - 工具调度     │          │
│  │ - Image(OCR)   │  │                │  │                │  │                │          │
│  │                │  │ EntityExtractor│  │ GraphStore     │  │ GraphRAG       │          │
│  │ TableReader    │  │ - 课程抽取     │  │ - Neo4j 存储   │  │ - 图谱检索     │          │
│  │ - 表格结构      │  │ - 时间抽取     │  │ - 向量索引     │  │ - 上下文增强   │          │
│  │ - Markdown     │  │ - 主办方抽取   │  │ - 混合检索     │  │                │          │
│  │                │  │                │  │                │  │ ToolManager   │          │
│  │ ChartParser    │  │ MilestoneDetect│  │                │  │ - 文件操作    │          │
│  │ - 图表类型识别  │  │ - 多时间节点   │  │ GraphQuery    │  │ - 日程管理    │          │
│  │ - 结构化提取   │  │ - 去重/排序    │  │ - Cypher 查询  │  │ - 知识检索    │          │
│  │                │  │                │  │ - 向量搜索     │  │ - 外部 API    │          │
│  │ Embedding      │  │ Namer          │  │ - 混合召回     │  │                │          │
│  │ - 文本向量化   │  │ - 规范命名     │  │                │  │ Memory        │          │
│  │ - 批处理       │  │ - organizer 回退│ │                │  │ - 短期记忆    │          │
│  │                │  │                │  │                │  │ - 长期记忆    │          │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘          │
│           │                   │                    │                   │                  │
│           └───────────────────┼────────────────────┼───────────────────┘                  │
│                               ↓                    ↓                                       │
│                    ┌─────────────────────┐  ┌─────────────────────┐                        │
│                    │    执行层           │  │   成长模型层         │                        │
│                    │  Execution          │  │  Growth Model       │                        │
│                    ├─────────────────────┤  ├─────────────────────┤                        │
│                    │                     │  │                     │                        │
│                    │ FileOps             │  │ UserProfile          │                        │
│                    │ - move/copy/del    │  │ - 技能画像          │                        │
│                    │ - rename            │  │ - 学习轨迹          │                        │
│                    │ - hash 计算         │  │ - 目标设定          │                        │
│                    │                     │  │                     │                        │
│                    │ Archiver            │  │ KnowledgeState      │                        │
│                    │ - 目录规划          │  │ - 掌握度评估        │                        │
│                    │ - 规范化存储        │  │ - 遗忘曲线          │                        │
│                    │ - 元数据记录        │  │ - 短板分析          │                        │
│                    │                     │  │                     │                        │
│                    │ CalendarBuilder     │  │ Recommendation     │                        │
│                    │ - .ics 生成         │  │ - 个性化推荐        │                        │
│                    │ - RFC 5545 合规     │  │ - 成长路径规划      │                        │
│                    │                     │  │ - 复习提醒          │                        │
│                    └─────────────────────┘  └─────────────────────┘                        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                           ↓
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       数据层                                                  │
│                                                                                               │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐ │
│  │   SQLite          │  │    Neo4j          │  │   Chroma/         │  │   文件系统      │ │
│  │  (结构化数据)     │  │  (知识图谱)        │  │   Weaviate        │  │  (原始文件)     │ │
│  │                   │  │                   │  │  (向量存储)       │  │                 │ │
│  │ - sessions        │  │ - 实体节点         │  │ - text embeddings │  │ - 归档目录      │ │
│  │ - processed_files │  │ - 关系边           │  │ - image vectors   │  │ - 备份          │ │
│  │ - operation_log   │  │ - 属性             │  │ - 混合检索        │  │ - 缓存          │ │
│  │ - user_rules     │  │ - 图谱查询         │  │                   │  │                 │ │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘  └─────────────────┘ │
│                                                                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                           ↑
                                    ┌────────────────┐
                                    │   LLM 层       │
                                    ├────────────────┤
                                    │                │
                                    │ DeepSeek API  │
                                    │ Claude API    │
                                    │ GPT-4o        │
                                    │ BGE Embedding │
                                    │                │
                                    └────────────────┘
```

---

## 2. 模块边界定义

### 2.1 感知层（Perception）

**职责**：将各种格式的文件转换为统一的结构化表示

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `FileParser` | 统一入口，根据后缀选择解析器 | 文件路径 | `{"raw_text": str, "metadata": dict}` |
| `PDFParser` | 提取 PDF 文本、表格 | PDF 文件 | 文本 + 元数据 |
| `WordParser` | 提取 Word 文本、表格 | Docx 文件 | 文本 + 元数据 |
| `PPTParser` | 提取 PPT 文本、图表 | PPT 文件 | 文本 + 元数据 |
| `OCRBackend` | 图片 OCR 识别 | 图片文件 | 文本 |
| `TableReader` | 表格结构化 | 文本/文件 | `List[Table]` |
| `ChartParser` | 图表类型识别 | 文本/文件 | `Chart` 结构 |
| `Embedding` | 文本向量化 | 文本 | 向量 |

**接口规范**：
```python
# 文件解析接口
def parse(path: str) -> ParseResult:
    """ParseResult = {raw_text: str, metadata: {...}}"""

# 表格提取接口
def extract_tables(text: str) -> List[Table]:
    """Table = {headers: List[str], rows: List[List[str]]}}"""

# 向量化接口
def embed(text: str) -> List[float]:
    """返回归一化向量"""
```

---

### 2.2 理解层（Understanding）

**职责**：对文件内容进行语义理解和信息抽取

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `Classifier` | 文件分类（7类） | 文本 + 文件名 | `{category, confidence, course_name}` |
| `EntityExtractor` | 实体抽取 | 文本 | `{course, task, deadline, location, extra}` |
| `MilestoneDetector` | 多时间节点识别 | 长文本 | `[{event, date, order}]` |
| `Namer` | 生成规范文件名 | 分类+课程+任务+时间 | `"[课程]-[类型]-[任务]-[日期]-[状态]"` |

**接口规范**：
```python
# 分类接口
def classify(text: str, filename: str = "") -> ClassificationResult:
    """ClassificationResult = {category, confidence, course_name, method}"""

# 实体抽取
def extract(raw_text: str) -> Entities:
    """Entities = {course_name, task_description, deadline, location, extra_entities}"""

# 里程碑检测
def detect(raw_text: str) -> List[Milestone]:
    """Milestone = {event: str, date: str, order: int}"""

# 命名生成
def generate(category, course, task, deadline, status="待处理") -> str:
    """返回规范文件名"""
```

---

### 2.3 知识图谱层（Knowledge Graph）

**职责**：构建和管理个人知识图谱，支持语义检索

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `GraphBuilder` | 从实体构建图谱 | 实体列表 | 图谱节点/边 |
| `GraphStore` | 图数据库操作 | Cypher/参数 | 查询结果 |
| `GraphQuery` | 图谱检索 | 查询语句 | 实体/关系 |
| `VectorStore` | 向量存储与检索 | 向量+元数据 | 相似结果 |

**接口规范**：
```python
# 添加实体
def add_entity(entity: Entity) -> str:
    """返回实体 ID"""

# 添加关系
def add_relation(from_id: str, to_id: str, relation: str) -> str:
    """返回关系 ID"""

# 语义检索
def search(query: str, top_k: int = 5) -> List[SearchResult]:
    """返回相关实体列表"""

# 路径查询
def find_path(start: str, end: str) -> List[Path]:
    """返回两点间路径"""
```

---

### 2.4 Agent 层（Agent）

**职责**：智能代理，基于知识图谱进行推理和规划

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `AgentCore` | Agent 核心编排 | 用户请求 | 响应 + 动作 |
| `Planner` | 任务分解 | 复杂目标 | 子任务列表 |
| `Reasoner` | 推理引擎 | 上下文 | 推理结果 |
| `ToolManager` | 工具调度 | 工具名+参数 | 工具结果 |
| `GraphRAG` | 图增强检索 | 查询 | 上下文 |
| `Memory` | 记忆管理 | 事件 | 记忆状态 |

**接口规范**：
```python
# Agent 执行
def run(request: str, context: dict = None) -> AgentResponse:
    """AgentResponse = {output: str, actions: List[Action], memory: dict}"""

# 工具调用
def call_tool(tool_name: str, **kwargs) -> Any:
    """返回工具执行结果"""

# 图谱增强
def enhance_with_graph(query: str) -> str:
    """返回增强后的上下文"""
```

---

### 2.5 成长模型层（Growth Model）

**职责**：用户画像和个性化推荐

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `UserProfile` | 用户画像 | 学习行为 | 画像数据 |
| `KnowledgeState` | 知识状态 | 图谱数据 | 掌握度 |
| `Recommender` | 个性化推荐 | 用户画像 | 推荐列表 |

**接口规范**：
```python
# 更新画像
def update_profile(user_id: str, event: Event) -> Profile:
    """返回更新后的画像"""

# 知识评估
def assess_knowledge(user_id: str, topic: str) -> KnowledgeState:
    """返回知识点掌握状态"""

# 推荐
def recommend(user_id: str, context: dict = None) -> List[Recommendation]:
    """返回推荐列表"""
```

---

### 2.6 执行层（Execution）

**职责**：执行具体的文件操作和持久化

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `FileOps` | 文件操作 | 操作类型+参数 | 结果 |
| `Archiver` | 文件归档 | 文件+规则 | 目标路径 |
| `CalendarBuilder` | 日程生成 | 事件列表 | .ics 文件 |
| `Storage` | 数据持久化 | 数据 | 写入结果 |

**接口规范**：
```python
# 文件操作
def move(src: str, dest: str) -> OpResult:
    """OpResult = {success: bool, dest_path: str, error: str}"""

# 归档
def archive(session: Session, rule: ArchiveRule) -> OpResult:
    """返回归档结果"""

# 日程生成
def build_calendar(milestones: List[Milestone], output: str) -> str:
    """返回 .ics 文件路径"""
```

---

## 3. 数据流设计

### 3.1 主数据流（文件处理）

```
用户上传文件
    ↓
┌─────────────────┐
│  感知层        │  1. FileParser.parse() → raw_text + metadata
│  Perception    │  2. TableReader.extract() → tables
└────────┬────────┘  3. ChartParser.parse() → charts
         │           4. Embedding.embed() → vectors
         ↓
┌─────────────────┐
│  理解层        │  1. Classifier.classify() → category + confidence
│  Understanding │  2. EntityExtractor.extract() → entities
└────────┬────────┘  3. MilestoneDetector.detect() → milestones
         │           4. Namer.generate() → suggested_name
         ↓
┌─────────────────┐
│  执行层        │  1. Storage.create_session() → session_id
│  Execution     │  2. Archiver.archive() → file moved
└────────┬────────┘  3. CalendarBuilder.build() → .ics generated
         │
         ├────────────────────────────────────────┐
         ↓                                        ↓
┌─────────────────┐                    ┌─────────────────┐
│  知识图谱层     │                    │  UI 层          │
│  Knowledge Graph│                    │  显示结果       │
│                 │                    │  等待用户确认    │
└─────────────────┘                    └─────────────────┘
         ↑
         │（可选：存储到图谱）
         │
┌─────────────────┐
│  后续 Agent 调用 │
│  （主动规划）   │
└─────────────────┘
```

### 3.2 Agent 数据流（智能问答）

```
用户提问
    ↓
┌─────────────────┐
│  Agent Core     │  1. 解析用户意图
│  理解请求       │  2. 判断是否需要工具调用
└────────┬────────┘
         │
    ┌────┴────┐
    ↓         ↓
┌────────┐ ┌─────────────────┐
│ 知识检索 │ │  工具调度        │
│ GraphRAG│ │  ToolManager     │
└───┬────┘ └────────┬────────┘
    │                │
    ↓                ↓
┌─────────────────┐ ┌─────────────────┐
│  图谱上下文     │ │  工具执行结果   │
│  + 向量检索     │ │  FileOps/其他   │
└────────┬────────┘ └────────┬────────┘
         │                   │
         └─────────┬─────────┘
                   ↓
         ┌─────────────────┐
         │  LLM 生成响应   │
         │  (带图谱上下文)  │
         └────────┬────────┘
                  ↓
         ┌─────────────────┐
         │  存入记忆       │
         │  Memory.update │
         └────────┬────────┘
                  ↓
              返回给用户
```

### 3.3 成长模型数据流

```
周期性触发 / 事件驱动
    ↓
┌─────────────────┐
│  学习行为事件   │
│  - 文件上传    │
│  - 问答记录    │
│  - 里程碑完成  │
└────────┬────────┘
         ↓
┌─────────────────┐
│  UserProfile   │  更新用户画像
│  更新          │
└────────┬────────┘
         ↓
┌─────────────────┐
│  KnowledgeState │  计算知识掌握度
│  计算          │
└────────┬────────┘
         ↓
┌─────────────────┐
│  Recommender   │  生成推荐
│  推荐          │
└────────┬────────┘
         ↓
┌─────────────────┐
│  主动通知      │
│  - 复习提醒    │
│  - 规划建议    │
└─────────────────┘
```

---

## 4. 模块间接口汇总

| 调用方 | 被调用方 | 接口方法 | 数据格式 |
|--------|----------|----------|----------|
| Pipeline | Perception | `parse(path)` | 文件路径 → 结构化文本 |
| Pipeline | Understanding | `classify(text)` | 文本 → 分类结果 |
| Pipeline | Understanding | `extract(text)` | 文本 → 实体 |
| Pipeline | Execution | `archive(session)` | 会话 → 文件移动 |
| Agent | KnowledgeGraph | `search(query)` | 文本 → 实体列表 |
| Agent | Execution | `call_tool(name, args)` | 工具名+参数 → 结果 |
| GrowthModel | KnowledgeGraph | `get_profile(user)` | 用户ID → 画像 |
| GrowthModel | Agent | `recommend(user)` | 用户 → 推荐列表 |

---

## 5. 技术选型说明

| 组件 | 选型 | 理由 |
|------|------|------|
| 图数据库 | Neo4j | 成熟稳定，支持 Cypher，生态完善 |
| 向量数据库 | Chroma / Weaviate | 轻量、易用、支持混合检索 |
| LLM | DeepSeek (主力) + Claude (前沿) | 成本可控 + 能力互补 |
| Embedding | BGE | 中文效果好，开源免费 |
| Agent 框架 | LangChain | 生态丰富，易于扩展 |
| 前端 | Vue 3 + Element Plus | 团队熟悉，组件丰富 |
| 后端 | FastAPI | 性能好，自动文档 |
| 部署 | Docker + Vercel | 轻量、快速 |

---

## 6. 扩展性设计

- **新增文件格式**：在 `Perception` 添加新 Parser 类
- **新增 Agent 工具**：在 `ToolManager` 注册新工具
- **更换 LLM Provider**：实现 `BaseLLMProvider` 接口
- **更换向量数据库**：实现 `BaseVectorStore` 接口

---

*文档版本：v1.1 | 最后更新：2026-08-09 | 状态：目标设计，非现役实现*
