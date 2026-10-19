# API 规范

2026-10-16 OPT-01候选：五个上传AI接口将同步生成放入线程池；摘要/卡片/笔记为空、结构错误或上游失败返回502，不持久化成功产物。上传和现役工作区保持配额429/治理503。学习导入与上传共用受控解析422，错误明确等待/拆分/解密，未知内部异常不公开。Source元数据保留页数/truncated/enrichment_incomplete及parse_warnings；AI响应、Artifact/Context元数据和计划新增可选warnings，记录实际模型输入截取范围。卡片数1–50、摘要长度1–10000、卡片格式front_back/qa、笔记outline/markdown/mindmap在落盘前校验。无新路由/schema/依赖/环境变量；旧数据缺字段仍可读。实现、证据及未完成项见[优化合同](../../docs/PRODUCT_OPTIMIZATION_EXECUTION_2026-10-16.md)，尚未发布。

2026-10-15 上传故障修复候选：PDF/Office 解码和 `/process` 富提取使用单槽子进程，384 MiB、40 秒墙钟、Linux 25 秒 CPU、8 MiB 输出上限。忙碌、超时、资源超限及失败沿用 `{raw_text,metadata,error}`；`/process` 为 success:false 的失败会话，`/knowledge/import` 沿用解析失败响应。超过 500 页 PDF 要求拆分，文本上限 500,000 字，metadata.truncated 标注截断；超过 50 页保留正文，metadata.enrichment_incomplete=true 和 note 明示未做表格／图表几何提取。API/阶段线程池保留租户及模型授权上下文；子进程不传模型密钥，不执行 LLM 或数据库写入。没有新环境变量、路由或迁移；Windows RSS 巡检不等同于 Linux 地址空间硬限制。见 [故障记录](../../docs/INCIDENT_2026-10-15.md)。

2026-10-14 缺陷修复候选：新增`GET /api/ready`，核心业务库/公网账号库/资源账本可读且版本符合当前实现时200，否则503；响应`{success,data:{version,status,checks},error}`，status为`ready`或`not_ready`，checks各项为`ready`或`unavailable`。响应no-store，不返回路径、异常原文、用户计数或密钥，不解析会话、不创建游客、不触发迁移或外部AI/语音/OJ调用。只读连接每库busy timeout 0.5秒；不是完整性扫描或全功能验收。`GET /api/health`继续仅报告进程存活和版本，数据库故障时仍可用。既有部署脚本同时校验存活、就绪和候选版本；维护及备份探测不会创建匿名空间。

上传`/process`和`/knowledge/import`在读取正文/落盘前校验文件名：统一剥离浏览器携带的Windows/Unix路径，UTF-8文件名最多255字节，拒绝控制字符、Windows非法字符、保留设备名与尾随空格/点，非法名称400。落盘故障503，清理本次新建目录内的部分文件，保留用户原件和已有同名文件；原25MiB/空内容/格式限制保留。

`LLMClient.call_structured()`保留返回对象或数组的历史合同；显式提供Schema时先校验配置，使用jsonschema执行结构验证（包括嵌套/必填/类型/枚举/内部引用），禁用网络和文件引用解析。非法Schema为LLMConfigError；无效JSON、非对象/数组根、NaN/Infinity/浮点溢出或不符合结构为LLMAPIError。错误不包含模型原文且不展示底层解析异常；已成功供应商调用的真实usage仍保留，不因解析失败清零，也不额外触发自动模型重试。未提供Schema的历史调用仍须执行各模块业务验证，此修改不代表所有AI结果均已完成事实校准。语音依赖锁更新为edge-tts 7.3.1，无路由、声线或授权规则变更。详见[本轮修复记录](../../docs/KNOWN_BUG_FIXES_2026-10-14.md)。

2026-10-11 本地任务/执行候选：治理追加migration2，业务schema26不变。Session/Agent/目标与学习任务/图谱及岗位计划/岗位训练/学期确认写入前校验空间和全站日额度。默认日任务/执行账号4000/100、游客1500/20、本地10000/500、全站30000/1000，执行并发2/1/2/2，UTC+08:00午夜重置。新增 FILEMATE_RESOURCE_{ACCOUNT,GUEST,LOCAL,GLOBAL}_{DAILY_TASKS,DAILY_EXECUTIONS,EXECUTION_CONCURRENT}，前两项1–100000、并发1–16，不能为0。计数为准入工作量，失败不退款，不是学习统计。Windows实际编译自检计数，缓存命中不计；Linux固定自检保持原代理十分钟缓存/单槽。

执行在认领/编译前拒绝超额429或账本故障503，保留queued与代码。完成/取消/重复确认不创建新工作，资料授权/记忆撤销审计免于预算；读取/完成/取消/隐私动作保留。HTTP绑定实际服务端数据库，生产缺可信Scope/绑定时拒绝新资源。GET /api/llm/usage追加resources计数/限额/独立coverage_started_at，offset改0–1000000（超大整数422），原字段/no-store保留。个人导出增加resource_events，恢复不回写额度；注销清本人资源记录，匿名全站累计保留。管理员备份/部署只读兼容治理schema1/2，M1应用不直接支持M2，回滚须配套完整备份/兼容工具。存储/费用/完整Trace及AUD-09未关闭；见[资源准入子卡](../../docs/TASK_EXECUTION_BUDGET_2026-10-11.md)，未上线。


2026-10-11 本地模型准入候选：统一LLM每次供应商尝试（含重试）及明确授权后的Microsoft语音使用独立持久账本，原子校验当前学习空间/全站的每日次数、准入单位和跨进程并发。次数/单位默认账号300/2000000、游客60/250000、本地1000/10000000、全站3000/20000000；单空间4路/全站16路，UTC+08:00午夜重置。准入单位是消息UTF-8字节＋最大输出token＋消息开销，不是实际token或账单；未知token和费用为NULL。账本故障拒绝新的外部调用，读取/健康/核心导出继续可用。模型连接测试的预算拒绝429、账本故障503，不作为无效密钥502处理。

