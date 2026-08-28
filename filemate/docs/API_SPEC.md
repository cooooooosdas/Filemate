# API 规范

> 核心 Python 模块与现役 HTTP API 的输入输出契约。
>
> - 4.1 分类模块接口
> - 4.2 实体抽取模块接口
> - 4.3 多里程碑识别模块接口
> - 4.4 命名生成模块接口
> - 4.5 执行层接口
> - 4.6 AI 学习资产 HTTP API
> - 4.7 可信确认、执行与撤销 API
>
> 2026-08-31 初步版本前允许在测试和调用方同步更新的前提下迭代；2026-09-27 Release Candidate 起冻结，后续破坏性变更必须经过项目负责人确认。

---

## 4.1 分类模块接口

**模块：** `filemate.understanding.classifier.Classifier`

**实例化：**

```python
from filemate.understanding.classifier import Classifier

classifier = Classifier(llm_client=llm)
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `llm_client` | `LLMClient` | 统一 LLM 客户端，来自 `filemate.llm_client` |

### `classify(text, filename="") -> dict[str, Any]`

**语义：** 给定文件文本和可选文件名，返回最可能的分类。

**Input：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | `str` | 是 | 文件提取出的纯文本 |
| `filename` | `str` | 否 | 原始文件名，用于 LLM 上下文 |

**Output（dict）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `category` | `str` | 分类结果，取值为 `{"课件", "作业", "竞赛通知", "考试通知", "参考资料", "大创通知", "待确认"}` |
| `confidence` | `float` | 置信度 `[0.0, 1.0]`；规则命中从 0.65 起，最高 0.92 |
| `course_name` | `str \| None` | 识别的课程名，未识别则为 `None` |
| `reason` | `str` | 分类依据（规则命中 / LLM 返回原文） |
| `method` | `str` | 分类方式：`"rule"` 规则命中 / `"llm"` LLM 推断 / `"none"` 空文本 |

**调用示例：**

```python
result = classifier.classify(text="实验三：实现一个线程池...", filename="lab3.docx")
# {"category": "作业", "confidence": 0.75, "course_name": None, "reason": "关键词规则命中"}
```

**边界行为：**
- `text` 为空/空白 → 直接返回 `{"category": "待确认", "confidence": 0.0, "course_name": None, "reason": "空文本"}`
- LLM 调用异常 → 同上，`reason` 携带异常信息
- `category` 不在合法集合 → 强制改写为 `"待确认"`

---

## 4.2 实体抽取模块接口

**模块：** `filemate.understanding.entity_extractor.EntityExtractor`

**实例化：**

```python
from filemate.understanding.entity_extractor import EntityExtractor

extractor = EntityExtractor(llm_client=llm)
```

### `extract(text) -> dict[str, Any]`

**语义：** 从文件文本中抽取课程名、任务描述、截止时间等结构化信息。

**Input：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | `str` | 是 | 文件提取出的纯文本（前 4000 字符送入 LLM） |

**Output（dict）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `course_name` | `str \| None` | 课程名 |
| `task_description` | `str \| None` | 任务描述 |
| `deadline` | `"YYYY-MM-DD" \| None` | 截止日期，格式不合法时置 `None` |
| `location` | `str \| None` | 地点（如有） |
| `extra_entities` | `dict` | 其他任意字段，LLM 可自由补充 |

**调用示例：**

```python
entities = extractor.extract(text)
# {"course_name": "操作系统", "task_description": "实验三：线程池",
#  "deadline": "2026-05-20", "location": None, "extra_entities": {}}
```

**边界行为：**
- 空文本 → 所有字段 `None` / `{}`
- LLM 异常 → 同上
- `deadline` 格式不符 `YYYY-MM-DD` → 丢弃该字段，置 `None`

---

## 4.3 多里程碑识别模块接口

**模块：** `filemate.understanding.milestone_detector.MilestoneDetector`

**实例化：**

```python
from filemate.understanding.milestone_detector import MilestoneDetector

detector = MilestoneDetector(llm_client=llm)
```

### `detect(text) -> list[dict[str, Any]]`

**语义：** 从竞赛通知、大创通知等长文本中识别多个时间节点。

**Input：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | `str` | 是 | 文件全文（前 6000 字符送入 LLM） |

**Output（list[dict]）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `event` | `str` | 事件名称 |
| `date` | `"YYYY-MM-DD"` | 事件日期 |
| `order` | `int` | 发生顺序（用于排序） |

**调用示例：**

```python
milestones = detector.detect(text)
# [
#   {"event": "报名截止", "date": "2026-05-10", "order": 1},
#   {"event": "初赛", "date": "2026-05-25", "order": 2},
#   {"event": "决赛", "date": "2026-06-15", "order": 3},
# ]
```

**边界行为：**
- 空文本 → `[]`
- LLM 返回非数组 → `[]`
- 单条记录缺 `event` 或 `date` 格式不符 → 丢弃该条
- 输出按 `order` 升序排列

---

## 4.4 命名生成模块接口

**模块：** `filemate.understanding.namer.Namer`

**实例化：**

```python
from filemate.understanding.namer import Namer

