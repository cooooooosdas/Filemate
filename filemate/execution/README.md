# 执行层（execution）

> 负责人：徐书和
> 状态：✅ 已完成

## 功能说明

执行层负责 FileMate 的"落地"操作——AI 理解完文件内容后，执行层真正去移动文件、重命名、生成日历、持久化数据。

## 模块总览

| 模块 | 文件 | 职责 |
|------|------|------|
| **FileOps** | `file_ops.py` | 文件 I/O 基础操作（移动/重命名/复制/删除/哈希/后缀判断） |
| **SQLiteStorage** | `storage.py` | SQLite 数据库（4 张表：sessions / processed_files / operation_log / user_rules） |
| **CalendarBuilder** | `scheduler.py` | 生成 RFC 5545 兼容 .ics 日历文件 |
| **Archiver** | `archiver.py` | 按"课程/分类"二级目录归档文件 |
| **BatchProcessor** | `batch_processor.py` | 并发批量处理（信号量限流 + 进度回调） |

## 依赖安装

```bash
pip install icalendar>=6.0
# SQLite3 为 Python 标准库，无需额外安装
```

## 使用示例

### FileOps

```python
from filemate.execution import FileOps, OpResult

ops = FileOps()

# 计算哈希（用于去重）
file_hash = ops.compute_hash("课件.pdf")

# 移动文件
result: OpResult = ops.move("demo.docx", "archive/操作系统/课件/demo.docx")
if result.success:
    print(f"已移动到: {result.dest_path}")

# 重命名
result = ops.rename("old.docx", "新文件名.docx")

# 判断支持的文件格式
assert ops.is_supported("a.pdf")    # True
assert ops.is_supported("a.zip")    # False
```

### SQLiteStorage

```python
from filemate.execution import SQLiteStorage

storage = SQLiteStorage("filemate.db")
storage.init_schema()

# session 生命周期
storage.create_session("sid-1", "/path/to/file.pdf")
storage.update_session("sid-1", category="课件", confidence=0.92)
session = storage.get_session("sid-1")

# 去重
if storage.is_duplicate(file_hash):
    print("文件已处理过，跳过")
else:
    storage.record_hash(file_hash, "sid-1")

# 操作日志
storage.log_operation("sid-1", "classify", "课件 0.92")

# 用户规则
storage.add_rule("category_override", "实验.*", "作业", priority=5)
```

### CalendarBuilder

```python
from filemate.execution import CalendarBuilder, CalendarEvent

builder = CalendarBuilder()
events = [
    CalendarEvent(
        summary="实验三截止",
        start="2026-04-15",
        location="线上提交",
        description="请按时提交实验报告",
    ),
]
builder.save(events, "schedule.ics")
# → 双击 schedule.ics 即可导入系统日历
```

### Archiver

```python
from filemate.execution import Archiver, FileOps
from pathlib import Path

archiver = Archiver(
    base_dir=Path.home() / "FileMateArchive",
    file_ops=FileOps(),
)

# 预览目标路径（不执行移动）
dest = archiver.preview_dest(
    base_dir=archiver.base_dir,
    category="课件",
    course="操作系统",
    new_name="操作系统-课件-第三章进程同步.pdf",
)
print(f"将归档到: {dest}")

# 实际归档
result = archiver.archive(
    session_id="sid-1",
    category="课件",
    course="操作系统",
    new_name="操作系统-课件-第三章进程同步.pdf",
    source_path="/path/to/第三章.pptx",
)
```

### BatchProcessor

```python
import asyncio
from filemate.execution import BatchProcessor

async def process_one(path: str) -> dict:
    # 实际使用时，这里是 PipelineWorker 的单个文件处理逻辑
    return {"path": path, "success": True}

async def main():
    processor = BatchProcessor(process_one, concurrency=2)

    def on_progress(done: int, total: int, path: str) -> None:
        print(f"[{done}/{total}] {path}")

    results = await processor.process_batch(
        ["a.pdf", "b.docx", "c.pptx"],
        on_progress=on_progress,
    )
    # results 与输入顺序一致，单个失败不影响其他

asyncio.run(main())
```

## 数据库 Schema

### sessions

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | TEXT PK | 唯一标识 |
| source_path | TEXT | 源文件路径 |
| status | TEXT | pending/processing/done/confirmed/skipped/expired/failed |
| category | TEXT | 分类结果 |
| confidence | REAL | 置信度 [0, 1] |
| suggested_name | TEXT | AI 建议文件名 |
| entities | TEXT | 实体抽取结果（JSON） |
| milestones | TEXT | 多里程碑列表（JSON） |
| error | TEXT | 错误信息 |
| user_modified | INTEGER | 用户是否修改了 AI 建议 |
| created_at | TEXT | ISO 8601 |
| updated_at | TEXT | ISO 8601 |

### processed_files

| 字段 | 类型 | 说明 |
|------|------|------|
| file_hash | TEXT PK | 文件 SHA-256 |
| session_id | TEXT FK | 首次处理 session |
| first_seen_at | TEXT | 首次发现时间 |
| last_processed_at | TEXT | 最近处理时间 |
| process_count | INTEGER | 处理次数 |

### operation_log

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| session_id | TEXT FK | 关联 session |
| action | TEXT | parse / classify / extract / calendar / rename / confirm / reject |
| detail | TEXT | 摘要信息 |
| input_snapshot | TEXT | AI 返回原始 JSON |
| user_override | TEXT | 用户修改后的值 |
| latency_ms | INTEGER | 操作延迟（毫秒） |
| model_used | TEXT | 使用的 LLM 模型 |
| prompt_tokens | INTEGER | Prompt token 数 |
| completion_tokens | INTEGER | 回复 token 数 |

### user_rules

| 字段 | 类型 | 说明 |
|------|------|------|
| rule_id | INTEGER PK | 自增 |
| rule_type | TEXT | category_override / naming_template / course_alias |
| pattern | TEXT | 匹配模式 |
| replacement | TEXT | 替换/映射值 |
| priority | INTEGER | 优先级（越大越先匹配） |
| enabled | INTEGER | 1=启用 0=禁用 |

## 已知问题

- `BatchProcessor` 依赖调用方传入异步 worker，自身不管理 session 生命周期
- 去重仅基于文件哈希，语义去重（Embedding 相似度）为 W5 可选增强，暑期暂不实现
- `user_rules` 表已在 schema 中定义但规则引擎的读取链路尚未对接（等理解层 W3 完成后接入）