新增 `GET /api/llm/usage?limit=50&offset=0`，limit1–100/offset非负，归属只来自服务端会话，不接受owner选择；返回日计数/上限/重置时间、coverage_started_at、分页attempt/trace/provider/model/duration/status/error_code/request_id及真实usage。partial汇总带每字段已知记录数，cost.status=`not_available`且amount/currency=NULL；响应no-store。个人JSON导出增加model_usage，ZIP新增签名保护的model-usage.json；恢复不安装该文件到数据库，不改变额度或恢复预览。用量导出故障/32MiB上限明确available:false，核心导出保留。注销/到期删除清理本人元数据，保留匿名全站累计；失败cleanup_pending:true由维护重试。

独立 `FILEMATE_DATA_DIR/control/resource-governance.db` 为治理schema1，业务schema26和已发布迁移不变，管理员完整备份/部署工具识别两种数据库。环境配置新增 `FILEMATE_AI_{ACCOUNT,GUEST,LOCAL,GLOBAL}_{DAILY_ATTEMPTS,DAILY_BUDGET_UNITS,CONCURRENT}`、`FILEMATE_AI_RETENTION_DAYS`；只接受有界正整数，默认保留30天。直接依赖psutil锁定7.2.2。真实费用、任务/存储预算、完整统一Trace、HTTP下载硬截止及AUD-08/09仍未完成；详见[本地模型累计准入子卡](../../docs/MODEL_BUDGET_AUDIT_2026-10-11.md)，尚未部署。

2026-10-11 本地候选的 LLM 模块合同：`call()`/供应商 `chat()` 保持纯文本；新增适配层 `chat_with_metadata()` 返回文本、供应商实际 token 计数及有界请求标识。`get_usage()` 按当前请求/线程隔离，仅包含供应商返回的合法字段，未知或`call()`失败为 `{}`，不会补写0；HTTP成功后的上层解析失败仍保留已知消耗。默认 timeout/retry 读取 `LLMConfig`，单次1–3次尝试共享递减的重试时间预算；Requests 的 socket 超时仍不是整个下载的硬截止。没有新增 HTTP API、环境变量或迁移，累计预算、持久化和成本仍未完成；详见[用量与调用隔离子卡](../../docs/LLM_USAGE_FOUNDATION_2026-10-11.md)。上线状态以该交付回执为准。

2026-10-10 自然语音合同：`POST /api/digital-human/speech` 接收 `{text, voice_id, allow_external_voice}`。正文1–5000字，默认 `zh-CN-XiaoxiaoNeural`，另允许 Yunxia/Yunxi/Xiaoyi Neural；必须明确传入布尔 `true` 授权正文经当前 FileMate 服务转交 Microsoft。响应为 `audio/mpeg`、`Cache-Control:no-store`，不保存请求正文或音频。每空间每分钟6次、每进程并发2次、55秒总超时、8MiB音频上限；无授权403，非法参数422，繁忙429，供应商失败502，功能关闭503。`FILEMATE_ENABLE_NATURAL_VOICE=0` 可独立关闭，数字人总开关同时生效。元数据 provider 新增 `microsoft_edge`，旧 `web_speech` 记录兼容；无需数据库迁移。完整边界见[自然语音交付](../../docs/MICROSOFT_NATURAL_VOICE_2026-10-10.md)。

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
| `DELETE` | `/knowledge/sources/{source_id}` | 确认删除资料及其派生产物 | 级联删除派生数据；仅清理托管上传副本 |
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

资料删除合同（schema v26）：

- `GET /knowledge/sources/{source_id}/delete-preview`：返回影响数量、托管文件状态及有效15分钟的随机 `confirmation_token`；不暴露绝对路径，不执行删除。
- `DELETE /knowledge/sources/{source_id}`：JSON 必须为 `{ "confirmed": true, "confirmation_token": "预览凭据" }`。缺少确认422，越权资源404，无效/过期凭据或原文/派生数据变化409。
- 确认在当前身份数据库内校验；原文和关联行摘要绑定修订，删除与最小审计/成功回执在同一事务中提交。审计不含资料名、路径、正文和凭据。
- 仅清理当前上传目录内且没有其他 Source 引用的托管副本。暂存、清理或数据库事务失败时恢复原文件并回滚数据；外部原文件保留。
- 相同凭据重复提交返回首次成功回执，不重复删除或记账；不存在资源且没有有效回执404。

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
| `DELETE` | `/knowledge/sources/{source_id}` | 确认删除资料及其派生产物 | 级联删除；仅清理 `FILEMATE_UPLOAD_DIR` 内托管副本 |
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

`result` 包含 `verdict`、`passed`、`total`、`score`、`compile_log`、`compile_ms`、`provider`、`tests`。CE无运行测试点；编译后逐点返回编号/名称、AC/WA/TLE/MLE/RE、输入预览与SHA-256、期望/实际输出、stderr、耗时、峰值内存、退出码及限制触发原因。MLE只由受信沙箱 `reason=memory_limit`（Windows本Job内核通知、Linux运行器实际计数或Docker OOMKilled）决定，不由学生错误文字/退出码137/AI推断。Linux新增可选 `tests[].peak_address_bytes`，为采样得到的地址空间观察峰值，不替代RSS；未观测不伪填预算值，旧记录保持可读。具体检测余量/平台差异见[内存识别修复](../../docs/OJ_MEMORY_LIMIT_2026-10-10.md)。输入预览最多4096字符，实际输出上限64KB字节。允许行末空白与末尾空行，不忽略中间空格、前导空格或大小写。分数严格为通过点数/总点数×100，总判定取首个失败测试点，全部通过为AC。CANCELLED与基础设施SYSTEM_ERROR不作为学习正确率样本。