namer = Namer(llm_client=llm)
```

### `generate(*, category, course, task, deadline, status="待处理") -> str`

**语义：** 根据分类与实体信息，生成规范文件名（不含扩展名）。

**Input（keyword-only）：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `category` | `str` | 是 | — | 课件 / 作业 / 竞赛通知 / 考试通知 / 参考资料 / 大创通知 / 待确认 |
| `course` | `str` | 是 | — | 课程名 |
| `task` | `str` | 是 | — | 任务描述 |
| `deadline` | `str` | 是 | — | `"YYYY-MM-DD"` 或 `"MMDD"`，空字符串 → `"待定"` |
| `status` | `str` | 否 | `"待处理"` | 状态 |

**Output：**

```
[课程]-[类型]-[任务]-[截止]-[状态]
```

不含扩展名。总长度不超过 80 字符；超长时优先截断 `course` 和 `task`。

**调用示例：**

```python
name = namer.generate(
    category="作业",
    course="操作系统",
    task="实验三：实现线程池",
    deadline="2026-05-20",
)
# "[操作系统]-[作业]-[实验三：实现线程池]-[0520]-[待处理]"
```

**边界行为：**
- `category` 不在合法集合 → 强制改写 `"待确认"`
- `course`/`task`/`status` 空字符串 → 替换为 `"未分类"` / `"未命名"` / `"待处理"`
- `task` 长度 > 15 字 → 尝试 LLM 精简，失败则硬截断到 15 字
- 文件名总长度 > 80 → 截断 `course` 到 10 字、`task` 到 10 字，仍超则再截到 6 字

---

## 4.5 执行层接口

执行层提供三条独立子接口：文件归档（`Archiver`）、日历生成（`CalendarBuilder`）、SQLite 持久化（`SQLiteStorage`）。

### 4.5.1 归档接口 `Archiver`

**模块：** `filemate.execution.archiver.Archiver`

```python
from filemate.execution.archiver import Archiver
from filemate.execution.file_ops import FileOps

archiver = Archiver(base_dir="./archive", file_ops=FileOps())
```

#### `archive(session_id, category, course, new_name, source_path=None) -> OpResult`

**Input：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `session_id` | `str` | 是 | 对应 session 的 ID |
| `category` | `str` | 是 | 课件 / 作业 / 竞赛通知 / 考试通知 / 参考资料 / 大创通知 / 待确认 |
| `course` | `str` | 是 | 课程名 |
| `new_name` | `str` | 是 | 目标文件名（不含路径） |
| `source_path` | `str \| Path \| None` | 否 | 参数形式为兼容旧调用保留；实际归档必须传入有效源文件路径 |

**Output（`OpResult` dataclass）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | `bool` | 是否成功 |
| `error` | `str` | 错误信息，成功则为空字符串 |
| `dest_path` | `str` | 目标路径（绝对路径），失败则为空字符串 |

**目标路径格式：**

```
<base_dir>/<course>/<category>/<new_name>
```

**边界行为：**
- `category` 不在合法集合 → 强制改为 `"待确认"`
- `course` 空/None → 归入 `"未分类"` 目录
- 目标目录不存在 → 自动创建
- 目标已存在同名文件 → 明确拒绝覆盖并返回失败，源文件保持不变

#### `preview_dest(base_dir, category, course, new_name) -> Path`

只返回目标路径，不执行移动。供 UI 预览用。

---

### 4.5.2 日历生成接口 `CalendarBuilder`

**模块：** `filemate.execution.scheduler.CalendarBuilder`

```python
from filemate.execution.scheduler import CalendarBuilder, CalendarEvent

