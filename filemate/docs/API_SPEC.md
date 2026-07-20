# API 规范

> 5 个核心接口的输入输出契约。
>
> - 4.1 分类模块接口
> - 4.2 实体抽取模块接口
> - 4.3 多里程碑识别模块接口
> - 4.4 命名生成模块接口
> - 4.5 执行层接口
>
> W4 里程碑（2026-08-03）后冻结，变更必须经过胡希。

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
| `confidence` | `float` | 置信度 `[0.0, 1.0]`；规则命中单次 ≥ 0.83 |
| `course_name` | `str \| None` | 识别的课程名，未识别则为 `None` |
| `reason` | `str` | 分类依据（规则命中 / LLM 返回原文） |

**调用示例：**

```python
result = classifier.classify(text="实验三：实现一个线程池...", filename="lab3.docx")
# {"category": "作业", "confidence": 0.83, "course_name": None, "reason": "关键词规则命中"}
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
- `task` 长度 > 20 字 → 尝试 LLM 精简，失败则硬截断到 20 字
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
| `source_path` | `str \| Path \| None` | 否 | 源文件路径，默认取 session 原始路径 |

**Output（`OpResult` dataclass）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | `bool` | 是否成功 |
| `error` | `str` | 错误信息，成功则为空字符串 |
| `dest_path` | `str` | 目标路径（绝对路径），失败则为空字符串 |
| `source_path` | `str` | 源路径 |

**目标路径格式：**

```
<base_dir>/<course>/<category>/<new_name>
```

**边界行为：**
- `category` 不在合法集合 → 强制改为 `"待确认"`
- `course` 空/None → 归入 `"未分类"` 目录
- 目标目录不存在 → 自动创建
- 目标已存在同名文件 → `FileOps.move` 按系统行为处理（Windows 会覆盖，POSIX 会报错）

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

**依赖：** `icalendar>=6.0`（可选，未安装时 `build()` 抛 `RuntimeError`，`save()` 同理）

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

**表结构（四张表 + 索引）：**

```
sessions
  session_id TEXT PK, source_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','processing','done','confirmed','skipped','expired','failed')),
  category TEXT, confidence REAL, suggested_name TEXT,
  entities TEXT (JSON), milestones TEXT (JSON),
  error TEXT, created_at TEXT, updated_at TEXT

processed_files
  file_hash TEXT PK, session_id TEXT REFERENCES sessions, first_seen TEXT

operation_log
  id INTEGER PK AI, session_id TEXT REFERENCES sessions,
  op TEXT NOT NULL, detail TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))

user_rules
  id INTEGER PK AI, category TEXT NOT NULL, keyword TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT
```

**索引：** `idx_sessions_status`, `idx_operation_log_sid`

**线程安全：** 每个线程持有独立 `sqlite3.Connection`，WAL 模式，`foreign_keys=ON`。

#### 常用方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `init_schema` | `() -> None` | 建表（幂等） |
| `create_session` | `(session_id: str, source_path: str) -> None` | 插入新 session |
| `update_session` | `(session_id: str, **kwargs) -> None` | 更新任意字段（自动写 `updated_at`） |
| `get_session` | `(session_id: str) -> dict \| None` | 按 ID 查询 |
| `list_sessions` | `(status: str \| None = None) -> list[dict]` | 列表，按 `created_at` 降序 |
| `is_duplicate` | `(file_hash: str) -> bool` | 文件是否已处理过 |
| `record_hash` | `(file_hash: str, session_id: str) -> None` | 记录哈希（自动建占位 session） |
| `log_operation` | `(session_id: str, op: str, detail: str = "") -> None` | 写操作日志 |
| `get_operations` | `(session_id: str) -> list[dict]` | 读操作日志 |
| `add_rule` | `(category: str, keyword: str, weight: float = 1.0) -> int` | 新增用户规则 |
| `list_rules` | `(active_only: bool = True) -> list[dict]` | 列出规则 |

**边界行为：**
- `update_session` 空 `kwargs` → 无操作
- `record_hash` 如果 `session_id` 不存在 → 自动插入占位记录（`/test/{session_id}`），避免 FK 报错

---

## 变更记录

| 日期 | 版本 | 内容 | 作者 |
|---|---|---|---|
| 2026-07-14 | v0.1 | 创建占位文件 | 胡希 |
| 2026-07-15 | v1.0 | 根据实现写入具体签名 | 胡希 |