Windows x64适配层要求MSVC/SDK。编译使用无网络能力的AppContainer，运行使用LPAC；恢复挂起进程前建立Job限制。编译30秒/768MB/8进程，运行每点1秒/256MB/1进程，CPU与墙钟均受限。只继承stdin/stdout/stderr三个句柄及必要标准路径变量。工具链副本只读，每点独立目录/身份，不修改宿主安装目录权限。BFE/MpsSvc未运行或隔离属性失败则禁止执行，不退回普通宿主进程。I/O写入观察阈值16MB，每20ms核对并终止洪泛，可能在观察间隔内超出，不是磁盘硬配额。支持标准C++17头文件；Windows不支持GCC扩展头；macOS执行暂不支持。

Linux适配层使用独立受限Unix socket代理，Web进程不持有Docker权限。代理要求固定摘要镜像与gVisor `filemate-runsc`，不退回原生Docker/宿主进程；请求仅含内置题目ID和代码，不接受路径、命令或自定义资源。每点独立容器，仅挂载二进制，根文件系统只读、移除能力、禁止提权/网络；受信任运行器限制学生单进程和线程，容器内计时排除启动开销，默认1秒/256MB学生地址空间预算，硬地址保护有16MiB检测余量。容器内存上限另含128MiB运行时预算，默认384MB、禁止额外swap，`result.limits`分别标明三种预算。编译30秒/384MB/单CPU，临时文件总量64MB；运行文件系统16MB，单文件8MB，输出合计64KB。取消或断连删除容器，异常/超时清理失败关闭代理并释放客户端。部署合同与固定版本见 `scripts/judge/README.md`。

编译诊断优先按UTF-8解码；未安装英语MSVC语言包时可回退Windows系统ANSI编码，避免中文CE日志乱码。学生程序输出不使用该回退，仍按UTF-8处理；日志捕获上限、隔离和判题规则不变。

`profile` 统计全部有效完成提交，分类通过率=AC提交数/有效提交数，趋势仅列最近30次。本周按服务器本地周一零点划分，平均次数=全部有效提交/已练习题数。最低通过率分类至少需3次提交，仅是练习线索。编程错题由提交投影生成，保留失败提交ID、错误/提交次数、最近复盘时间，同题连续两次AC标记已复习。取消、失败与撤销排除；无样本通过率为null，不构造能力百分制或用户研究结论。

模型不能写入分数。反馈行号须在代码范围内；归因须完整覆盖真实失败点且不能指向通过点。复杂度是静态参考意见。外发编译日志最多6000字符、每点输入/输出2048字符、stderr1024字符，并标注片段截断；代码完整外发最多100KB。异常或格式不合格502，旧记录保留。

## 4.12 V2.4 面试观察、内容证据与复盘报告

沿用 `/interviews` 原流程及现役本机/匿名设备分库。SQLite v23 仅追加迁移：回答新增 `visual_metrics`、`content_analysis`、`answer_key`、`answer_digest`；新增 `interview_review_state`、`interview_review_events`。报告复用 Artifact，类型为 `interview_report`，通用 Artifact 编辑返回 409，不能改写面试证据。

`POST /interviews` 增加可选 `allow_external_analysis: boolean | null`，保存到 Agent 上下文引用。`false` 禁止该场出题及提交回答时自动外发；新前端默认 `false`，用户后续逐题确认分析。不传/null 一律不授权外发；`FILEMATE_INTERVIEW_LOCAL_ONLY=1` 优先强制本地。原知识讲解和未授权私有错题规则保留。

`POST /interviews/{id}/answers` 增加可选 `question_index`（0–100）、`request_key`（16–80 位字母/数字/下划线/短横线）与 `visual_metrics`。同场同键且正文、题号和指标一致，重复提交返回现有记录；同键不同请求或过期题号返回 409，不推进第二题。旧客户端可省略这些字段。空回答仍为 422。

2026-10-13开发候选：`POST /interviews`的`scenario`兼容原四场景，并增加`技术面|项目面|算法面|HR面|压力面|英语面`。可选`project_name`（≤120）、`project_details`（≤6000）、`remember_for_future`（默认false）、`memory_id`（≤64）。项目面缺项目或只填一项返回422；无有效回答、资料已删除或撤销的所选记忆返回409。新专项或记忆训练不传`allow_external_analysis`时按false处理，旧四场景未传字段同样不授权外发。专项五题为规则脚本；下一问题按本次真实回答与已校验分析组织，不新增模型请求。原题库CRUD的场景限制未在本轮扩展。

创建、恢复、回答响应增加`practice_context:{mode,project,remember_for_future,memory_id,memory_ref,memory_available}`；project为用户填写的`{name,details,source:'user_input'}`或null。memory_ref含历史memory/interview/turn/question引用及本轮`target_question_index`。remember_for_future反映当前有效许可，不把已撤销的初始勾选当成许可。英语`fluency_metrics`增加`language:'en-US'`、`words_per_minute`；英语不产生未校准的节奏分，报告expression的words_per_minute可缺省/null以兼容旧报告。

| 方法 | 路径 | 面试记忆合同 |
|---|---|---|
| GET | `/interview/practice/memories?limit=30` | 1–100；按近期会话列本空间已授权且已回答记录的memory_id/interview_id/target_role/scenario/answer_count/created_at，不返回回答正文 |
| GET | `/interview/practice/memories/{id}/forget-preview` | 返回作用范围与绑定该许可的confirmation_token；不存在404 |
| DELETE | `/interview/practice/memories/{id}` | `{confirmed:true,confirmation_token}`；未确认422、令牌不匹配409、不存在404；成功`{forgotten:true}`，重复同令牌幂等；只停止未来复用，原会话/报告与已生成问题保留 |

编程`GET /api/programming/problems`增加`knowledge_nodes:[{id,label,kind:'catalog_concept'}]`、`source`、`source_url`。目录概念不等于个人已确认图谱节点。`GET /api/programming/overview`增加`recommendations:[{problem_id,title,difficulty,stage,reason,basis_submission_ids,knowledge_nodes,method:'local_evidence_rules_v1'}]`，默认三条；统计全部有效完成提交，规则选择且不调用LLM/创建任务。依据ID可用原提交读取接口核对。题目版本与Judge请求格式不变。

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

