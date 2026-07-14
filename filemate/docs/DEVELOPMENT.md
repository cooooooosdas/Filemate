# FileMate 开发指南

> 面向团队成员：如何开始写代码、调试、提交。
> 有任何问题 → 群里 @胡希。

---

## 目录

- [你的第一周](#你的第一周)
- [模块接口速查](#模块接口速查)
- [各模块实现指引](#各模块实现指引)
  - [感知层（汤新阳）](#感知层汤新阳)
  - [理解层（张金宝）](#理解层张金宝)
  - [执行层（徐书和）](#执行层徐书和)
  - [UI 层（余恒）](#ui-层余恒)
- [调试技巧](#调试技巧)
- [常见报错](#常见报错)

---

## 你的第一周

```bash
# 1. clone 仓库
git clone https://github.com/cooooooosdas/Filemate.git
cd FileMate

# 2. 创建虚拟环境 + 安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置 LLM（找胡希要 API Key）
cp .env.example .env
notepad .env    # 填入真实值

# 4. 验证环境
python -c "from filemate.llm_client import LLMClient; print('环境 OK')"

# 5. 拉你自己的分支
git checkout -b feat/你的名字
```

### 第一周目标

| 负责人 | 目标 |
|---|---|
| 汤新阳 | `python -c "from filemate.perception import FileParser; ..."` 能跑通 |
| 张金宝 | 写一个分类 Prompt，在 10 份样本上测试 |
| 徐书和 | `python -c "from filemate.execution import SQLiteStorage; ..."` 能跑通 |
| 余恒 | `python -m filemate.ui.app` 能弹出一个 Gradio 页面 |
| 杨乐 | 通读本文件和 `README.md`，有问题直接问胡希 |

---

## 模块接口速查

### 感知层入口

```python
from filemate.perception import FileParser, FileWatcher

parser = FileParser()
result = parser.parse("实验报告.docx")
# → {"raw_text": str, "metadata": {"filename": ..., "suffix": ..., "size_bytes": ...}}

watcher = FileWatcher("C:\\Downloads\\CourseFiles")
watcher.on_new_file(lambda p: print(f"新文件: {p}"))
# 启动: await watcher.run()
```

### 理解层入口

```python
from filemate.llm_client import LLMClient
from filemate.understanding import Classifier, EntityExtractor, MilestoneDetector, Namer

llm = LLMClient()   # 自动从 .env 读配置
clf = Classifier(llm)
result = clf.classify("实验三实验报告...", filename="lab3.docx")
# → {"category": "作业", "confidence": 0.92, "course_name": "操作系统"}

ext = EntityExtractor(llm)
entities = ext.extract(raw_text)
# → {"course_name": ..., "task_description": ..., "deadline": "2026-04-15", ...}

det = MilestoneDetector(llm)
milestones = det.detect(raw_text)
# → [{"event": "报名截止", "date": "2026-05-01", "order": 1}, ...]

namer = Namer(llm)
name = namer.generate(category="作业", course="操作系统", task="实验三", deadline="0415")
# → "[操作系统]-[作业]-[实验三]-[0415]-[待处理]"
```

### 执行层入口

```python
from filemate.execution import FileOps, CalendarBuilder, Archiver, SQLiteStorage

ops = FileOps()
ops.ensure_dir("D:\\Archive")
result = ops.move("a.docx", "D:\\Archive\\课程\\作业\\a.docx")
# → OpResult(success=True, dest_path="D:\\Archive\\...")

cal = CalendarBuilder()
cal.save([CalendarEvent("实验三截止", "2026-04-15")], "out.ics")

store = SQLiteStorage("filemate.db")
store.init_schema()
store.create_session("abc123", "/path/a.docx")
store.log_operation("abc123", "classify", "作业 0.92")

archiver = Archiver("D:\\Archive", ops)
archiver.archive("abc123", category="作业", course="操作系统", new_name="[操作系统]-[作业]-[实验三]-[0415]-[待处理].docx")
```

### Pipeline

```python
import asyncio
import uuid
from filemate.core import PipelineWorker, ProcessingSession
from filemate.execution.storage import SQLiteStorage

queue = asyncio.Queue()
store = SQLiteStorage()
store.init_schema()

async def on_complete(session):
    print(f"完成: {session.suggested_name}")

worker = PipelineWorker(queue, on_complete=on_complete, stages=[...])

# 入队
sid = uuid.uuid4().hex[:12]
session = ProcessingSession(session_id=sid, source_path="a.docx")
await queue.put(session)

# 启动消费者
asyncio.create_task(worker.run())
```

---

## 各模块实现指引

### 感知层（汤新阳）

**目标：** 实现 `FileParser.parse(path)`，返回 `{"raw_text": str, "metadata": dict}`。

**开发顺序：**

1. 先写 `parsers/word.py`（最简单，先用它验证流程）
2. 再写 `parsers/pdf.py`
3. 再写 `parsers/ppt.py`
4. 最后写 `watcher.py` + `ocr.py`

**Word 解析示例（给你参考怎么写）：**

```python
# filemate/perception/parsers/word.py
from docx import Document

class WordParser:
    def parse(self, path):
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return {
            "raw_text": text[:500_000],  # 截断 50 万字
            "metadata": {"suffix": "docx", "size_bytes": Path(path).stat().st_size},
        }
```

**异常处理规范：**

- 文件不存在 → 返回 `{"raw_text": "", "metadata": {...}, "error": "文件不存在"}`
- 解析失败（加密 PDF、乱码）→ 同样返回带 `error` 字段的结构，**不要抛异常**
- 大文件截断到 50 万字（控制 LLM token 消耗）

**验证命令：**

```bash
python -c "
from filemate.perception import FileParser
p = FileParser()
import sys
path = sys.argv[1] if len(sys.argv) > 1 else 'test.docx'
try:
    r = p.parse(path)
    print('raw_text 长度:', len(r.get('raw_text', '')))
    print('metadata:', r.get('metadata'))
except Exception as e:
    print('FAIL:', e)
" 你的文件.docx
```

### 理解层（张金宝）

**目标：** 四个子模块都调用 `llm_client.call_structured()` 拿 JSON。

**核心模式（所有模块通用）：**

```python
from filemate.llm_client import LLMClient

class Classifier:
    def __init__(self, llm_client, rules_path=None):
        self.llm = llm_client
        self.rules = self._load_rules(rules_path)

    def classify(self, text, filename=""):
        # 1. 先规则引擎兜底
        hit = self._keyword_hit(text)
        if hit:
            return {"category": hit, "confidence": 0.9, "course_name": None}

        # 2. 走 LLM
        prompt = Path("filemate/understanding/prompts/classify.md").read_text()
        result = self.llm.call_structured(
            prompt=prompt,
            messages=[{"role": "user", "content": f"文件名: {filename}\n\n{text[:2000]}"}],
        )
        return result
```

**分类 Prompt 要求（写 classify.md 时）：**

- 输出严格 JSON，字段固定：`category / confidence / course_name / reason`
- `category` 只能是 `课件 / 作业 / 竞赛通知 / 考试通知 / 待确认`
- `confidence` 是 0–1 的浮点数
- 没把握时 category 输出 `待确认`，confidence 输出 `< 0.7`

**Prompt 迭代流程：**

```
写 v1 → 用 10 份样本测 → 记录错误 → 分析错误类型 → 写 v2 → ...
最终版归档到 docs/PROMPT_LIB.md
```

**准确率验收标准：**

- W3 末：≥ 85%（50 份样本）
- W6 末：≥ 90%，接近 95% 需记录瓶颈分析

### 执行层（徐书和）

你的代码已经基本写完了（胡希写的框架），你只需要：

1. 通读 `execution/storage.py` / `file_ops.py` / `scheduler.py` / `archiver.py`
2. 跑一遍 `pytest tests/test_file_ops.py tests/test_calendar.py` 确认通过
3. 补充 `batch_processor.py` 的测试（目前没有）
4. 根据反馈修 bug

**SQLite 表结构（已在 storage.py 里写好）：**

- `sessions` — 每个文件一个 session 记录
- `processed_files` — 文件哈希去重
- `operation_log` — 操作日志（供 Prompt 迭代分析）
- `user_rules` — 用户自定义规则

### UI 层（余恒）

**目标：** 四个 Tab 的 Gradio 界面。

**Tab 结构：**

| Tab | 功能 | 后端接口 |
|---|---|---|
| 导入 | 文件上传 + 文件列表 | `BackendAPI.submit(path)` |
| 分类预览 | 建议分类 + 置信度 + 确认/修改按钮 | `BackendAPI.get_queue()` |
| 命名预览 | 原始名 vs 建议名 + 编辑框 | `BackendAPI.confirm(session_id, accepted, edits)` |
| 日程预览 | 时间轴视图 + 导出 .ics | `BackendAPI.get_operations(session_id)` |

**最小可行界面（先跑通这个）：**

```python
import gradio as gr
from filemate.ui.backend_api import BackendAPI

api = BackendAPI(pipeline_worker, state_store)

with gr.Blocks(title="FileMate") as demo:
    f = gr.File()
    out = gr.Textbox(label="处理结果")
    btn = gr.Button("处理")
    btn.click(lambda files: api.submit(files[0].name), inputs=f, outputs=out)

demo.launch()
```

**开发技巧：**
- Gradio 官方文档：https://www.gradio.app/docs
- 用 `gr.Timer(interval=2)` 每 2 秒刷新一次队列状态
- `gradio` 支持 `pip install "gradio[fetch]"` 开启文件下载功能

---

## 调试技巧

### 1. 只跑感知层（不调 LLM，不花钱）

```python
from filemate.perception import FileParser
p = FileParser()
print(p.parse("test.docx"))
```

### 2. 只跑理解层（用假 LLM 响应）

```python
class FakeLLM:
    def call(self, **kw): return '{"category": "待确认", "confidence": 0.5}'
    def call_structured(self, **kw): return {"category": "待确认", "confidence": 0.5}

from filemate.understanding import Classifier
clf = Classifier(FakeLLM())
print(clf.classify("随便什么文本"))
```

### 3. 看 LLM 实际发出的请求

```bash
python main.py a.docx -v
# 或代码里加:
import logging; logging.basicConfig(level=logging.DEBUG)
```

### 4. SQLite 浏览器

```bash
# 安装 DB 浏览器
pip install sqlite-utils
sqlite-utils filemate.db "SELECT * FROM sessions LIMIT 5"
```

---

## 常见报错

| 报错 | 原因 | 解决 |
|---|---|---|
| `LLM_API_KEY 未配置` | `.env` 不存在或 Key 为空 | 复制 `.env.example` → `.env`，填入 Key |
| `不支持的格式: xxx` | 感知层还没实现该格式的解析器 | 先实现，或先用 Word/PDF |
| `icalendar 未安装` | 缺依赖 | `pip install icalendar` |
| `gradio` 导入失败 | 缺依赖 | `pip install gradio` |
| `pipeline.py: NotImplementedError` | 理解层还没写完 | 按分工先实现对应模块 |
| `sqlite3.OperationalError: database is locked` | 多线程同时写 SQLite | 已在 storage.py 用 WAL 模式 + 线程本地连接解决，若仍出现请报告 |

---

*本文件随项目进展持续更新。有问题随时 @胡希。*
