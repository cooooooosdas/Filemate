# API 规范

> 核心 Python 模块与现役 HTTP API 的输入输出契约。

2026-10-04 首页接入外部[一言诗词API](https://developer.hitokoto.cn/sentence/)：前端`services/api.ts`发起HTTPS GET `https://v1.hitokoto.cn/?c=i&encode=json&min_length=8&max_length=22`，仅读取`uuid/hitokoto/type/from/from_who`，不携带Cookie、Referer、资料或学习内容。没有新增本服务路由、环境变量或schema。请求2.5秒超时，每次页面加载最多一次，同次SPA切页共享结果；允许的外部CSP连接仅为该端点。

正文须为8–22字、类型为`i`且UUID有效；无效响应、HTTP错误/429和断网回退到最多24条已验证格式的本机缓存或已核对出处的经典备用句，作者缺失不补写。只取JSON并以Vue文本节点显示，不使用接口的JS输出。来源归属按一言记录展示，外链使用官方UUID详情地址；不将语句库审核等同于逐句学术校勘。协议及离线句出处见设计系统/本次交付记录。
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

**数据库版本：** `schema_migrations` 记录已应用迁移，当前 schema 为 v25。`init_schema()` 可对旧数据库安全、幂等升级。

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
| `coding_submissions` / `coding_events` | 编程提交索引、状态、幂等键与最小操作日志；提交内容复用 `coding_submission` 类型 Artifact |
| `document_contexts` | 持久化文档上下文、聊天历史与可选过期时间 |
| `execution_records` | 最终确认、失败、撤销、快照和幂等状态 |
| `document_chunks` | 带页码和顺序的可引用资料分块 |
| `quiz_attempts` | 用户作答、得分和反馈证据 |
| `wrong_questions` | 错题、掌握状态和间隔重复参数 |
| `interview_sessions` / `interview_turns` | 模拟面试流程与评分记录 |
| `interview_questions` | 可维护面试题库、启停状态与场景/难度过滤 |
| `interview_review_state` / `interview_review_events` | V2.4 面试分析修订、报告引用、有限操作事件 |
| `career_positions` / `career_trainings` / `career_events` | V2.5 岗位修订、训练 Artifact 索引与有限操作记录 |
| `study_plans` | 学习计划、每日完成状态和考试目标 |
| `product_feedback` | 匿名产品反馈哈希与统计上下文 |
| `agent_runs` / `agent_steps` | 按需选择的 Agent 角色、真实步骤、来源标识与输出摘要 |
| `agent_memories` | 四类可撤销摘要记忆及其来源、可用角色和删除状态 |
| `source_rights` | 资料权利来源、分享范围与确认时间 |

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
| `get_source_lineage` | `(source_id) -> dict \| None` | 聚合资料、产物、练习、错题、计划和关联面试计数，不返回原文 |
| `save_artifact` | `(*, artifact_type, content, source_id=None, ...) -> str` | 保存资料派生的 AI 产物 |
| `save_document_context` | `(*, ctx_id, context_text, ...) -> None` | 保存可恢复问答上下文 |
| `append_context_messages` | `(ctx_id, messages) -> list[dict]` | 原子追加并返回聊天历史 |
| `list_interview_questions` | `(*, scenario=None, difficulty=None, enabled=None, limit=100) -> list[dict]` | 筛选面试题库 |
| `create_interview_question` | `(*, scenario, difficulty, text, enabled=1) -> str` | 新增题目；重复内容拒绝 |
| `create_agent_run` | `(*, task_type, goal, selected_agents, context_refs=None) -> dict` | 创建可审计 Agent 运行 |
| `append_agent_step` | `(*, run_id, agent_name, input_refs, output_summary, status="completed") -> dict` | 追加真实执行步骤，不保存输入原文 |
| `save_agent_memory` | `(*, memory_type, scope_id, source_type, source_id, summary, allowed_agents, ...) -> dict` | 保存带来源和使用范围的摘要记忆 |
| `set_source_rights` | `(*, source_id, rights_status, sharing_scope="private", note="") -> dict` | 声明资料授权与分享边界 |

**边界行为：**
- `update_session` 空 `kwargs` → 无操作
- `record_hash` 如果 `session_id` 不存在 → 自动插入 `__auto_created__` 占位记录，避免 FK 报错
- 同工作区、同文件哈希会稳定复用同一个 `source_id`

---

## 4.6 AI 学习资产 HTTP API

所有接口使用统一响应：`{"success": bool, "data": any, "error": str | null}`。

HTTP 错误同样保持该结构：参数错误使用 `400/422`，资源不存在使用 `404`，执行冲突使用 `409`，AI 上游失败使用 `502`。前端必须读取 `error` 字段，不依赖 FastAPI 默认的 `detail`。

部署模板的TLS网关对已声明超过32 MiB的请求体在传输前返回统一JSON `413`，并对读取正文设置32 MiB上限；文件自身仍受后端25 MiB限制。分块传输中途超限可能终止连接，客户端需保留输入并允许重试。HTML和API使用`Cache-Control: no-store`，内容哈希资源长期缓存，本地视觉模型/WASM使用`no-cache`校验更新。`/knowledge`、`/wrongbook`、`/interview`、`/goals`、`/trust`同时作为页面和API入口，只有这些精确路径的HTML导航交给前端；其余API不因`Accept: text/html`而变成页面。实际部署复核见[网关交付](../../docs/GATEWAY_PREFLIGHT_DELIVERY_2026-10-03.md)。

生产环境默认启用 `FILEMATE_IDENTITY_MODE=anonymous`，同时支持游客和邮箱账号。未登录时签发 `HttpOnly`、`Secure`、`SameSite=Lax` 的签名设备 Cookie；账号使用独立的 `filemate_session` 不透明会话 Cookie，前端请求必须使用 `withCredentials=true`。资料继续按独立 SQLite、上传和归档目录隔离，跨身份资源统一返回 `404`。游客清除 Cookie 后无法恢复原身份；账号换设备登录可恢复资料空间。开发和桌面 Sidecar 默认 `local` 模式，无需账号且禁止创建网站账户。

### 邮箱账号与恢复码（alpha.4 / schema v25）

所有账号 `POST` 必须为 JSON，附 `X-FileMate-Action: account`，并遵守 Origin 白名单。响应为统一信封且 `Cache-Control: no-store`。主 SQLite 追加 `accounts`、`account_sessions`、`account_attempts`；业务资料留在原独立目录。没有新增环境变量或邮件服务。

| 方法 | 路径 | 输入与输出 |
|---|---|---|
| GET | `/api/auth/me` | `user`（账号ID、邮箱、昵称、创建时间）或 null；`enabled`、`expired` |
| POST | `/api/auth/register` | `email`、`display_name`、`password`、`keep_guest_data=true`、`remember=true`；返回 `user` 和仅此次显示的 `recovery_code`，设置会话 Cookie |
| POST | `/api/auth/login` | `email`、`password`、`remember=true`；返回 `user`，轮换当前设备会话 |
| POST | `/api/auth/logout` | `{}`；撤销当前设备会话并删除 Cookie；重复退出幂等 |
| POST | `/api/auth/recover` | `email`、`recovery_code`、新 `password`；更换密码、撤销全部会话并返回新的恢复码；旧码不能复用，需重新登录 |

邮箱去首尾空格并 casefold，暂不验证邮件归属，因此不是已验证联系方式。昵称2–30字符，注册和恢复的新密码为9–128字符，必须同时包含英文字母`A–Z/a–z`及数字`0–9`，不要求大小写混合，符号和中文可作为附加字符；常见或明显重复的密码继续拒绝。登录仅验证已存密码摘要，不按新规则拒绝已有密码。scrypt `N=32768,r=8,p=3` 独立随机盐，最多两个并发密码派生。恢复码和会话为256位随机令牌，数据库仅存SHA-256摘要，秘密不进入客户端持久存储。勾选保持登录使用30天有效Cookie，否则为浏览器会话Cookie且服务端最长12小时；每账号最多10个活跃设备会话。登录/注册/恢复分别每邮箱15分钟最多10次；Nginx认证动作另限每IP20次/分钟、突发8次，`me`和退出不计此额度。

注册可显式选择把当前游客空间归入账号；保留时只原子绑定目录、不复制或删除资料，已绑定空间的旧游客Cookie立即失去访问权。取消保留则创建新账号空间，退出后可回到原游客空间。登录已有账号不会合并游客资料。过期/撤销会话的业务请求返回401，禁止悄悄写入新的游客空间；`me`、健康和账号端点可继续使用。页面路由为 `/login`、`/register`、`/recover`；恢复码须保存后才进入学习空间。

完整备份必须同时包含主库、`identity.secret` 和用户分库/托管资料。恢复演练保留密码摘要、恢复码摘要及账号归属。发布允许完整旧迁移之后追加v25；开放账号写入后禁止回退到只识别游客的alpha.3，否则旧游客凭证会绕过账号归属检查。回退必须保留账号服务和v25，不能以旧快照覆盖新写入。

携带 `Origin` 的状态变更请求只接受 `FILEMATE_CORS_ORIGINS` 白名单来源。资料 API 不返回 `source_path`、`workspace_id` 等服务器内部字段；`.ics` 只允许从当前身份已应用的执行记录读取，且路径必须位于该身份归档目录内。

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
| `POST` | `/knowledge/import` | multipart `file` 仅本地解析入库，无模型调用；按哈希复用已有源；支持原课件格式及UTF-8 Markdown/代码文本 | 返回过滤内部路径后的 Source 详情，失败/重复上传清理此次副本 |
| `POST` | `/knowledge/sources/{source_id}/contexts` | 从已有资料新建可恢复会话，不自动生成内容 | Context；不覆盖旧对话 |
| `POST` | `/knowledge/sources/{source_id}/artifacts` | JSON `artifact_type` 为 summary/notes/knowledge_cards/questions；`count` 为 1–10（默认5，上限非保证数量），必须明确 `allow_external_model=true` | Artifact 绑定原 Source；笔记/卡片/摘要输入最多前12000字，练习沿用现役出题链前2500字；metadata 标记覆盖范围与截断；生成失败502且不保存，资料在生成期间删除409 |
| `GET` | `/knowledge/sources/{source_id}` | 获取资料源详情 | 包含解析正文与元数据，不返回服务器绝对路径和内部工作区字段 |
| `GET` | `/knowledge/sources/{source_id}/artifacts` | 查询资料派生产物 | 支持 `artifact_type` 与 `limit` |
| `GET` | `/knowledge/sources/{source_id}/lineage` | 查询六阶段学习资产链 | 只聚合真实持久化记录，不返回原文 |
| `DELETE` | `/knowledge/sources/{source_id}` | 预览并删除资料及其派生产物 | 级联删除派生数据；仅清理托管上传副本 |
| `PUT` | `/knowledge/sources/{source_id}/rights` | 声明资料来源与分享范围 | 写入 `source_rights`、安全 Agent 轨迹和操作记忆 |

AI 生成接口成功时同时返回 `ctx_id`、`source_id`、`artifact_id`。服务重启后，这三个标识仍然有效。`POST /ai/chat` 将 assistant 消息的 `citations` 与正文一并持久化，恢复历史会话后仍可核验引用来源。

2026-10-03 DEV-01：`/knowledge/import`在PDF/DOC/DOCX/PPT/PPTX/TXT之外增加`.md/.markdown/.c/.cpp/.h/.hpp/.py/.java/.js/.ts`，后缀不区分大小写；新增格式按UTF-8纯文本读取，不渲染HTML、不执行/编译源码，不调用模型。最大25MiB，现役解析器最多保留前500000字符；空白或编码错误返回422且清理此次上传，其他后缀400。原文与块引用沿用Source/Context，内容哈希相同仍复用首次资料；`/process`与原AI文件上传的格式合同保持原六种，不因学习入口扩展而改变。没有新增API、schema或环境变量。

学习工作区 `/ai-tools` 以「资料 / 对话 / 学习内容」切换资料目录和阅读区；笔记、卡片、练习、摘要为四个直接任务入口，卡片和练习显示5/10的数量上限选项，仍遵守上述1–10 API合同。已有内容默认进入阅读模式，点击「创建学习内容」才展开生成配置；首次添加且没有产物时直接显示四种任务。生成和解释在页面共用明确模型授权；打开资料、已有产物、引用和新建会话不调用模型。选择已有产物将 `artifact` 写入当前 `source` / `ctx` URL，切换产物保留正在编辑的问题及当前页面内的练习状态；重新打开时恢复已入库内容、完整对话与引用，模型授权重新确认。本轮练习标记及未发送问题不作为持久记录，离开/切换资料提供舍弃确认，顶部刷新和进行中的操作提供保护。无新增业务API、schema或生产环境开关。

---

## 4.7 可信确认、执行与撤销 API

分类编辑和最终执行已拆开，避免用户尚未修改文件名时提前移动文件。

2026-10-03前端将分类与命名合为一个资料审核模块：`/classification?session=...`和旧`/naming?session=...`均加载同一页面。可在一次`PATCH`中保存分类、名称和日程开关草稿，或核对同屏预览后用一次`POST /sessions/{id}/confirm`提交`edits`并归档；两个阶段的副作用合同保持独立。`entities.calendar_enabled=false`表示本次不生成日历。已归档字段锁定，需先撤销再编辑。没有新增HTTP端点、数据表或环境变量。

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
| `PATCH` | `/knowledge/artifacts/{artifact_id}` | 更新产物标题与内容；历史题集只读 | 写入 `artifacts`；修订有学习历史的题集时原子保存旧版快照 |
| `DELETE` | `/knowledge/sources/{source_id}` | 预览并删除资料及其派生产物 | 级联删除；仅清理 `FILEMATE_UPLOAD_DIR` 内托管副本 |
| `GET` | `/knowledge/search` | 跨资料检索 | 无 |
| `POST` | `/quiz/attempts` | 提交作答并判题；核对题目快照 | 写入 `quiz_attempts`，更新错题；修订冲突409不写入 |
| `GET` | `/wrongbook` | 查询错题列表，包含知识点标识、错因、来源与置信度 | 无 |
| `PATCH` | `/wrongbook/{wrong_id}/diagnosis` | 用户确认或修正错因，可附最多 300 字备注 | 更新错题诊断；依赖旧诊断的目标任务会失效 |
| `GET` | `/review/today` | 根据计划、到期错题、用户时间预算与顺序返回今日队列 | 无 |
| `PUT` | `/review/today/preferences` | 保存今日可用时长（10–240 分钟）和手动任务顺序 | 写入 `daily_coach_preferences`，返回重算后的队列 |
| `GET` | `/study-plans` | 查询学习计划列表 | 无 |
| `GET` | `/study-plans/{plan_id}` | 查询单个学习计划 | 无 |
| `PATCH` | `/study-plans/{plan_id}/days/{day_index}` | 更新每日完成状态 | 写入 `study_plans.completed_days` |
| `POST` | `/goals/reverse-plan` | 从目标和当前学习证据反推缺口与任务；选定资料有未掌握错题时附加口头解释任务及证据引用 | 写入 `reverse_goal_plan` Artifact、Agent 轨迹和摘要记忆 |
| `GET` | `/goals` | 列出已保存的目标反推计划，并实时标记证据已失效的口头训练任务 | 无 |
| `PATCH` | `/goals/{goal_id}/tasks/{task_id}` | 更新目标任务完成状态；证据失效时返回 409 | 更新目标 Artifact |
| `POST` | `/goals/{goal_id}/replan` | 读取最新证据重新规划、保留仍有效的已完成任务，并归档旧建议失效原因 | 更新目标 Artifact 和 Agent 轨迹 |
| `POST` | `/interviews` | 创建模拟面试或知识讲解训练；可选 `focus_wrong_id` 将同一资料的未掌握错题作为首题 | 写入 `interview_sessions` 与 Agent 来源引用 |
| `GET` | `/interviews/{interview_id}` | 获取面试进度 | 无 |
| `POST` | `/interviews/{interview_id}/answers` | 提交面试回答并评分；语音回答可附流畅度指标 | 写入 `interview_turns` 与 `fluency_metrics` |
| `GET` | `/interview/questions` | 列出面试题库题目 | 支持 `scenario` / `difficulty` / `enabled` 过滤，`limit` 上限 500 |
| `POST` | `/interview/questions` | 新增题库题目 | 写入 `interview_questions` |
| `PATCH` | `/interview/questions/{question_id}` | 更新题库题目 | 更新 `interview_questions` |
| `DELETE` | `/interview/questions/{question_id}` | 删除题库题目 | 删除 `interview_questions` |
| `GET` | `/analytics/overview` | 成长数据聚合 | 无 |
| `POST` | `/evaluation/feedback` | 提交匿名产品反馈 | 写入 `product_feedback` |
| `GET` | `/evaluation/feedback/summary` | 反馈汇总 | 无 |
| `GET` | `/evaluation/feedback/export.csv` | 导出匿名反馈 CSV | 无 |
| `GET` | `/trust/overview` | 获取角色目录、真实运行轨迹、共享记忆元数据与授权状态 | 无 |
| `PUT` | `/knowledge/sources/{source_id}/rights` | 更新资料授权与分享范围 | 写入授权、安全 Agent 轨迹和操作记忆 |
| `DELETE` | `/agents/memories/{memory_id}` | 撤销一条共享记忆 | 软删除记忆并记录安全 Agent 轨迹 |
| `GET` | `/api/health` | 健康检查 | 无 |
| `GET` | `/settings/llm` | 读取 DeepSeek 配置状态，不返回密钥 | 仅允许本机回环地址 |
| `PUT` | `/settings/llm` | 保存当前用户自己的 DeepSeek 密钥 | 写入操作系统安全凭据库；不进入数据库 |
| `DELETE` | `/settings/llm` | 删除当前用户保存的 DeepSeek 密钥 | 删除系统凭据；环境变量配置不受影响 |

2026-10-04网站自带密钥合同：公网不开放上述本机凭据管理接口，Nginx继续屏蔽`/settings/*`；生产/匿名模式即使经过回环代理也禁止修改系统共享密钥。网页使用以下接口，并在当前浏览器的IndexedDB中按`credential_scope`加密保存经测试有效的密钥。

| 方法 | 路径 | 含义 | 边界 |
| --- | --- | --- | --- |
| `GET` | `/api/llm/status` | 当前部署模型状态、学习空间凭据作用域 | 不返回任何密钥；`credential_scope`为当前私有空间标识的SHA256 |
| `POST` | `/api/llm/test` | 一次小额真实模型请求，返回`verified`与`latency_ms` | 需受信Origin及`X-FileMate-Action: model`；失败不保存候选密钥、不替换原配置 |

自带密钥通过`X-FileMate-LLM-Key`请求头传递，仅允许POST模型生成路由：`/process`、六项`/ai/*`生成/问答、资料产物生成、图谱草稿、面试创建/作答/内容分析、代码AI复盘及连接测试。上传入库、编译器判题、读取、账号登录等请求不携带密钥。服务端请求上下文隔离凭据，结束后复原；不得写`os.environ`或全局Client，不得无效密钥回退到共享密钥。该凭据强制DeepSeek官方HTTPS地址，禁止跟随HTTP重定向；网络及供应商错误不回显原响应。DeepSeek的401/402/403在连接测试中映射到本站502并显示原因，不触发FileMate登录过期跳转。

浏览器密文使用AES-256-GCM、新随机IV、作用域附加认证数据及不可导出的CryptoKey；事务完成才算保存，恢复浏览器后仍可读取；移除只删除当前空间记录。不写localStorage/sessionStorage，不随账号同步到其他设备。该方式仍依赖浏览器及同源脚本可信，不能等同于系统凭据库对XSS/本机入侵的保护。清除站点数据、隐私模式或浏览器存储权限被禁用可能使本机密钥不可恢复，需重新填写。

说明：`POST /interviews` 创建面试时按场景和难度选择最近维护的启用题目，响应和持久化记录均包含与 `questions` 等长的 `question_ids`；静态回退题及 v8 旧会话对应 `null`。评分响应包含 `scoring_mode`，取值为 `llm` 或 `local_fallback`。

`POST /interviews` 的 `scenario` 还支持 `知识讲解`。可选 `focus_wrong_id` 必须与 `source_id` 同时提供，且错题属于该资料并尚未掌握；否则返回 422。可选 `goal_id` 必须指向同一资料、同一错题且证据仍有效的现有目标任务。目标口头任务在 `evidence_ref` 保存 `artifact_id`、题号、`attempt_id`、作答时间、题目指纹、资料内容指纹和错因诊断指纹，不保存用户答案或参考答案；出现更新的失败作答、资料或题目变化、错因修正、错题掌握时，任务以 `invalidated` 返回并要求重排。首题只使用题干，不包含参考答案。知识讲解暂不产生未经校准的内容分数，回答仅在本地记录并返回 `local_fallback`；该资料授权未确认时，其他场景的聚焦错题回答也不向外部模型发送。来自目标的训练完成整场后只将“口头解释”任务标为已完成，不自动将错题标为掌握。

口头任务的 `source_evidence` 使用本地 BM25 风格词法排序，从同一 `source_id` 的 `document_chunks` 中选择一个可核对片段，返回 `status`、`method`、`chunk_id`、从零开始的 `chunk_index`、可选 `page_number`、分数和片段指纹，但不复制片段正文。目标 Agent 与面试 Agent 只消费引用 ID；前端将序号转换为从一开始的“片段 N”。没有词法重叠时返回 `status=unavailable` 和人工核对提示，不生成虚假页码或片段。已引用片段被替换、删除或转移到其他资料时，旧任务失效并要求重新规划。

错题在 v16 保存 `knowledge_key`、`knowledge_label`、`error_cause`、`error_cause_source`、`error_cause_confidence`、`error_cause_note` 和 `diagnosed_at`。`knowledge_key` 由资料 ID 和持久化题目的知识点标签确定，只保证同一资料范围内稳定；不同课程不会因标签相同而合并。系统仅使用本地规则生成低置信度初始建议，用户通过诊断接口保存的选择优先，后续错误作答不会覆盖用户确认。

`GET /review/today` 默认按 60 分钟预算返回最多 8 项，响应包括 `available_minutes`、`recommended_minutes`、`deferred_count`、`item_order`。优先级从计划日期、错题到期时间、错误次数及用户已确认的错因推导；规则建议的错因明确标记“待核对”。超过预算的任务暂不排入当日队列，不修改原计划或错题记录。`PUT /review/today/preferences` 仅保存当前日期的预算和顺序；更改后立即重算，次日恢复默认预算。用户顺序优先于系统排序，任务消失或完成时自动从当日候选队列过滤。

语音回答可以在请求中附带可选字段：

```json
{
  "answer": "我先分析问题，再制定方案并完成验证。",
  "fluency_metrics": {
    "duration_seconds": 18,
    "filler_count": 1,
    "long_pause_count": 0,
    "source": "speech_recognition"
  }
}
```

服务端根据回答字数和时长重新计算字速，并把流畅度作为 15% 的低权重参考分写入 `dimensions.流畅性`；文字回答或不足 2 秒的语音不会生成流畅度结论。摄像头与麦克风录像只保存在当前浏览器页的 Blob URL 中，不上传、不写入业务数据库，刷新即清除；时间轴只持久化口头语/长停顿的类型与时间点。面试创建和逐题评价同时写入真实 Agent 轨迹；轨迹只保存题号、会话 ID 和评分摘要，不复制回答原文。资料驱动面试仅在资料权利确认为本人、授权或公开时向模型发送最多 2000 字符摘录，否则只使用本地文件名。

---

## 4.9 V2.1 数字人讲解 API

页面 `/digital-human` 使用浏览器 `Web Speech` 合成语音，不调用服务端 TTS；播放日志仅保存最小元数据。前端 `digital-human/provider.ts` 定义 Provider 接口，当前实现为 `web_speech`，可在不改动学习业务的前提下替换后续供应商。语音事件只驱动近似口型动画，并非音素级同步。浏览器或系统声线可能联网，不能保证 TTS 完全离线。

V2.1.1 不增加 HTTP 接口或数据库迁移。数字人日志客户端请求限制为 15 秒；语音分段等待启动最多 15 秒，已开始分段的超时为 `max(30000, UTF-16长度 × 600 / 语速 + 15000)` 毫秒。暂停期间不计时，继续后恢复剩余预算。停止、替换讲解及终态会释放计时器并忽略旧事件；失败可重试。页面在 `ctx`/`message` 变化时重新加载答案，加载失败的重试重新请求原答案。终态日志同步失败时保留当前页面的重试队列，不重新播放或重复创建记录；离开或刷新页面后队列不保留，未同步记录仍按“播放中或未正常结束”展示。

| 方法 | 路径 | 作用 | 边界 |
|---|---|---|---|
| `GET` | `/api/digital-human/playbacks?limit=30` | 读取当前身份的播报元数据 | `limit` 1–100；不返回正文或音频 |
| `POST` | `/api/digital-human/playbacks` | 记录开始播报 | `text_length` 1–5000，`avatar_id` 为已发布形象，`provider=web_speech`；可选 `context_id` 与 `message_index` 必须成对出现且指向当前身份已保存的 assistant 消息 |
| `PATCH` | `/api/digital-human/playbacks/{playback_id}` | 记录 `completed` / `stopped` / `failed` | 只有 `started` 可转终态；重复及晚到请求不覆盖既有终态 |
| `DELETE` | `/api/digital-human/playbacks/{playback_id}` | 软删除单条记录 | 重复删除返回 `deleted=false`；不影响其他学习数据 |
| `POST` | `/api/digital-human/playbacks/{playback_id}/restore` | 撤销记录删除 | 重复恢复返回 `restored=false`；不重新播放语音 |

`POST` 请求只提交字数、形象、声线、Provider 以及可选的会话引用，不提交手动输入的正文。若绑定会话，服务端验证消息角色和最新正文长度；长度变化时返回 409，前端提示重新打开。记录含 `created_at`、`updated_at` 和 `module_version=2.1`；身份由所在本地/匿名租户数据库隐式确定，不复制用户标识到表内。`FILEMATE_ENABLE_DIGITAL_HUMAN=0` 时仅这些接口返回 503；前端构建变量 `VITE_ENABLE_DIGITAL_HUMAN=false` 可关闭页面和入口，旧讲解链接返回学习工作区。SQLite v17 独立新增 `digital_human_playbacks` 表，停用模块不影响 v1–v16 的数据与路由。

---

## 4.10 V2.2 个人知识图谱 API

页面 `/knowledge-graph` 从当前身份的 Source 正文提取知识点和关系。`mode=local` 只处理本地明确写出的标题、定义与关系句；`mode=llm` 必须提交 `allow_external_model=true`，最多发送正文前 20,000 字符给当前配置的模型。两种方式均要求每个节点与关系带连续逐字原文；服务端拒绝无出处、悬空关系、不同术语 ID 冲突、超限和空结果。模型结果仅存为待确认草稿。

模型提取先执行同一原文校验。若结构或出处不合格，最多再请求一次依据原文重新提取，每次调用限时45秒；第二次仍不合格则失败，不删除无效关系来伪装成功，也不改写原文。关系出处必须逐字包含两端的术语，避免“有序数组”与“数组有序”等词序混用。

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/knowledge-graph` | 当前身份已确认、未失效的节点与关系、批次历史、实时练习证据、`profile` 画像和最近100条 `events`；无作答显示待评测 |
| `POST` | `/api/knowledge-graph/drafts` | 请求 `{source_id,mode,allow_external_model}`；提取并持久化待确认批次；失败只记录错误类型，返回 422/502 |
| `POST` | `/api/knowledge-graph/batches/{id}/confirm` | 确认草稿；资料变更、状态冲突或节点 ID 冲突返回 409 |
| `POST` | `/api/knowledge-graph/batches/{id}/undo` | 撤销草稿或已确认批次；不删除原资料、题目或作答；重复操作幂等 |
| `POST` | `/api/knowledge-graph/batches/{id}/restore` | 恢复已撤销批次，重新检查资料版本与 ID 冲突 |
| `GET` | `/api/knowledge-graph/nodes/{id}/plan` | 沿已确认前置/依赖关系预览路径，返回作答证据指纹 `evidence_revision` |
| `POST` | `/api/knowledge-graph/nodes/{id}/plan` | 请求 `{evidence_revision}`；证据未变化时原子新增现役 StudyPlan 与 Artifact，相同请求幂等且不覆盖已有计划 |
| `POST` | `/api/knowledge-graph/plans/{id}/undo`、`/restore` | 仅归档/恢复本模块生成的计划，保留每日完成进度 |

SQLite v18 新增 `knowledge_graph_batches`，绑定 Source 并随资料删除级联清理。节点、关系、引用原文、来源版本与提取状态保存在批次 `payload`；资料正文或分块变化后旧批次标记 `stale`，不进入当前图谱。掌握状态为现役 QuizAttempt/WrongQuestion 的只读汇总：最近 10 次正确率、样本量、最近练习时间与错题数；无样本不构造百分比，学习时长未采集显示“待评测”。图谱建议须由用户确认才写入 StudyPlan。`FILEMATE_ENABLE_KNOWLEDGE_GRAPH=0` 返回 503；`VITE_ENABLE_KNOWLEDGE_GRAPH=false` 隐藏前端入口。当前实现是 SQLite 本地图谱，并未接入 Neo4j 或 GraphRAG。

V2.2 本次加固新增 SQLite v21 `knowledge_graph_events`，与业务变更在同一事务中提交。只保存 Source、目标 ID、操作、状态、证据指纹、错误类型及时间，不复制正文或供应商异常详情；幂等重试不重复记录，删除资料时级联清理，删除预览计数包含该表。旧批次不补造历史。关闭前端模块后，旧地址 `/knowledge-graph` 重定向学习工作区。

`profile` 是当前已确认图谱的只读投影，返回 `node_count`、`observed_node_count`、`unassessed_node_count`、`attempt_count`、`pending_wrong_count`、`excluded_sample_count`、`status_counts`、`weaknesses` 和 `study_time=null`。没有匹配本图谱知识点的作答不进入统计。`weaknesses` 返回知识点/资料 ID、规则依据 `reasons` 及需核对的前置知识和关系原文，不推断学科整体能力。提醒由未掌握错题、至少3次且最近10次正确率低于50%、30天无作答触发；先判断30天风险，再判断高频错误、10次且正确率≥90%的熟练、至少5次且正确率≥80%的基本掌握。样本不足5次显示“样本较少”。状态规则是学习提醒，不是能力测量。

节点 `metrics` 补充 `recent_sample_count`、`days_since_review`、`pending_wrong_count`、`excluded_sample_count`。异常时间、未来时间或非法判题字段不进入有效样本；完整历史错误次数与当前待复习错题分别计数。JSON/字段结构损坏的批次保留原库内容，以 `data_error=true`、空展示 payload 和错误类型返回，暂停确认/恢复并允许撤销；不会阻断健康批次与来源资料。计划证据指纹只依赖推荐路径涉及的节点和关系，相关证据改变返回409，无关关系变化不使其失效。

本地规则还可识别“X作为Y的一个特例”和“X通常用于实现Y”等限定句式，保留完整原句作为依据；否定或不确定词不会当作术语后缀生成肯定关系。关系复杂、资料没有显式结构时应由用户核对后选择模型提取。2026-10-01图谱阶段复用原课件/TXT解析链；2026-10-03 DEV-01在学习入口增加UTF-8 Markdown及代码文本，详见4.6的格式清单与限制。图片/OCR尚未在学习上传入口开放，旧版Office仍取决于本机解析依赖。

### 题目修订与学习证据

修改 `questions` Artifact 正文时，若已有作答或错题，在同一 SQLite 写事务中新增旧正文的 questions Artifact，并将旧作答与错题关联到该快照；原记录 ID、答案、诊断和复习进度不删除。快照 metadata 包含 `read_only_snapshot=true`、`question_revision_parent` 和保存时间，标题带“历史题集”。`PATCH` 不能修改快照，但仍可导出和复练；新作答继续关联旧题。新正文保留原 Artifact ID，首次答错形成新错题记录，不继承旧知识点的错误次数或诊断。操作失败整体回滚，标题修改不产生快照。无新增数据库 migration。

`POST /quiz/attempts` 接受 `{artifact_id,question_index,user_answer,expected_question?}`，`expected_question` 是页面加载时的原始题目 JSON（不是前端格式化后的题目）。当前所有答题入口均发送该快照。正文已修订的活动题集必须提供快照；其他未修订题集保留旧客户端兼容。服务端在判题前和写事务内分别核对，内容变化返回409且不保存成绩/错题；题集删除返回404。单纯标题变化不阻止提交。今日队列的错题项增加 `question_snapshot`，供调用方核对。

新版本快照使旧成绩仍归到原知识点，不移算到新题。图谱关联练习增加 `read_only_snapshot` 标识，界面明确标注历史。历史库从未记录正文修订时，无法恢复已被覆盖的旧题：使用 `question_evidence_since` 冻结原更新时间边界，保守排除不确定旧作答；未修订题集使用 `graph_attempt_cutoff=0`，仅改标题不损失有效证据。历史错题与题目正文不一致时不挂到新知识点。`excluded_sample_count` 包含上述不确定记录与时间/判题字段异常，不补造历史证据。

## 4.11 V2.3 C++ 编程练习与隔离评测

所有接口使用 `ApiResponse` 信封，并按现役本机/匿名设备身份选择数据库。`FILEMATE_ENABLE_PROGRAMMING=0` 关闭全部编程接口（503）；前端构建 `VITE_ENABLE_PROGRAMMING=false` 隐藏入口并将旧 `/programming` 链接转到学习工作区。

| 方法 | 路径 | 合同 |
|---|---|---|
| GET | `/api/programming/status` | `ready`、`installed`、`provider`、支持语言和网络隔离服务状态；真实编译/身份探针通过才为ready，自检缓存10分钟；`max_concurrent`为Windows 2/Linux 1，`setup_supported`标识是否支持页面准备，Windows网络服务每次核对 |
| POST | `/api/programming/setup` | Windows复制本机已安装MSVC/SDK到专用目录并强制自检；Linux只查询已部署代理状态，不安装系统组件，`setup_supported=false`，代理缺失返回未就绪 |
| GET | `/api/programming/problems` | 8道原创题的版本、题面、示例、分类、提示和资源限制；当前仅 `cpp17` |
| GET | `/api/programming/overview` | 最近100条完整提交/操作日志及全部有效完成记录的 `profile`，`evidence_scope=all_active_completed_submissions` |
| POST | `/api/programming/submissions` | `{problem_id,code,request_key,language:'cpp17'}`；非空代码至多100000 UTF-8字节；请求键16–80个ASCII字母/数字/下划线/短横线；相同键和代码幂等，不同内容409 |
| GET | `/api/programming/submissions/{id}` | 原代码、Artifact ID、状态、逐点结果、本地提示、复盘和笔记；跨身份或缺失记录404 |
| POST | `/api/programming/submissions/{id}/run` | 原子认领queued记录并真实编译运行；Windows并行上限2，Linux上限1，容量不足409且保持queued；重复认领不重复执行 |
| POST | `/api/programming/submissions/{id}/cancel` | queued/running→cancelled并终止对应Job；取消不可被迟到结果覆盖，重复操作幂等 |
| POST | `/api/programming/submissions/{id}/undo`、`/restore` | 仅改变已结束提交的统计资格，原始记录保留；运行中409，重复操作幂等 |
| POST | `/api/programming/submissions/{id}/review` | `{mode:'local'|'llm',allow_external_model:false}`；需有效completed记录；未确认外发422；模型异常502且保留旧复盘；已有相同复盘方式幂等返回 |
| POST | `/api/programming/submissions/{id}/notes` | `{notes}`最多8000字符，结束后的有效记录可保存；不修改代码/判题 |

SQLite v22只追加两个表，旧迁移不变。提交复用现役Artifact，保存代码、语言、哈希、判题、本地提示、复盘与笔记，可不绑定Source。日志只保存提交ID、操作、环境自检结果和时间，不包含代码、凭据或供应商异常详情。通用Artifact编辑拒绝修改评测证据（409）；代码修改须新建提交。损坏JSON、题目缺失或固定版本不可用的记录以 `data_error=true` 返回，阻止执行/改写/恢复，不进入profile，仍可取消和撤销，原库字节保留；不会用新版题目重判旧提交。服务中断后overview将本进程未持有的running记录标为failed；损坏记录只更新索引状态与中断事件，正常记录保留代码供新提交重试。一条损坏的孤立记录不会阻断其他历史；状态与事件必须原子提交，失败回滚且重复读取不重复记事件。

`result` 包含 `verdict`、`passed`、`total`、`score`、`compile_log`、`compile_ms`、`provider`、`tests`。CE无运行测试点；编译后逐点返回编号/名称、AC/WA/TLE/RE、输入预览与SHA-256、期望/实际输出、stderr、耗时、Job峰值内存、退出码及限制触发原因。输入预览最多4096字符，实际输出上限64KB字节。允许行末空白与末尾空行，不忽略中间空格、前导空格或大小写。分数严格为通过点数/总点数×100，总判定取首个失败测试点，全部通过为AC。CANCELLED与基础设施SYSTEM_ERROR不作为学习正确率样本。

Windows x64适配层要求MSVC/SDK。编译使用无网络能力的AppContainer，运行使用LPAC；恢复挂起进程前建立Job限制。编译30秒/768MB/8进程，运行每点1秒/256MB/1进程，CPU与墙钟均受限。只继承stdin/stdout/stderr三个句柄及必要标准路径变量。工具链副本只读，每点独立目录/身份，不修改宿主安装目录权限。BFE/MpsSvc未运行或隔离属性失败则禁止执行，不退回普通宿主进程。I/O写入观察阈值16MB，每20ms核对并终止洪泛，可能在观察间隔内超出，不是磁盘硬配额。支持标准C++17头文件；Windows不支持GCC扩展头；macOS执行暂不支持。

Linux适配层使用独立受限Unix socket代理，Web进程不持有Docker权限。代理要求固定摘要镜像与gVisor `filemate-runsc`，不退回原生Docker/宿主进程；请求仅含内置题目ID和代码，不接受路径、命令或自定义资源。每点独立容器，仅挂载二进制，根文件系统只读、移除能力、禁止提权/网络；受信任运行器限制学生单进程和线程，容器内计时排除启动开销，默认1秒/256MB。编译30秒/384MB/单CPU，临时文件总量64MB；运行文件系统16MB，单文件8MB，输出合计64KB。取消或断连删除容器，异常清理失败关闭代理。部署合同与固定版本见 `scripts/judge/README.md`。

编译诊断优先按UTF-8解码；未安装英语MSVC语言包时可回退Windows系统ANSI编码，避免中文CE日志乱码。学生程序输出不使用该回退，仍按UTF-8处理；日志捕获上限、隔离和判题规则不变。

`profile` 统计全部有效完成提交，分类通过率=AC提交数/有效提交数，趋势仅列最近30次。本周按服务器本地周一零点划分，平均次数=全部有效提交/已练习题数。最低通过率分类至少需3次提交，仅是练习线索。编程错题由提交投影生成，保留失败提交ID、错误/提交次数、最近复盘时间，同题连续两次AC标记已复习。取消、失败与撤销排除；无样本通过率为null，不构造能力百分制或用户研究结论。

模型不能写入分数。反馈行号须在代码范围内；归因须完整覆盖真实失败点且不能指向通过点。复杂度是静态参考意见。外发编译日志最多6000字符、每点输入/输出2048字符、stderr1024字符，并标注片段截断；代码完整外发最多100KB。异常或格式不合格502，旧记录保留。

## 4.12 V2.4 面试观察、内容证据与复盘报告

沿用 `/interviews` 原流程及现役本机/匿名设备分库。SQLite v23 仅追加迁移：回答新增 `visual_metrics`、`content_analysis`、`answer_key`、`answer_digest`；新增 `interview_review_state`、`interview_review_events`。报告复用 Artifact，类型为 `interview_report`，通用 Artifact 编辑返回 409，不能改写面试证据。

`POST /interviews` 增加可选 `allow_external_analysis: boolean | null`，保存到 Agent 上下文引用。`false` 禁止该场出题及提交回答时自动外发；新前端默认 `false`，用户后续逐题确认分析。旧客户端不传/null 保持已有流程；`FILEMATE_INTERVIEW_LOCAL_ONLY=1` 优先强制本地。原知识讲解和未授权私有错题规则保留。

`POST /interviews/{id}/answers` 增加可选 `question_index`（0–100）、`request_key`（16–80 位字母/数字/下划线/短横线）与 `visual_metrics`。同场同键且正文、题号和指标一致，重复提交返回现有记录；同键不同请求或过期题号返回 409，不推进第二题。旧客户端可省略这些字段。空回答仍为 422。

视觉摘要合同如下，额外字段、非有限数、计数不一致或超出时段的事件返回 422：

```json
{
  "source": "mediapipe_local_v1", "timeline_origin": "recording",
  "duration_seconds": 10, "sample_count": 20, "face_samples": 12,
  "low_light_samples": 4, "dropped_samples": 0,
  "events": [{"kind": "no_face", "start": 4, "end": 7}],
  "events_truncated": false
}
```

示例为合成合同数据。采样最多约 2Hz、30 分钟、3604 次，事件最多 200 条。`kind` 只允许 `no_face`、`low_light`、`head_turn`、`head_pose_change`、`smile_change`、`look_direction_change`；不接受音视频、帧、人脸坐标、情绪或人格字段。比例来自样本数，不是识别准确率。模型和 WASM 随前端同源分发，在 Worker 本机推理。

| 方法 | 路径 | 合同与副作用 |
|---|---|---|
| GET | `/interview/review/status` | 返回 `enabled`、`version=2.4`、`video_uploaded=false`、`calibration=待校准`；关闭模块仍为 200 |
| GET | `/interviews/{id}/review` | `{report, events}`；未生成或记录变化后 `report=null`；损坏报告 409，原回答保留 |
| POST | `/interviews/{id}/review` | 本地生成报告，无回答 409；同输入复用同一 Artifact；新回答或分析更新后需重新生成 |
| POST | `/interviews/{id}/turns/{turn_id}/analyze` | 请求 `{external_consent:true}`；只发送问题、回答、训练方向，无音视频；返回更新后的面试 |
| POST | `/interviews/{id}/analysis/cancel` | 使迟到分析失效；保留旧结果，返回 `{cancelled:true}` |
| POST | `/interviews/{id}/analysis/clear` | 请求 `{confirmed:true}`；清空模型评分、内容/视觉分析、报告和表达复盘，保留原回答及语音节奏 |
| GET | `/interviews/{id}/delete-preview` | 返回本场回答/报告数、`scope`、64 位 `confirmation_token` |
| DELETE | `/interviews/{id}` | 请求 `{confirmed:true,confirmation_token:"..."}`；删除本场记录及关联私有 Agent 记录；不删除原资料和其他练习 |
| GET | `/interviews/{id}/review/export?format=json\|markdown\|pdf` | 要求当前报告已生成，否则 409；返回实际下载文件，不使用 ApiResponse 信封 |

除状态接口外，`FILEMATE_ENABLE_INTERVIEW_REVIEW=0` 关闭以上八个增强路由（503），并拒绝回答请求中的视觉摘要；原有创建、获取、文字/语音回答及题库接口继续可用。前端 `VITE_ENABLE_INTERVIEW_REVIEW=false` 隐藏增强报告与视觉操作。关闭不删除数据；恢复后重新可读。不存在的会话/回答 404；确认缺失 422；删除预览后记录变化 409，重复确认已删除会话仍返回 `{deleted:true}`。

模型内容分析含 `source=llm_reference`、`areas`、`dimension_evidence`、`keywords`。六项 `areas` 为 `completeness`、`logic`、`technical_coverage`、`technical_expression`、`relevance`、`star`，各项含 `status=covered|partial|missing|not_applicable`、`evidence`、`suggestion`。肯定/部分覆盖必须提供原回答子串；四维引用必须齐全且为原句，关键词最多 20 个、每个最多 40 字并来自回答。读取持久化数据时重新验证，损坏记录返回 `analysis_data_error=true`，仅跳过损坏的分析而保留其他有效采集证据及原库字节；内容引用无效时评分和总分计数均排除该题，显示待评估。模型分数为有限 0–100 参考值，`scoring_mode=llm`、`scoring_version=v2.4`；缺字段、编造引用或网络失败返回 502，不替换旧报告。未确认外发 422、本地模式 503、私有错题未授权 403。已有效分析的同一回答复用已有结果，不重复调用模型；重新分析须先清空。

取消、清空、删除和新回答均推进修订号，迟到模型不能写入，返回 409。取消只阻止结果落库，已经发送的远端请求可能仍被供应商处理。事件仅保存操作、题目/回答引用或计数，不复制回答原文；删除后仅保留无会话标识的删除计数事件。

报告含逐题原回答、评分来源和原句、关键词、六项内容建议、本地结构线索、实际节奏/视觉统计及 `timeline`。时间轴每项含 `question_index`、`start/end`、`kind/label`、`timebase=recording|speech|visual`。语音指标可选 `recording_offset_seconds`；只有实际录像开始后启动语音识别时才由前端提供，用于对齐录像。没有共同起点则保留独立时间基准，不假装能定位录像。页面刷新后只恢复摘要，不恢复内存录像；有本题录像和录像时间基准时才允许点击回放。

导出使用 `Content-Disposition: attachment` 和 `Cache-Control: no-store`。PDF 通过 ReportLab 嵌入随项目提供的 Noto Sans SC 字体（SIL OFL），无需阅读器系统中文字库。无内容评分时 `overall_score=null`，无语音/视觉样本的比例和字速为 `null`。报告持续标记“待校准”，不构造情绪、人格、录用结论或专家准确率。匿名专家 CSV 与 Spearman 工具位于 `evaluation/`，真实专家和合成配对分开统计。

摄像头/录像只保存在当前页 Blob 内存，主动下载由用户决定；音视频不传业务服务。语音识别使用浏览器 API，厂商可能提供在线识别服务，前端明确提示这一独立边界。删除本地录像不会删除已保存回答和观察摘要，清空分析不会删除原回答；整场删除必须先预览确认。

## 4.13 V2.5 求职训练中心

SQLite v24 **追加** `career_positions`、`career_trainings` 和 `career_events`；旧迁移不改写。岗位保存完整来源、采集时间、要求和当前修订号；每次训练为 `career_training` Artifact，冻结当时的岗位快照。接口沿用 `ApiResponse` 与本机/匿名设备分库，导出返回附件字节。

| 方法与路由 | 合同 |
|---|---|
| `GET /api/career/status` | `{enabled,version:"2.5",live_recruitment:false}`，关闭时仍可读 |
| `GET /api/career/catalog` | 三个短篇官方岗位摘要；只读目录，不自动保存或动态抓取 |
| `POST /api/career/extract` | `{description}`；本地词表返回 `{requirements,method}`，只供核对，未落库 |
| `GET /api/career/positions` | 最新200个岗位（包含撤销/损坏标记） |
| `POST /api/career/positions` | `{position,request_key,confirmed:true}`；同键同内容返回原记录 |
| `GET /api/career/positions/{id}` | 当前岗位、修订号、采集距今天数及异常标记 |
| `PATCH /api/career/positions/{id}` | `{position,expected_revision,confirmed:true}`；修改当前岗位，不改变旧训练 |
| `POST /api/career/positions/{id}/state/{undo\|restore}` | `{confirmed:true}`；重复状态变更幂等 |
| `GET /api/career/positions/{id}/evidence` | 当前图谱、全部有效代码提交、基础作答和关联面试的有限投影 |
| `GET /api/career/positions/{id}/trainings` | 本岗位最新100份训练；撤销后仍可读取历史 |
| `POST /api/career/positions/{id}/trainings` | `{kind:"written"\|"interview"\|"review",expected_revision,request_key,confirmed:true}` |
| `GET /api/career/trainings/{id}` | 历史岗位与训练快照；未提交基础题隐藏本接口的答案/解释 |
| `POST /api/career/trainings/{id}/answers` | `{answers:{question_id:option_index}}`；全部题目、严格整数、索引范围校验 |
| `GET /api/career/trainings/{id}/export?format=json\|markdown` | 保存的训练快照附件，`Cache-Control:no-store`；未作答时同样隐藏答案 |
| `GET /api/career/positions/{id}/delete-preview` | `training_count`、`learning_plan_count`、明确保留范围与64位确认令牌；绑定岗位学习计划内容、状态及进度 |
| `DELETE /api/career/positions/{id}` | `{confirmed:true,confirmation_token}`；预览后岗位/训练变化则409 |
| `GET /api/career/events` | 最新100条有限事件，不复制描述、代码或原回答 |
| `GET /api/career/overview` | 成长页只读汇总：有效岗位数、训练数、基础题实际作答/答对数、面试已答/已评估数、对比快照数、异常排除数、最新5份引用和记录更新时间 |

`position` 字段：`company/industry/region`（1–80字）、`title`（1–100字）、`employment=校招|实习|社招参考|用户自定义`、`description`（10–12000字）、`requirements`（1–30项）、`source`（1–120字）、`source_url`（可空，最多1000字）、`source_kind=official_snapshot|user_import`、带时区且不在未来的 `collected_at` 和可选 `published_at`（最多40字）。要求为 `{label,category,evidence}`，标签1–60字且不重复，`category=programming|knowledge|project|communication`；`evidence` 为1–400字的描述原句。来源链接只允许无凭据的HTTPS，服务端不请求该URL。

仅与目录完全一致的摘要可标记 `official_snapshot`。自行导入及修改为 `user_import`，原链接保留供用户核对，不赋予平台已验证或企业授权标签。目录采集于2026-10-01，仅两家企业、三个训练参考岗位，社招参考不冒充校招机会；来源说明见 [career/README](../career/README.md)。

`request_key` 为16–80位字母、数字、下划线或连字符；岗位保存绑定内容，训练绑定岗位ID/修订/类别。已接受训练即使后来岗位修改或撤销，同键重试仍返回原快照；新训练必须使用当前修订且岗位有效。确认缺失/字段异常422，不存在404，过期修订/键冲突/重复不同作答409。相同基础作答重试返回原结果，不重复计数；改变答案需新建一轮。无关联原创题则409，面试和对比仍可创建。岗位面试一次原子创建真实Agent步骤、五道原创口头问题、原面试会话和训练Artifact；失败整体回滚。默认 `allow_external_analysis=false`，回答/报告/逐题外发仍遵循4.12。

成长汇总统计全部当前保存的有效训练，包含撤销岗位的历史；只显示最近5份原记录链接，不受训练列表100条显示上限影响。删除求职岗位后其训练不再计入该汇总，保留的面试仍见原面试统计；刷新汇总只读取现有数据，不写入成绩、事件或画像分数。

对比不计算适配率、录用概率或能力总分。图谱只使用已确认且未过期的节点和其真实最近窗口；各节点样本之和允许重复关联，不当作独立样本数。编程取有效、未撤销的完成记录，排除SYS及取消等状态；每技能提供全部有效提交数量、AC数量和最新20条引用。基础题取本岗位最近100份训练中的已完成记录，同题跨轮可重复。面试只统计岗位关联会话的实际已答/已评估数。公开标签词表只确定训练关联，需人工核对；未录入/未作答显示待评测，不代表能力不足。Python/Java的代码执行尚未支持，复用C++17平台的边界不变。

保存对比为当时的持久快照；后续作答不改写旧对比。岗位或训练载荷损坏标记 `data_error=true`，保留原字节，禁用训练/导出；可预览删除或重新导入。求职训练Artifact及`origin=career_plan`的学习计划Artifact禁止通用PATCH覆盖。删除岗位清除其求职训练、岗位、由它生成的学习计划和进度、私有求职事件，保留原Source、图谱、编程提交、面试、Agent及其他学习计划；整场面试可按4.12单独删除。重复确认已删除岗位返回 `{deleted:true}`，只保留无岗位/训练/计划ID的删除计数。

`FILEMATE_ENABLE_CAREER=0` 使状态外的21种路由操作返回503（含4.14四种计划操作），数据保留。前端构建 `VITE_ENABLE_CAREER=false` 隐藏入口，旧 `/career` 跳转 `/ai-tools`。恢复开关后原记录可读；不要降级/改写旧迁移。

## 4.14 B2 岗位证据到学习计划

沿用v24、现役`study_plans`和Artifact，无新表或迁移。所有新路由使用同一身份空间与求职开关。

| 路由 | 合同 |
|---|---|
| `GET /api/career/positions/{id}/plan-preview` | 只读返回岗位修订、`evidence_revision`、`requirements_total`、最多7项`steps`、规则`method`和现役合同`plan` |
| `GET /api/career/positions/{id}/plans` | 本岗位生成的计划，含`plan_id/artifact_id/title/status/created_at/updated_at/plan_data/completed_days/data_error`；撤销岗位仍可回看 |
| `POST /api/career/positions/{id}/plans` | `{confirmed:true,evidence_revision}`，指纹为64位小写十六进制；当前证据一致后原子新增计划、Artifact及事件 |
| `POST /api/career/positions/{id}/plans/{plan_id}/{undo\|restore}` | `{confirmed:true}`；只操作本岗位创建的计划，撤销为archived、恢复按原进度为active/completed |

每个step含`label/status/priority/requirement_quote/reason/actions`。优先安排最近基础题答错、关联节点待复习或最近相关C++提交失败；未采集作答为待评测。基础题取全部有效训练中每知识点的最近作答，时间相同时以持久提交事件序号排序；未来时间排除。图谱数量可能跨节点重合，代码引用沿用最近20条投影，面试回答只作为人工回看依据。日程使用服务器本地日期，每天建议30分钟，最多7项；既有计划与完成进度不覆盖。`daily_plan[].training_actions`提供有标签的本地原记录链接；`career_basis`保存规则版本`career-plan-v1`、岗位/证据版本和原依据。时间统一返回带时区的ISO格式。

指纹绑定岗位修订、实际推荐依据和日期。确认缺失/非法指纹422、不存在或跨身份/跨岗位404、新证据/岗位变化409。相同已接收指纹重试返回原计划和进度，撤销后重试不会自动恢复；新指纹另存一份。损坏的计划内容、路由、进度或metadata显示`data_error=true`，保留原字节，允许撤销和删除预览，阻止恢复。计划状态和内容/进度都参与岗位删除确认，预览后发生变化须重新预览。进度、今日队列、CSV/ICS复用现役学习计划接口。

## 4.15 B2 成长统计证据说明

`GET /analytics/overview` 保留旧字段，并追加只读 `evidence_profile`（`learning-evidence-v1`），不新增表或migration。资料范围内的内部聚合使用相同过滤；公开成长页只读取当前设备身份空间。

画像含 `scope/source_id/window`、`metrics.quiz|wrong|plan|interview`、按维度的 `dimensions`，以及未评估回答、撤销计划和不可解析面试数量。每项提供 `sample_count/sample_unit/updated_at/basis/value/status/excluded_count/records`；最多展示最近5条匿名标识及本地原题集、计划或面试链接，样本数统计全部有效记录。

作答率按实际判题次数；错题状态按平台连续答对两次规则；计划完成率排除archived及损坏记录，完成日使用现役**零起始数组索引**，重复/越界索引不计入；面试仅汇总有效 `scoring_mode=llm` 的逐回答分数，本地回退不参与。分数、时间及JSON异常只读排除，原字节保留。旧无时区SQLite时间按UTC解释，未来时间不计入画像。

无样本为 `pending_assessment`，不足5条为 `insufficient_samples`，90天没有新证据为 `historical_only`，其余为 `observed`。原始观察值可回看，但少量样本和历史数据不展示为当前能力结论；5条和90天仅为界面摘要规则，不能作为学习认证或研究门槛。每维度分别报告样本数，不使用其他维度或面试场数替代。

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
| 2026-08-27 | v1.6 | 增加 SQLite v12 题库兼容修复，并支持 `FILEMATE_HOST` / `FILEMATE_PORT` 部署监听配置 | Codex |
| 2026-08-28 | v1.7 | LLM 鉴权、余额或权限错误改为立即失败并进入本地降级，避免无效重试拖慢导入 | Codex |
| 2026-08-28 | v1.8 | 增加 AI 会话列表与恢复合同、结构化引用持久化和列表限流 | AcMaster-MAX / Codex |
| 2026-08-28 | v1.9 | 默认模型统一迁移至 `deepseek-v4-flash`，移除 Step 系列运行时分支并拒绝旧配置 | Codex |
| 2026-09-02 | v1.10 | 增加 SQLite v13 面试流畅度证据、摄像头本地预览边界与可选请求合同 | Codex |
| 2026-09-03 | v1.11 | 增加 SQLite v14 可信 Agent 轨迹、共享记忆撤销、资料授权与隐私中心接口 | Codex |
| 2026-09-12 | v1.12 | 增加生产匿名设备身份、独立数据目录、跨用户越权回归、可信 Origin 校验和内部路径过滤 | Codex |
| 2026-09-05 | v1.12 | 增加目标反推、资料学习资产链、本地录像时间轴和资料驱动面试合同 | Codex |
| 2026-09-07 | v1.13 | 增加本机 DeepSeek 密钥安全配置接口，桌面端用户可自带密钥且不写入业务数据库 | Codex |
| 2026-09-29 | v2.1 | 增加数字人播报最小日志、身份隔离、幂等终态与可删除记录合同 | Codex |
| 2026-10-01 | v2.1.1 | 数字人播放超时、取消与暂停恢复、答案路由切换、日志同步重试；无新增 schema/API | Codex |
| 2026-09-29 | v2.2 | 增加知识图谱草稿确认、原文溯源、学习证据投影与计划确认撤销合同 | Codex |
| 2026-10-01 | v2.2 | 补充学习画像、可追溯薄弱点、SQLite v21 操作事件、损坏批次隔离及真实教材验收 | Codex |
| 2026-09-29 | v2.2 | 增加错题口头复练的资料片段定位、Agent 引用传递、无匹配回退与片段变更失效合同 | Codex |
| 2026-09-29 | v2.3 | 增加 SQLite v19 今日学习时间预算、用户任务排序与可解释错因建议合同 | Codex |
| 2026-10-01 | V2.3 编程模块 | 增加SQLite v22编程提交、Windows隔离C++17真实评测、逐点证据、复盘与撤销恢复合同 | Codex |
| 2026-10-01 | V2.4 面试增强 | 增加 SQLite v23 本地视觉摘要、原句内容证据、幂等回答、修订取消、报告导出与确认删除合同 | Codex |
| 2026-10-01 | v2.5 | 增加求职岗位来源核对、原创训练、真实证据对比、快照导出及独立关闭合同，SQLite v24 | Codex |
| 2026-10-02 | v2.5 | 补齐成长页求职只读汇总、原记录链接、异常排除和更新时间 | Codex |
| 2026-10-02 | B2 | 岗位实际证据到确认学习计划、进度回看与撤销恢复，扩展岗位删除预览 | Codex |
| 2026-10-02 | B2 | `learning-analytics.evidence_profile`四类只读统计、样本/时间/依据/原记录、异常和本地回退排除；无新schema | Codex |
| 2026-10-03 | DEV-01 | 学习资料本地导入增加UTF-8 Markdown/代码文本；沿用原文引用/哈希复用/会话，无执行、无模型调用；分类上传格式不变 | Codex |