2026-10-04面试分析修正：适配层请求JSON对象，让模型选择程序生成的原回答片段编号，入库前还原为严格原文；编号不进入公开结果或数据库，旧原句格式仍须通过同一校验。格式/引用错误最多纠正一次，两次调用共享45秒预算、单次不超过30秒，不对鉴权或连接错误盲重试。可选关键词逐项筛选、去重及限量，未出现在原回答中的词不入库，单个无效标签不抹掉已核对的内容分析；关键词容器格式错误仍拒绝。502提示区分配置、密钥/余额/权限、超时、限流、格式/引用和连接问题，不返回供应商正文、密钥或原回答。确认、取消竞态、报告保留、隐私授权与schema保持原合同。

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

### 错题全量分页（AUD-02）

`GET /wrongbook/page` 返回 `{items,total,limit,offset,has_more}`。`limit=1..200`（默认50）；稳定排序为到期时间、更新时间降序、wrong_id。支持 `mastered`、`q`（最多160字，题干/知识点/资料名，通配符按字面匹配）、`source_id`、`error_cause`、`due_only`。筛选作用于整个当前身份数据库，先筛选再分页；数据变化后总数会更新，翻页期间不提供冻结快照。旧 `GET /wrongbook` 保留数组合同，增加 offset/q/source_id。

正式错题页每页30条，搜索后回到首页，筛选无结果与真实空数据分别展示。索引复用 idx_wrong_next_review / idx_wrong_mastered。

### 大图谱有界读取（AUD-03）

`GET /api/knowledge-graph` 默认/最多200节点；offset/q（最多160字）筛选完整图谱。返回 pagination.total/offset/limit/has_more/batch_total/batch_offset 和 edge_total；profile 的统计始终来自全量实际证据，weaknesses 只展示前20条，weakness_total 保留总数。edges 仅为当前页内部关系，不能当全图边数。

批次列表每页20条，使用 batch_offset；payload_loaded=false 时不含完整节点/关系，`GET /api/knowledge-graph/batches/{id}` 按需加载核对原文。`GET /api/knowledge-graph/nodes/{id}` 可从复习提醒或链接读取页外知识点证据；不存在/其他身份404。新调用方必须按分页与按需详情合同读取，不能把摘要里的空 payload 当成空批次。

聚合使用独立SQLite只读一致性快照；同一空间的CPU密集图谱聚合并发限制为1，不占用工作区写锁，也不共用其他空间的聚合锁。客户端每图最多100节点，大图采用圆形布局；列表分页、全量搜索和批次详情保留访问能力。未增加缓存，因此新作答、资料编辑、撤销和删除会在刷新后立即体现。

### 题目完整性（AUD-04）

模型输出整批验证：1至请求上限（最多10），题干/答案为非空文本，题型为choice/fill/short_answer，选择题2至8个不同选项且参考答案对应实际选项；非选择题不携带选项。错误题型、超额、重复题干和任何坏题均导致生成502，不保存Source派生产物。缺少解析可以保留为空，不补造答案或选项；仅基于已有选项规范化标号。没有校验失败后的无限重试。

历史题目仅兼容既有字段名/缺省非客观题型；完整性失败时产物返回metadata.question_data_error=true，原内容保留，判题422且不增加作答/错题记录，也不计入图谱掌握度。题集内容编辑验证1至1000题且不可重复；无效编辑422，不覆盖原内容；标题单独编辑不改变历史证据。

### 技能树（AUD-05a）

独立入口 `/skills`；`GET /api/skills/tree`、`PUT /api/skills/tree`。配置以schema_version=1的skill_tree Artifact持久化，最多200个目标，每个20项验收条件。PUT传递上次读取的revision，修订冲突409；多余字段/格式422；重复标识、循环/缺失先修、重复或其他空间的验收记录409。通用产物编辑接口不得绕过专用合同修改技能树。

criteria关联quiz题集与question_index、coding提交或interview会话，required_successes=1..20（单个coding提交仅1）。统计仅为实际正确作答、有效活动AC或实际面试回答；修改题目、撤销提交、删除证据会重新计算。states为pending_assessment/in_progress/prerequisites_pending/conditions_met，不冒充专业能力分数。

`GET /api/skills/targets?q=...` 在当前空间全量题集里按题干/标题查询，最多展示500课程目标、100编程记录、50面试记录；默认展示近期候选，输入更具体的词可找到旧题。没有外部AI调用。后端FILEMATE_ENABLE_SKILL_TREE=0拒绝模块503，前端VITE_ENABLE_SKILL_TREE=false隐藏入口并重定向；停用不删除数据。

## 简历事实与导出（AUD-05b）

GET /api/resume/profile 返回当前私有空间的事实或 null；PUT 接受 schema_version=1、revision、name/school 必填，教育、联系方式、技能≤40、项目≤30。revision 不匹配返回409；项目可关联当前空间有效编程提交，其他空间或已撤销提交不接受。保存记录最小审计，不修改观察画像。

POST /api/resume/generate：profile_revision、mode=local|llm、allow_external_model。local 不调用模型；llm 必须显式同意，发送教育/技能/项目及目标岗位，姓名/联系方式字段不发送（自由文本须自行去敏）。模型仅返回合法且唯一的事实ID，不能增加正文。结构错误/资料版本变化409，模型故障502；旧事实/简历保留。45秒模型超时、最多一次调用尝试；复用可替换LLM适配器与单请求凭据。

GET /api/resume 列最近30份；GET /api/resume/{id} 返回不可由通用Artifact编辑器修改的快照；GET /api/resume/{id}/export?format=markdown|json|pdf|docx 导出事实快照。2026-10-12新增PDF/DOCX本地排版，不调用模型；PDF嵌入仓库OFL中文字体，DOCX为可编辑正文；正文超过2MB/20000行返回413，不静默截断，依赖/字体暂不可用503。关联判题仅证明生成时该次结果，教育/技能/经历属于用户声明，不能作为专业能力或岗位录用认证。缺失404、损坏409，不覆盖损坏内容。FILEMATE_ENABLE_RESUME=0 返回503，VITE_ENABLE_RESUME=false隐藏入口，数据保留。