builder = CalendarBuilder()
```

#### `build(events: Sequence[CalendarEvent]) -> bytes`

将事件列表序列化为 RFC 5545 兼容的 `.ics` 字节串。

**`CalendarEvent` dataclass：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `summary` | `str` | 是 | — | 事件标题 |
| `start` | `str` | 是 | — | 开始时间，`"YYYY-MM-DD"` 或 `"YYYY-MM-DDTHH:MM"` |
| `end` | `str \| None` | 否 | `None` | 结束时间，格式同上；`None` 则开始时间 +1h |
| `location` | `str` | 否 | `""` | 地点 |
| `description` | `str` | 否 | `""` | 描述 |

**Output：** `bytes` — `.ics` 文件内容

**依赖：** 项目依赖 `icalendar>=6.0`；运行环境缺失时 `build()` 和 `save()` 抛 `RuntimeError`。

#### `save(events, out_path) -> Path`

等价于 `Path(out_path).write_bytes(build(events))`，返回输出 `Path`。

---

### 4.5.3 持久化接口 `SQLiteStorage`

**模块：** `filemate.execution.storage.SQLiteStorage`

```python
from filemate.execution.storage import SQLiteStorage

storage = SQLiteStorage(db_path="filemate.db")
storage.init_schema()
```

**数据库版本：** `schema_migrations` 记录已应用迁移，当前 schema 为 v9。`init_schema()` 可对旧数据库安全、幂等升级。

**核心表：**

| 表 | 说明 |
|---|---|
| `sessions` | 文件处理生命周期、分类、实体、里程碑与人工修改状态 |
| `processed_files` | SHA-256 去重记录与处理次数 |
| `operation_log` | 操作、人工覆盖、模型、延迟与 token 审计信息 |
| `user_rules` | 分类覆盖、命名模板、课程别名等规则 |
| `workspaces` | 用户学习工作区，默认包含 `local` |
| `sources` | 统一资料源、解析正文、媒体类型与元数据 |
| `artifacts` | 摘要、知识卡、题目、笔记、学习计划等 AI 产物 |
| `document_contexts` | 持久化文档上下文、聊天历史与可选过期时间 |
| `execution_records` | 最终确认、失败、撤销、快照和幂等状态 |
| `document_chunks` | 带页码和顺序的可引用资料分块 |
| `quiz_attempts` | 用户作答、得分和反馈证据 |
| `wrong_questions` | 错题、掌握状态和间隔重复参数 |
| `interview_sessions` / `interview_turns` | 模拟面试流程与评分记录 |
| `interview_questions` | 可维护面试题库、启停状态与场景/难度过滤 |
| `study_plans` | 学习计划、每日完成状态和考试目标 |
| `product_feedback` | 匿名产品反馈哈希与统计上下文 |

**线程安全：** 每个线程持有独立 `sqlite3.Connection`，开启 WAL、`busy_timeout=10000` 和 `foreign_keys=ON`；写操作由进程内可重入锁串行保护。

#### 常用方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `init_schema` | `() -> None` | 应用版本迁移（幂等） |
| `get_schema_version` | `() -> int` | 读取当前数据库版本 |
| `create_session` | `(session_id: str, source_path: str) -> None` | 插入新 session |
| `update_session` | `(session_id: str, **kwargs) -> None` | 更新允许字段（自动写 `updated_at`） |
| `get_session` | `(session_id: str) -> dict \| None` | 按 ID 查询 |
| `list_sessions` | `(status: str \| None = None, limit: int = 100) -> list[dict]` | 列表，按 `created_at` 降序 |
| `is_duplicate` | `(file_hash: str) -> bool` | 文件是否已处理过 |
| `record_hash` | `(file_hash: str, session_id: str) -> None` | 记录哈希（自动建占位 session） |
| `log_operation` | `(session_id: str, action: str, detail: str = "", ...) -> int` | 写操作日志并返回 ID |
| `get_operations` | `(session_id: str) -> list[dict]` | 读操作日志 |
| `add_rule` | `(rule_type: str, pattern: str, replacement: str, priority: int = 0) -> int` | 新增用户规则 |
| `list_rules` | `(rule_type: str \| None = None, enabled_only: bool = True) -> list[dict]` | 列出规则 |
| `save_source` | `(*, original_name, source_path, raw_text="", ...) -> str` | 新增或按哈希更新资料源 |
| `save_artifact` | `(*, artifact_type, content, source_id=None, ...) -> str` | 保存资料派生的 AI 产物 |
| `save_document_context` | `(*, ctx_id, context_text, ...) -> None` | 保存可恢复问答上下文 |
| `append_context_messages` | `(ctx_id, messages) -> list[dict]` | 原子追加并返回聊天历史 |
| `list_interview_questions` | `(*, scenario=None, difficulty=None, enabled=None, limit=100) -> list[dict]` | 筛选面试题库 |
| `create_interview_question` | `(*, scenario, difficulty, text, enabled=1) -> str` | 新增题目；重复内容拒绝 |

**边界行为：**
- `update_session` 空 `kwargs` → 无操作
- `record_hash` 如果 `session_id` 不存在 → 自动插入 `__auto_created__` 占位记录，避免 FK 报错
- 同工作区、同文件哈希会稳定复用同一个 `source_id`

---

## 4.6 AI 学习资产 HTTP API

所有接口使用统一响应：`{"success": bool, "data": any, "error": str | null}`。

HTTP 错误同样保持该结构：参数错误使用 `400/422`，资源不存在使用 `404`，执行冲突使用 `409`，AI 上游失败使用 `502`。前端必须读取 `error` 字段，不依赖 FastAPI 默认的 `detail`。

| 方法 | 路径 | 作用 | 持久化结果 |
|---|---|---|---|
| `POST` | `/ai/summarize` | 生成摘要 | `Source + summary Artifact + Context` |
| `POST` | `/ai/knowledge-cards` | 生成知识卡 | `Source + knowledge_cards Artifact + Context` |
| `POST` | `/ai/questions` | 生成练习题 | `Source + questions Artifact + Context` |
| `POST` | `/ai/notes` | 生成结构化笔记 | `Source + notes Artifact + Context` |
| `POST` | `/ai/study-plan` | 生成个性化复习计划 | `Source + study_plan Artifact + Context` |
| `POST` | `/ai/chat` | 基于资料连续问答 | 追加 `document_contexts.chat_history` |
| `GET` | `/ai/contexts` | 列出最近问答会话摘要 | `limit` 范围 1–200，不返回正文和完整历史 |
| `GET` | `/ai/contexts/{ctx_id}` | 恢复单个问答会话 | 返回完整上下文、历史消息与结构化引用 |
| `GET` | `/knowledge/sources` | 列出本地资料源 | 不返回大段 `raw_text`，返回 `text_length` |
| `GET` | `/knowledge/sources/{source_id}` | 获取资料源详情 | 包含解析正文与元数据 |
| `GET` | `/knowledge/sources/{source_id}/artifacts` | 查询资料派生产物 | 支持 `artifact_type` 与 `limit` |
| `DELETE` | `/knowledge/sources/{source_id}` | 预览并删除资料及其派生产物 | 级联删除派生数据；仅清理托管上传副本 |

AI 生成接口成功时同时返回 `ctx_id`、`source_id`、`artifact_id`。服务重启后，这三个标识仍然有效。`POST /ai/chat` 将 assistant 消息的 `citations` 与正文一并持久化，恢复历史会话后仍可核验引用来源。

---

## 4.7 可信确认、执行与撤销 API

分类编辑和最终执行已拆开，避免用户尚未修改文件名时提前移动文件。

| 方法 | 路径 | 作用 | 文件系统副作用 |
|---|---|---|---|
| `PATCH` | `/sessions/{session_id}` | 保存分类、名称或实体草稿 | 无 |
| `POST` | `/sessions/{session_id}/confirm` | `accepted=true` 最终执行；`false` 跳过 | 归档文件，按需生成 `.ics` |
| `POST` | `/sessions/{session_id}/undo` | 撤销当前已应用执行 | 文件恢复原位置，移除本次 `.ics` |
| `GET` | `/sessions/{session_id}/executions` | 查询执行、失败与撤销历史 | 无 |

最终确认具备以下不变量：

- 目标文件或日历已存在时拒绝覆盖。
- 归档和日历任一步失败时自动恢复原文件。
- 重复确认返回原 `execution_id`，不重复移动。
- 重复撤销返回已撤销记录，不重复修改文件系统。
- 文件扩展名不可借重命名改变，目录名和文件名经过路径穿越防护。
- Session、执行记录和审计日志在同一个 SQLite 事务内完成。

确认响应中的 `execution` 包含 `execution_id`、`status`、`source_path`、`dest_path`、`ics_path`、`can_undo` 和 `idempotent`。

---

## 4.7.1 知识资料删除语义

`DELETE /knowledge/sources/{source_id}` 提供「预览 → 确认 → 删除」的安全资料生命周期：

- **预览**：删除前返回受影响的 `artifacts`、`chunks`、`contexts`、`quiz_attempts`、`wrong_questions`、`study_plans` 数量。
- **级联删除**：依赖 SQLite 外键 `ON DELETE CASCADE`，删除 `sources` 行后派生数据不可查询；其他 Source 不受影响。
- **托管副本清理**：仅当 `source_path` 位于 `FILEMATE_UPLOAD_DIR` 内（`resolve()` 后仍在其下）时，才随删除清理物理文件；符号链接与路径穿越逃逸到目录外的文件不会被删除。
- **外部文件保护**：用户原始文件、归档文件及其他 Source 引用文件绝不删除，返回 `external_files_untouched=true`。
- **幂等**：重复删除返回 `404`，不重复清理；托管文件已不存在时返回 `exists=false, removed=false`，仍视为成功。

---

## 4.8 文件处理、知识库与学习闭环补充 API

下表按 `server.py` 现役路由整理，用于补齐 4.6/4.7 未覆盖的接口。

| 方法 | 路径 | 作用 | 持久化/副作用 |
|---|---|---|---|
| `POST` | `/process` | 上传并处理单个文件 | 保存 `.filemate-data/inbox`，写入 Session |
| `GET` | `/sessions` | 查询历史 Session | 无 |
| `GET` | `/sessions/{session_id}` | 获取 Session 详情 | 无 |
| `GET` | `/sessions/{session_id}/ics` | 获取确认后的 `.ics` 内容 | 无 |
| `GET` | `/knowledge/artifacts/{artifact_id}` | 获取单个 AI 产物 | 无 |
| `PATCH` | `/knowledge/artifacts/{artifact_id}` | 更新产物标题与内容 | 写入 `artifacts` |
| `DELETE` | `/knowledge/sources/{source_id}` | 预览并删除资料及其派生产物 | 级联删除；仅清理 `FILEMATE_UPLOAD_DIR` 内托管副本 |
| `GET` | `/knowledge/search` | 跨资料检索 | 无 |
| `POST` | `/quiz/attempts` | 提交作答并判题 | 写入 `quiz_attempts`，更新错题 |
| `GET` | `/wrongbook` | 查询错题列表 | 无 |
| `GET` | `/review/today` | 今日复习队列 | 无 |
| `GET` | `/study-plans` | 查询学习计划列表 | 无 |
| `GET` | `/study-plans/{plan_id}` | 查询单个学习计划 | 无 |
| `PATCH` | `/study-plans/{plan_id}/days/{day_index}` | 更新每日完成状态 | 写入 `study_plans.completed_days` |
| `POST` | `/interviews` | 创建模拟面试 | 写入 `interview_sessions` |
| `GET` | `/interviews/{interview_id}` | 获取面试进度 | 无 |
| `POST` | `/interviews/{interview_id}/answers` | 提交面试回答并评分 | 写入 `interview_turns` |
| `GET` | `/interview/questions` | 列出面试题库题目 | 支持 `scenario` / `difficulty` / `enabled` 过滤，`limit` 上限 500 |
| `POST` | `/interview/questions` | 新增题库题目 | 写入 `interview_questions` |
| `PATCH` | `/interview/questions/{question_id}` | 更新题库题目 | 更新 `interview_questions` |
| `DELETE` | `/interview/questions/{question_id}` | 删除题库题目 | 删除 `interview_questions` |
| `GET` | `/analytics/overview` | 成长数据聚合 | 无 |
| `POST` | `/evaluation/feedback` | 提交匿名产品反馈 | 写入 `product_feedback` |
| `GET` | `/evaluation/feedback/summary` | 反馈汇总 | 无 |
| `GET` | `/evaluation/feedback/export.csv` | 导出匿名反馈 CSV | 无 |
| `GET` | `/api/health` | 健康检查 | 无 |

说明：`POST /interviews` 创建面试时按场景和难度选择最近维护的启用题目，响应和持久化记录均包含与 `questions` 等长的 `question_ids`；静态回退题及 v8 旧会话对应 `null`。评分响应新增 `scoring_mode`，取值为 `llm` 或 `local_fallback`。

---

## 变更记录

| 日期 | 版本 | 内容 | 作者 |
|---|---|---|---|
| 2026-07-14 | v0.1 | 创建占位文件 | 胡希 |
| 2026-07-15 | v1.0 | 根据实现写入具体签名 | 胡希 |
| 2026-08-09 | v1.1 | 增加版本迁移、学习资产持久化与 HTTP API | Codex |
| 2026-08-09 | v1.2 | 增加确认执行、操作快照、幂等保护与撤销 API | Codex |
| 2026-08-09 | v1.3 | 校准当前 v8 数据模型、归档冲突策略与线程安全说明 | Codex |
| 2026-08-16 | v1.4 | 补齐现役 HTTP 路由表，修正命名阈值 20→15 | 杨乐 |
| 2026-08-26 | v1.5 | 增加 SQLite v9 面试题库、CRUD 与选题来源合同 | YL / Codex |
| 2026-08-28 | v1.6 | 增加 AI 会话列表与恢复合同、结构化引用持久化和列表限流 | AcMaster-MAX / Codex |