## 学期模式（AUD-05c）

GET /api/semester 返回当前课程/任务或null。POST /api/semester/preview 接受schema_version=1、revision、title、start_date/end_date（最多366天）、courses（1–20门，标识唯一；目标、每周10–600分钟、weekday=0–6；可关联自己资料及学期内考试日期）。预览不创建学期；返回周数、任务数、原完成数量、确认token。POST /api/semester/confirm 接受config、confirmed=true、confirmation_token；token绑定提出配置、现有进度和资料存在状态，过期/变更409；重复确认不重复创建。替换前把旧课程和进度存为semester_history，当前任务重新开始。PATCH /api/semester/tasks/{id} 接受revision、completed，修订冲突409；完成时保存实际时间，不推断成绩。类型/日期/数量错误422；自己的任务缺失404；损坏数据409保留。FILEMATE_ENABLE_SEMESTER=0独立503，VITE_ENABLE_SEMESTER=false隐藏入口。

## 成长报告（AUD-05d）

POST /api/growth/reports 接受start_date、end_date、time_zone=Asia/Shanghai（UTC+8日期边界，最多366天，不能选未来）。在一致只读快照中汇总有效题目对应的客观作答、当前有效编译器完成事件、实际面试回答和学期任务完成时间。坏题/修订前不适用证据/已撤销编程结果不进入统计；面试分数要求有效模型分析引用，不计本地回退。每类记录保留ID、时间、回读入口，5条只是摘要展示门槛。旧学习计划没有逐日完成时间，仅报告生成时的完成快照，不把更新时间当作实际完成时间。无记录为待评测，不造提升幅度、时长、准确率、能力或岗位评价。

GET /api/growth/reports 返回最近30份；GET /api/growth/reports/{id} 返回持久历史快照及前20条依据；GET /{id}/evidence?offset=0&limit=20 完整分页（limit≤100）；GET /{id}/export?format=markdown|json|pdf 包含全部依据。2026-10-12新增PDF沿用保存快照，本地中文排版不调用模型；2MB/20000行以上明确413，建议缩小期间或使用原格式，字体/依赖不可用503。历史报告是当时快照，后续删除不重写过去统计；彻底隐私删除应一并移除有关报告。损坏409、跨空间/缺失404，通用Artifact编辑器禁止修改这些报告。FILEMATE_ENABLE_GROWTH_REPORT=0独立503、VITE_ENABLE_GROWTH_REPORT=false隐藏组件。

### 连续复练日期边界修复

重复正确复练的间隔上限365天，ease_factor限制1.3–3.0，旧异常数值安全归一。此前无上限指数增长会导致日期溢出500；50次连续正确作答回归已覆盖。该间隔是平台复练规则，不是记忆效果实验结论。

## 个人整包导出与自助恢复（AUD-05e）

GET /api/privacy/export?format=backup|json 导出当前空间的业务表，排除accounts/account_sessions/account_attempts/schema_migrations/操作确认凭据。JSON含业务数据及自己的最小操作审计，不包含文件正文，不能作为恢复输入。默认backup是签名ZIP，含业务数据与该空间inbox/archive托管文件；不跟随链接/重解析点/硬链接，不复制外部原文件，不包含环境变量、API凭据或签名私钥。两路导出并发上限；容量超过限制拒绝生成残缺备份。

POST /api/privacy/restore-preview 以multipart file上传签名ZIP（≤25MB），校验当前学习空间归属、签名、条目摘要、路径、schema（自助格式从v26开始，拒绝未来schema）和容量；返回backup_id、15分钟确认token、备份时间、当前/拟恢复记录与文件数量、整体替换说明。原数据保持不变。预览备份在此空间的受限临时目录暂存，成功恢复后清除；取消/超时的清理由AUD-06保留维护处理。

POST /api/privacy/restore 接受backup_id、confirmation_token、confirmed=true。校验绑定的当前业务与文件修订；有其他窗口请求或后台处理/判题任务时409。该空间短时阻止新请求，其他空间不受影响。文件先暂存并交换，所有业务表在同一SQLite事务中替换并检查foreign_key，任何失败恢复原文件与原业务数据；数据库故障503（只影响该操作）。成功最小审计、清理临时副本，重复确认不重放恢复。清理失败显式cleanup_pending=true，不能宣称副本已清除。旧文件处理会话与execution_records恢复为失败历史，不能重放旧确认/撤销；登录状态、密码与API密钥不恢复。API响应no-store，签名私钥保留在当前空间受操作系统目录权限保护的文件中（Windows chmod不等同于独立OS密钥库），不发送客户端。

自助上限：压缩25MB、展开128MB、业务数据32MB、托管文件5000个；更大规模使用现有管理员离线备份/恢复工具。备份只能恢复到同一学习空间且签名配置未变更；跨账号迁移及已注销账号恢复不在此合同内。FILEMATE_ENABLE_PERSONAL_DATA=0独立503，VITE_ENABLE_PERSONAL_DATA=false隐藏面板。

## 编程提交永久删除（AUD-06a）

GET /api/programming/submissions/{id}/delete-preview 返回源码/事件/相关简历与成长报告/个人事实关联的影响数量、notice和15分钟绑定当前数据修订的确认token。评测queued/running时409。DELETE同一路径需confirmed=true和confirmation_token；当前空间其他请求活跃时409，等待后重新预览。原产物与coding_submissions/events真正删除；相关简历和成长报告整份删除（避免伪造改写历史统计），当前resume_profile解除该作品引用并提高revision；技能目标保留，证据将重新评估为不可用。缺失或跨空间404，预览变化409，重复已完成确认不重复审计。日志只记录操作与数量，不保存源码。已下载备份及第三方模型留存不属于此操作的删除范围。

## 账号注销与数据保留（AUD-06b/c）

GET /api/auth/delete-preview 仅当前登录账号可用；绑定全部业务记录与托管文件的流式修订，不受整包导出的容量限制。POST /api/auth/delete 接受confirmed=true、64位confirmation_token、当前password；要求JSON与X-FileMate-Action:account，重新验证密码并限流。其他在途请求或后台处理/编译阻止注销。错误密码401、过期/变更409、主库事务失败503且恢复账号/目录。账号主库事务撤销全部登录、删除密码和恢复码哈希；资料目录先暂存，失败回滚。签名阶段记录在启动前按主库提交结果恢复；成功仅保留操作、空间摘要、数量、时间和状态。已提交确认可重复读取结果，不重放删除。cleanup_pending=true时不可宣称服务内所有副本已清除；每分钟及重启时重试。Cookie清除，前端只清除此账号当前浏览器的密钥；其他设备/已下载备份和第三方供应商留存仍需用户或维护者处理。

GET /api/privacy/retention 返回实际保留配置：匿名空间默认连续90天不活动后清理，FILEMATE_GUEST_RETENTION_DAYS支持7–3650天；注册账号不按该期限删除。旧匿名空间没有有效活动时间的，首次维护才开始完整宽限期。活跃请求、注册空间和后台执行任务保护；每60秒扫描候选，只有需清理的空间才打开数据库。DELETE /api/privacy/restore-preview 接受backup_id和confirmation_token，取消并清理其恢复预览；其他仍有效的同包预览保留。过期确认及无有效确认的ZIP副本每分钟清理。恢复清理失败的生成目录使用签名归属记录重试，成功后更新重复确认回执，不允许任意路径删除。

管理员快照支持个人备份签名文件、隐私活动与删除账本，排除服务内临时预览、已经提交删除的暂存副本与恢复回滚目录。恢复至新目录时将仍在原逻辑数据目录内的最新有效删除账本合并；有未恢复的注销阶段或签名轮换则拒绝恢复。启用恢复目录前必须保留最新删除账本与对应身份签名配置；若原数据卷已丢失，应从独立运维保管中恢复最新账本，不能仅依赖旧业务备份。服务启动依该账本拒绝已删除身份，并清除被旧管理员快照恢复的已注销空间/账号。下载到用户设备的备份无法远程删除。

身份签名配置优先采用环境变量；只有环境配置与备份实际使用的密钥摘要相同，才合并删除账本，无须存在同名配置文件。匿名活动记录写入或校验失败时该次请求503且不进入业务操作，活跃计数正常释放，修复存储后可重试；不吞掉故障后继续上传或导致空间永久被标为活跃。

## 网站与本机数据边界（AUD-07）

GET /api/privacy/boundary 公开返回storage_location=server|local_machine、storage_notice、key_notice、model_notice、camera_notice、speech_notice、guest_inactive_days、retention_notice；不返回目录、密钥或账号。部署身份模式anonymous表示网站服务器私有分库，local表示运行服务的设备。面试FILEMATE_INTERVIEW_LOCAL_ONLY仅限制该功能模型评分，不等于整个网站离线，也不决定资料保存位置。GET /trust/overview附同一boundaries，guarantees不再泛化本机保存。

GET /api/llm/status新增credential_storage=browser|system，前端按该模式选择密钥库，包括以回环地址访问的匿名网站；不得仅按URL误用桌面凭据接口。网站自带密钥当前浏览器按账号/游客空间加密，主动AI时经本站临时转发；本机系统凭据和部署环境配置独立。浏览器加密不等于隔离同源恶意脚本，需保留CSP与依赖控制；第三方模型留存由其政策决定。

上传页先读取实际说明，说明未就绪时不允许选取或投放资料；读取失败可重试，不能显示假落点。资料导入/阅读不调用模型，生成笔记/练习/讲解、面试内容分析和代码复盘需主动授权对应正文/片段/回答/代码外发。摄像头/录像不上传，但提交的文字/节奏/观察摘要保存在当前学习空间。浏览器语音识别和TTS可能在线，数字人按所选SpeechSynthesisVoice.localService显示设备/在线/未确认来源；默认声线不保证离线。

## 2026-10-10 视觉与讲话展示

没有新增API/schema。视频模块在用户开启摄像头并主动开启本地观察后，以同源Worker实时展示FaceLandmarker的微笑/皱眉/张口系数（0–100）及姿态；数值不是情绪概率。实时原始系数不发送/保存，提交仍只使用原VisualMetrics动作摘要。无脸、低光、停止/异常清空读数。数字人使用连续SVG/CSS讲解动画，随语音实际状态启停、减少动态关闭；没有音素/音频输出，不保证精确唇形同步。


2026-10-16 面试教练开发候选：业务 schema27 追加回答版本、已进入问题、场次授权、分析运行与幂等操作表；schema26回答启动时原文原时间回填，旧写入同步捕获版本。尚未完成本批整体验收，未部署；治理schema2不变。


### 2026-10-17 逐题面试教练候选（默认关闭）

业务 schema27；治理schema2不变。FILEMATE_ENABLE_INTERVIEW_COACH=1 开启新写入，默认0；VITE_ENABLE_INTERVIEW_COACH=true 开启新界面，默认false。关闭保留原训练和版本只读。REVIEW总开关、LOCAL_ONLY、知识讲解和私有资料限制优先；不默认外发任何音视频。POST /interviews 只有 allow_external_analysis=true 才授权该场外发，省略/null/false均不授权；旧 answers 先保存原文再可选分析，失败不丢回答。

| 方法/路径 | 合同 |
| --- | --- |
| GET /interviews/{id}/coach | 兼容session、revision、displayed_index、phase(question/feedback/summary)、external_consent、consent_revision、provider_identity、current_attempt、active_run_id、pending_retries、data_error；过期运行仅标interrupted，不重放 |
| POST /interviews/{id}/coach/answers | answer(1–12000非空白)、question_index(0–100)、request_key(16–80字母数字下划线短横线)、expected_revision、expected_attempt_id(null或当前版本ID)、可选既有fluency_metrics/visual_metrics；回答先保存，显示feedback，不自动切题 |
| GET /interviews/{id}/turns/{turn_id}/attempts | limit=20(1–100)、before_version可选正整数；items版本倒序、next_before_version，不跨场次 |
| POST /interviews/{id}/coach/consent | allowed、expected_revision、request_key；只授权当前场次及服务端提供商身份，撤销使在途结果失效 |
| POST /interviews/{id}/coach/analysis | attempt_id、consent_revision、expected_revision、request_key；60秒截止、每次≤30秒，只有格式错误允许一次纠正；每场一个在途运行 |
| POST /interviews/{id}/coach/advance | from_index、expected_attempt_id、expected_revision、request_key；进入下一题或summary，已进入题冻结 |

写成功均返回 {snapshot,receipt}，receipt含kind/request_key及受限attempt_id/run_id/target_index。同键同操作返回原回执及最新快照；同键异文或异操作409，不重复保存或调用模型。末次回答是当前版本，失败时score=null，历史成功仅在历史中；显式分析重试使用新key。新分析使当前报告失效，原Artifact保留，需重新生成当前报告。旧 /analyze 的 external_consent=true 是单次授权，不升级为后续自动授权。

错误信封沿用success/data/error；data可含error_code、retryable、run_id、attempt_id。参数422、跨空间404、修订/并发/授权冲突409、私有资料403、模型故障502、累计额度429、治理或关闭503。无供应商异常原文、正文或密钥。新接口不替代现有身份/CSRF写保护；密钥只在请求上下文使用，不写入上述五张表。

### 逐题面试隐私与恢复（2026-10-17 候选）

删除预览增加`answer_attempts`、`analysis_runs`、`coach_actions`，`reports`计入全部历史报告；确认指纹绑定当前教练修订。清空覆盖全部版本的内容／视觉派生结果并撤销在途写资格，保留回答与语音节奏。关闭REVIEW后仍允许读取、导出、取消、清空和确认删除；禁止新增报告和外发分析。个人备份动态包含五张新表；有running/cancelling分析时拒绝覆盖恢复。恢复清除本场外发授权，将在途运行改为interrupted；管理员恢复先校验原哈希、库事实与删除账本，再对新目录的业务库事务规范化并检查外键，结果增加`normalized_coach_databases`，始终`activated=false`，不修改治理库及原备份。schema26管理员副本先保留原字节，首启追加迁移和回填。

### 面试审阅修复补充（2026-10-17）

`POST /interviews/{id}/coach/focus`接收`request_key`、`expected_revision`和`question_index`（已答题索引，null表示已完成场次汇总），仅切换阅读位置，不新增回答、不推进提交进度，不改冻结题目。允许完成后在原场次重答和重试。新端点同样受COACH写开关、认证及空间权限保护。

授权开启仍严格比较revision；明确撤销`allowed=false`允许使用小于等于当前revision的已知修订，直接收紧当前权限，保证分析claim增加revision后仍可撤销；同键回执规则不变。保存回执`receipt.attempt_id`是本次操作归属，`snapshot.current_attempt`可能属于另一个较新版本，调用方不得混用或对较新版本自动分析。语音派生指标由服务端计算保存；报告按attempt/run/source_revision及分析pending使当前显示失效。
# 面试 2.0 统一配置（业务 schema28，2026-10-19）

复用现有身份／空间路由、CORS、访问控制与请求限流；以下草稿只属于当前空间的数据库。无额外用户画像表。

| 接口 | 合同 |
| --- | --- |
| `GET /interview/configuration` | `{success,data:{enabled,draft,capabilities}}`；关闭写入仍可读。`draft={revision,version_token,content,updated_at,error}`；无草稿revision0/version_token=null/content=null；损坏时保留记录并返回可恢复错误。能力明确标记fixed_questions、timing_active=false、creator_active=false。 |
| `PUT /interview/configuration/draft` | `{content,expected_revision,expected_token,request_key}`；content包含configuration、target_role≤120、source_id≤64、project_name≤120、project_details≤6000；严格拒绝未声明字段（包括权限）。expected_token必填，取最新读取的version_token，无草稿时为null；request_key为12–80位字母数字下划线或连字符。同一最新请求及内容可重试；过期revision／token或同key变更内容409，关闭503，校验失败422。保存是显式替换当前草稿；读取不覆盖本地输入。 |
| `POST /interviews` | 原合同保留，新增可选configuration。若提供，必须与scenario/difficulty一致；不支持的组合422且不创建会话。配置与会话同事务保存为不可变快照。关闭新写入时带配置请求503，省略配置的旧请求仍可用。 |
| `GET /interviews/{id}` / coach快照 | 新增configuration投影；origin=snapshot/legacy/unavailable。旧数据时长未知为null，原scenario保留；损坏配置仍可读原题和回答。 |

configuration严格字段：schema_version=1；category=general/technical/project/creator/learning_expression；track必须属于category；language=zh-CN/en-US；difficulty=入门/标准/压力面（UI“进阶”对应旧压力面难度）；duration_minutes为1–60整数（含3/5/10/15/30预设与自定义；目标，未计时）；difficulty_strategy=standard/challenge；question_strategy=fixed/random/ai/mixed；media_preferences包含camera/microphone/transcription/local_recording/post_analysis布尔意向，默认全false，不能授予权限。默认general/general、中文、标准、10分钟、standard、fixed。英文和challenge只支持general/general，二者不可叠加；creator及非fixed模式仅草稿可保存，启动拒绝。

映射：general/general→求职面试、general/hr→HR面；technical/technical→技术面、technical/algorithm→算法面；project/project→项目面、competition→竞赛答辩、academic→保研复试；learning_expression/explain→知识讲解；英文综合→英语面，挑战综合→压力面。知识讲解仍受本地分析限制。未提供configuration的历史请求维持原选题合同。

草稿version_token复用最新保存请求的标识，不是认证凭据。个人备份和管理员快照恢复时重新生成此标识，防止恢复旧revision后旧标签页覆盖新内容；恢复无草稿表的旧备份时为null，同样拒绝持有旧标识的保存。标识与revision均匹配才允许新保存，网络重试保留同一request_key与原payload。恢复历史会话后“再练一次”保留实际场景、目标时长和媒体意向；未知旧场景可回看，但新建前须重新选择方向。

表`interview_session_config`以interview_id为主键和级联外键；表`interview_configuration_draft`为当前空间唯一、带revision的草稿。个人导出、签名备份、管理员快照、整空间删除均通过动态表集合覆盖新表；恢复schema27等无新表备份时配置按旧模式只读投影。草稿不存AI／媒体权限，不自动请求设备或分析；既有恢复授权撤销继续生效。单场删除级联移除快照，独立草稿由用户显式保存替换或整空间删除清除。关闭功能不降级数据库；二进制回退需迁移前完整快照并在新目录验证，不承诺任意降级。

### Interview 2.0 Stage 3 — continuous runtime (schema29)

`FILEMATE_ENABLE_INTERVIEW_RUNTIME=1` plus COACH=1 and CONFIG enabled permit writes; default off. Reads, exports, reports and deletion remain available when off.

- `POST /interviews/runtime`: `{content: DraftContent, request_key: string(16..80)}` → prepared CoachSnapshot, `session.runtime` contains status/revision/version_token/seed/duration_seconds/started_at/deadline/ended_at/current_task/audience_count/ai_reserved/tasks/events/server_now/remaining_seconds/event_cooldown_seconds. Same preparation key and digest replays the same session; changed content conflicts.
- `GET /interviews/{id}/runtime`: authoritative CoachSnapshot; expiry persists once, without AI/device/network side effects. All tenant scoped; another space receives404.
- `POST /interviews/{id}/runtime/commands`: `{kind,request_key,expected_revision,expected_token,task_index?,answer?,expected_attempt_id?,fluency_metrics?,visual_metrics?}` → `{snapshot,receipt}`. Kinds: start/resume/submit/advance/event/skip/finish. Revision/token refer to runtime, not coach; receipt submit includes immutable attempt_id. No pause or deadline reset. Start requires prepared, resume requires restored interrupted status. Task/attempt/revision conflicts409. Replay returns the original receipt and current snapshot, even after expiry. Only unanswered challenge can be skipped.
- `DraftContent.configuration.execution_mode`: fixed(default) or timed; timed currently Chinese fixed/random rules. Creator knowledge/commerce require project_details containing authorized facts. source_id import and AI/mixed generation are rejected422 in this stage. Media intentions never grant permission.
- `session.runtime.events` are bounded command/audience evidence records, audience comments clearly simulated (max30, cooldown15s). Task attempt_id links immutable answer evidence; no copied answer text in event records. New events invalidate report digest; countdown alone does not.
- Existing /answers, /coach/answers and /coach/advance reject timed sessions409 before model calls. /coach/focus is history-only after timed completion. AI feedback explicitly authorized, existing evidence validation applies; each claim reserves2 transports including repair, max12/session. Failures retain answers; late results after expiry/finish cannot publish.
- Restore preserves deadlines and tasks/answers, rotates runtime version tokens, interrupts running sessions, revokes AI consent. Deleting a confirmed interview cascades runtime/tasks/events; preview includes runtime_tasks/runtime_events. JSON/Markdown/PDF reports include task and simulated-comment evidence. No new six-dimension score or real-user calibration claim.

Runtime UI drafts are temporary sessionStorage records bound to the session/task/current attempt/version token and restored only after an authorized snapshot. A changed task/token/attempt preserves text and blocks a new write until explicitly cleared. Definite 4xx rejection discards cached write preconditions; ambiguous transport failure keeps the original idempotent request. No draft is sent for external AI until explicitly submitted under consent.


### Interview 2.0 Stage4：独立音频证据（本地验收）

仅 coach answers 与 runtime commands 的 `fluency_metrics` 新增 `source=browser_media_v1`。
旧 `speech_recognition` 继续可读写；旧顺序答题接口保持原合同。
新结构：`duration_seconds` 0–600；`audio` 和 `transcription` 至少一项非空。
`audio={status:measured|unavailable, summary}`；measured 必须有摘要，unavailable 必须为 null。
摘要为 `method=web_audio_energy_v1`、duration_seconds(0,600.1]、sample_rate[8000,96000]、
sample_count≥1、rms[0,1.01]、low_energy_seconds≤音频时长、clipping_ratio[0,1]、threshold=0.01。
采样数与采样率必须和时长匹配；所有数字有限，不允许额外字段。
`transcription={provider:browser_web_speech,status:completed|interrupted|denied|no_speech|unsupported,
language:zh-CN|en-US,segments,confidence}`；最多100段，每段1000字符，总计12000。
每段包含text、confidence(供应商原始估计或null)、callback_seconds[0,600]（回调时刻，不是词时间戳）。
平均confidence由已提供的段值计算，全部缺失时null；非准确率。不接收正在识别的中间态。
这些摘要只是设备上报、未经服务端核验，不影响内容评分。非法指标在请求边界返回422。
报告2.5追加audio汇总及逐题audio/transcription；旧字段保留，JSON/Markdown/PDF均可导出。
已有回答JSON列及备份承载摘要，无schema迁移。删除练习同步删除各回答版本及其摘要。

`VITE_ENABLE_INTERVIEW_AUDIO=true`（默认关闭，需coach启用）开启浏览器独立录音与转写面板。
原始录音Blob仅在页面内存：单次10分钟/20MiB，单页60MiB/30段；不上传、不写SQLite、不进备份。
刷新/离页清除，用户可在当前页面逐题回听、单独导出（沿用用户下载目录设置）。
浏览器语音转写为单独授权的可选服务，可能向浏览器厂商发送音频；授权与录音、微软自然语音分别控制。
