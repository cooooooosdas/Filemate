# FileMate

基于多模态语义理解的课程文件归档与任务提醒助手。

> 国家级大学生创新创业训练计划项目
> 2026 暑期开发阶段 | 负责人：胡希
> 成员：汤新阳、张金宝、徐书和、余恒、杨乐

---

## 目录

- [快速开始](#快速开始)
- [项目定位](#项目定位)
- [四层架构](#四层架构)
- [目录结构](#目录结构)
- [模块负责人与分工](#模块负责人与分工)
- [五个核心接口](#五个核心接口)
- [接口变更规则](#接口变更规则)
- [里程碑](#里程碑)
- [运行测试](#运行测试)
- [代码风格](#代码风格)
- [Git 工作流](#git-工作流)
- [周会机制](#周会机制)
- [常见问题](#常见问题)
- [项目文档索引](#项目文档索引)

---

## 快速开始

### 环境要求

- Python >= 3.10（推荐 3.11/3.12）
- Windows 11（主要开发平台）/ macOS / Linux
- Git

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/cooooooosdas/Filemate.git
cd FileMate

# 2. 创建虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 LLM
cp .env.example .env
# 用文本编辑器打开 .env，填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
# .env 不会被提交到 Git（已在 .gitignore 中）

# 5. 验证安装
python -c "from filemate.llm_client import LLMClient; print('OK')"
```

### 使用方式

```bash
# 处理单个文件
python main.py <file_path>

# 监控目录模式（持续运行，新文件自动处理）
python main.py --watch-dir C:\Users\胡希\Downloads\CourseFiles

# 跳过 .ics 生成
python main.py <file_path> --no-calendar

# 指定数据库路径
python main.py <file_path> --db D:\data\filemate.db

# 详细日志
python main.py <file_path> -v
```

---

## 项目定位

**FileMate 解决什么问题：** 大学生的课件、作业、竞赛通知、考试通知散落在电脑里，命名杂乱，deadline 藏在文档深处容易漏掉。

**产品做三件事：**

1. 你拖一个文件进来 → 系统自动判断它是什么课、什么类型
2. 自动生成规范的文件名，一眼看出课程 / 类型 / 截止时间
3. 长通知（竞赛通知）→ 自动提取所有关键时间节点，生成日历提醒

**用户核心动作 = "点确认"。** AI 建议好之后，用户点一下确认，系统执行。

---

## 四层架构

```
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │   感知层      │      │   理解层      │      │   确认层      │      │   执行层      │
  │ perception/  │ ────▶│ understanding│ ────▶│     ui/      │ ────▶│  execution/  │
  │              │      │              │      │              │      │              │
  │ • 文件解析    │      │ • 分类        │      │ • Gradio     │      │ • 文件归档    │
  │ • 目录监控    │      │ • 实体抽取    │      │   四 Tab     │      │ • .ics 生成  │
  │ • OCR        │      │ • 里程碑识别  │      │ • 确认/修改  │      │ • SQLite     │
  │              │      │ • 命名生成    │      │ • 进度展示   │      │ • 哈希去重   │
  └──────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
        ▲                     ▲                    ▲                    ▲
        │                     │                    │                    │
  watchdog / PyPDF2    规则引擎 + LLM       用户交互界面            os / shutil
  python-docx           Prompt 工程           Gradio 4.x             icalendar
  PaddleOCR（可选）
        │                     │                    │                    │
        └─────────────────────┼────────────────────┼────────────────────┘
                              │                    │
                       ┌──────▼──────┐      ┌──────▼──────┐
                       │   core/     │      │   core/     │
                       │ Pipeline    │      │  Session    │
                       │ Worker      │      │ 状态机      │
                       │ (异步队列)   │      └─────────────┘
                       └─────────────┘
```

**数据流：** 文件 → 感知层提取文本 → 理解层分类/抽取/命名 → 确认层展示给用户 → 用户确认 → 执行层归档 / 生成 .ics / 写入 SQLite

---

## 目录结构

```
FileMate/
├── .env.example                 # 环境变量模板（复制为 .env 填入真实值）
├── .gitignore                   # Git 忽略规则
├── requirements.txt             # Python 依赖
├── main.py                      # 命令行入口（单文件 + watch 模式）
├── README.md                    # 本文件
│
├── datasets/                    # 样本数据（不入库）
│   ├── raw/                     #   课程文件样本（PDF / Word / PPT / 截图）
│   └── long_text/               #   长文本样本（竞赛通知 / 大创通知）
│
└── filemate/                    # 主包
    ├── __init__.py
    │
    ├── llm_client/              # ── LLM 统一封装（胡希）──
    │   ├── __init__.py
    │   ├── client.py            #   LLMClient — 统一调用入口（含重试 / 超时 / JSON 解析）
    │   ├── config.py            #   LLMConfig — 从 .env 加载配置
    │   ├── exceptions.py        #   异常体系（LLMAPIError / LLMTimeoutError / LLMRateLimitError）
    │   ├── providers/
    │   │   ├── __init__.py
    │   │   ├── base.py          #   BaseLLMProvider — 抽象基类
    │   │   └── step_speed.py    #   StepSpeedProvider — 对接 Step 3.7 Speed
    │   └── models/
    │       ├── __init__.py
    │       ├── message.py       #   Message 模型
    │       └── response.py      #   LLMResponse 模型
    │
    ├── perception/              # ── 感知层（汤新阳）──
    │   ├── __init__.py
    │   ├── file_parser.py       #   FileParser — 统一入口，按后缀选解析器
    │   ├── watcher.py           #   FileWatcher — watchdog / 轮询监控目录
    │   ├── ocr.py               #   OCRBackend — PaddleOCR 封装（可选）
    │   └── parsers/
    │       ├── __init__.py      #   解析器注册表
    │       ├── pdf.py           #   PDFParser（PyPDF2 / pdfplumber）
    │       ├── word.py          #   WordParser（python-docx）
    │       └── ppt.py           #   PPTParser（python-pptx）
    │
    ├── understanding/           # ── 理解层（张金宝）──
    │   ├── __init__.py
    │   ├── classifier.py        #   Classifier — 关键词规则兜底 + LLM 分类
    │   ├── entity_extractor.py  #   EntityExtractor — 抽取课程名 / 截止时间等
    │   ├── milestone_detector.py #  MilestoneDetector — 长通知多时间节点识别
    │   ├── namer.py             #   Namer — 生成规范文件名
    │   ├── rules/
    │   │   └── keywords.json    #   关键词规则库
    │   └── prompts/
    │       ├── __init__.py
    │       ├── classify.md      #   分类 Prompt 模板
    │       ├── extract.md       #   实体抽取 Prompt 模板
    │       ├── milestone.md     #   多里程碑 Prompt 模板
    │       └── naming.md        #   命名生成 Prompt 模板
    │
    ├── core/                    # ── Pipeline + Session（胡希）──
    │   ├── __init__.py
    │   ├── session.py           #   ProcessingSession — 单个文件全生命周期 + 状态机
    │   ├── pipeline.py          #   PipelineWorker — 异步消费队列 + 阶段链
    │   └── state_store.py       #   SQLiteStateStore — 薄封装，委托给 execution.storage
    │
    ├── execution/               # ── 执行层（徐书和）──
    │   ├── __init__.py
    │   ├── storage.py           #   SQLiteStorage — 四张表 + 线程安全
    │   ├── file_ops.py          #   FileOps — ensure_dir / move / rename / copy / hash
    │   ├── scheduler.py         #   CalendarBuilder — .ics 生成（RFC 5545）
    │   ├── archiver.py          #   Archiver — 归档到 <base>/<course>/<category>
    │   └── batch_processor.py   #   BatchProcessor — 并发限制 + 进度回调
    │
    ├── ui/                      # ── 确认层（余恒）──
    │   ├── __init__.py
    │   ├── app.py               #   FileMateUI — Gradio 主界面（4 Tab）
    │   ├── backend_api.py       #   BackendAPI — Gradio 与后端的胶水层
    │   └── components/
    │       └── __init__.py      #   可复用 Gradio 组件
    │
    ├── tests/                   # ── 测试（全体）──
    │   ├── __init__.py
    │   ├── test_file_ops.py     #   文件操作单元测试
    │   ├── test_calendar.py     #   .ics 生成测试
    │   ├── test_classifier.py   #   分类契约测试
    │   └── test_e2e.py          #   端到端集成测试（W4 里程碑）
    │
    └── docs/                    # ── 项目文档 ──
        ├── PROMPT_LIB.md        #   Prompt 库（v1→v5 迭代记录）
        └── API_SPEC.md          #   5 个接口契约（W4 后冻结）
```

---

## 模块负责人与分工

| 模块 | 路径 | 负责人 | 状态 | 备注 |
|---|---|---|---|---|
| LLM 统一封装 | `llm_client/` | 胡希 | ✅ 已完成 | Step 3.7 Speed 供应商已对接 |
| 感知层 | `perception/` | 汤新阳 | ⬜ 待实现 | 见下方"感知层开发指引" |
| 理解层 | `understanding/` | 张金宝 | 🟡 骨架就绪 | 接口已写好，Prompt 待迭代 |
| Pipeline + Session | `core/` | 胡希 | ✅ 已完成 | 状态机 + 异步消费循环 |
| 执行层 | `execution/` | 徐书和 | ✅ 已完成 | SQLite / 文件 I/O / .ics / 归档 |
| Gradio 界面 | `ui/app.py` + `ui/components/` | 余恒 | ⬜ 待实现 | 后端 API 已封装 |
| 功能设计 + 协调 | 各模块 | 杨乐 | ⬜ 待启动 | 对齐各模块进度 |
| 测试 | `tests/` | 全体 | 🟡 部分 | 文件操作 + 日历 + 契约已覆盖 |

### 感知层开发指引（汤新阳）

你的目标是让 `FileParser.parse(path)` 返回如下结构：

```python
{
    "raw_text": "文件里的文字内容（字符串）",
    "metadata": {
        "filename": "原始文件名",
        "suffix": "文件后缀（小写，不含点）",
        "size_bytes": 12345,
    },
}
```

**开发顺序：**

1. 先实现 `parsers/word.py`（python-docx 最简单，用来验证流程）
2. 再实现 `parsers/pdf.py`（PyPDF2 / pdfplumber）
3. 然后 `parsers/ppt.py`（python-pptx）
4. 最后 `watcher.py`（watchdog 或轮询）+ `ocr.py`（PaddleOCR，可选）

验证方式：

```bash
python -c "
from filemate.perception import FileParser
p = FileParser()
print(p.parse('测试.docx'))   # 替换成你电脑上的真实文件
"
```

**模块使用示例：**

```python
from filemate.perception import FileParser

parser = FileParser()
result = parser.parse("实验报告.docx")
# {
#   "raw_text": "实验三：实现一个线程池...",
#   "metadata": {"filename": "实验报告.docx", "suffix": "docx", "size_bytes": 20480},
# }
text = result["raw_text"]
```

### 理解层开发指引（张金宝）

四个子模块的接口契约已经写在代码里，你只需要：

1. 读 `understanding/classifier.py` 里的 `classify()` 输出格式要求
2. 写 Prompt 模板到 `understanding/prompts/*.md`
3. 让 `classify()` 调用 `llm_client.call_structured()` 拿结构化 JSON
4. 用 `rules/keywords.json` 做规则引擎兜底

**开发顺序：** classifier → entity_extractor → milestone_detector → namer

**模块使用示例：**

```python
from filemate.llm_client import LLMClient
from filemate.understanding import Classifier, EntityExtractor, MilestoneDetector, Namer

llm = LLMClient()  # 自动从 .env 读取配置

# 1. 分类
classifier = Classifier(llm)
cat = classifier.classify(text="实验三：实现一个线程池...", filename="lab3.docx")
# {"category": "作业", "confidence": 0.83, "course_name": None, "reason": "关键词规则命中"}

# 2. 实体抽取
extractor = EntityExtractor(llm)
entities = extractor.extract(text)
# {"course_name": "操作系统", "task_description": "实验三", "deadline": "2026-05-20", ...}

# 3. 多里程碑识别
detector = MilestoneDetector(llm)
milestones = detector.detect(long_text)
# [{"event": "报名截止", "date": "2026-05-10", "order": 1}, ...]

# 4. 命名生成
namer = Namer(llm)
name = namer.generate(
    category=cat["category"],
    course=entities["course_name"] or "未分类",
    task=entities["task_description"] or "未命名",
    deadline=entities["deadline"] or "待定",
)
# "[操作系统]-[作业]-[实验三]-[0520]-[待处理]"
```

每个 Prompt 迭代到 v5 后归档到 `docs/PROMPT_LIB.md`。

### UI 层开发指引（余恒）

1. 读 `ui/backend_api.py`，理解 `submit / confirm / get_queue` 三个接口
2. 在 `ui/app.py` 里用 Gradio 4.x 搭四个 Tab
3. 先跑通"上传文件 → 展示解析文本"的最小链路，再逐步加功能

参考：

```bash
pip install gradio
python -m filemate.ui.app   # 或你写好的启动方式
```

**模块使用示例：**

```python
from filemate.ui.backend_api import BackendAPI
from filemate.execution.storage import SQLiteStorage
from filemate.core.pipeline import PipelineWorker
from filemate.core.session import ProcessingSession

# 1. 初始化
storage = SQLiteStorage("filemate.db")
storage.init_schema()
pipeline = PipelineWorker(stages=...)  # 见 main.py _make_stages()
api = BackendAPI(pipeline_worker=pipeline, state_store=storage)

# 2. 提交文件
result = api.submit("/path/to/lab3.docx")
# {"session_id": "a1b2c3d4e5f6", "source_path": "...", "status": "pending"}

# 3. 查询队列
queue = api.get_queue(status="pending")

# 4. 用户确认 / 拒绝
api.confirm(session_id="a1b2c3d4e5f6", accepted=True, edits={"suggested_name": "..."})

# 5. 查看操作日志
ops = api.get_operations("a1b2c3d4e5f6")
```

---

## 五个核心接口

> W4 里程碑后接口冻结，变更必须经过胡希。

| # | 接口 | 输入 | 输出 | 负责人 |
|---|---|---|---|---|
| 4.1 | 分类模块 | `text: str, filename: str` | `{category, confidence, course_name}` | 张金宝 |
| 4.2 | 实体抽取 | `raw_text: str` | `{course_name, task_description, deadline, location, extra_entities}` | 张金宝 |
| 4.3 | 多里程碑识别 | `raw_text: str` | `[{"event", "date", "order"}, ...]` | 张金宝 |
| 4.4 | 命名生成 | `category, course_name, task_description, deadline, status` | `str`（规范文件名） | 张金宝 |
| 4.5 | 执行层 | `file_path, new_name, target_dir` | `{success, error, dest_path}` | 徐书和 |

详见 `filemate/docs/API_SPEC.md`。

---

## 接口变更规则

1. **W4 前（8 月 3 日之前）：** 接口可调整，但必须先在群里告知胡希，胡希更新 `API_SPEC.md` 后你再改实现
2. **W4 后：** 接口冻结。需要变更 → 胡希评估影响 → 发版本更新
3. **私自改接口 = 阻塞他人开发**，会被记入周报

---

## 里程碑

| 里程碑 | 日期 | 验收标准 |
|---|---|---|
| **W1 启动** | 2026-07-13 | 环境搭建 + 各模块 Demo |
| **W2 感知层** | 2026-07-20 | 一个 .docx 丢进去能输出文本 + 元数据 |
| **W3 理解层** | 2026-07-27 | 分类准确率 ≥ 85%（50 份样本） |
| **里程碑 1** | **2026-08-03** | `python main.py <file>` 跑通完整流程（命令行即可） |
| **W5 执行层深化** | 2026-08-10 | Gradio 内走完完整流程 |
| **W6 确认层打磨** | 2026-08-17 | 批量导入 10 个文件，全程无需命令行 |
| **里程碑 2** | **2026-08-24** | Gradio + 批量 + 演示视频 |
| **W8 收尾** | 2026-08-31 | 阶段成果包 + 中期检查材料 |

---

## 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio

# 运行全部测试
pytest tests/ -v

# 只跑文件操作测试
pytest tests/test_file_ops.py -v

# 带覆盖率
pytest tests/ -v --cov=filemate --cov-report=term-missing
```

**测试提交要求：** 每个 milestone 前，你负责的模块必须有对应的测试用例通过。

---

## 代码风格

- **PEP 8**，缩进 4 空格
- 提交前运行 `black .` + `ruff check .`（见 `requirements.txt`）
- 所有公开函数/类必须有 docstring
- 每个 TODO 标记格式：`TODO(姓名): 描述`，方便 grep 追踪
- 日志用 `logging.getLogger(__name__)`，不用 print
- 接口函数必须写明输入输出格式（参考已有代码注释）

---

## Git 工作流

```
main (受保护，只能由胡希合并)
  │
  ├─ feat/perception-parser     (汤新阳)
  ├─ feat/classifier            (张金宝)
  ├─ feat/gradio-ui             (余恒)
  └─ ...
```

**工作方式：**

1. 从 main 拉一条新分支：`git checkout -b feat/你的模块名`
2. 开发，多次 commit（每周至少 2 次有效 commit）
3. 推送到远端：`git push -u origin feat/你的模块名`
4. 在 GitHub 上发 PR，@ 胡希 review
5. 胡希合并到 main

**禁止：**
- 直接 push 到 main
- -force push 到 main
- 提交 `.env` / `filemate.db` / `datasets/raw/*`（.gitignore 已覆盖）

---

## 周会机制

| 会议 | 频率 | 时间 | 内容 |
|---|---|---|---|
| 周站会 | 每周一 20:00 | 30 min | 上周完成 / 本周计划 / blockers |
| 里程碑评审 | W4 末 / W7 末 | 1–2 h | 端到端演示 + Bug 清理 + 下一阶段计划 |
| 结项会 | W8 末 | 2 h | 阶段总结 + 成果展示 + 开学后分工 |

**卡住超过 2 小时 → 群里喊胡希，不要自己闷着。**

---

## 常见问题

**Q：需要训练 AI 模型吗？**
> 不需要。分类、抽取、命名都是调 Step 3.7 Speed 的 API，Prompt 写好就行。

**Q：不会 Python 能参与吗？**
> 感知层、理解层、执行层、UI 层都需要写 Python。如果某块完全不熟悉，找胡希调整分工。

**Q：Gradio 是什么？难学吗？**
> 几行代码就能出界面。胡希有参考代码，照着搭就行。

**Q：Step API 额度够吗？**
> 暑期开发阶段够用。具体用量胡希有统计。

**Q：我负责的模块看不懂接口文档怎么办？**
> 找胡希，单独过一遍。接口文档不是让你一次全看懂，先有一个"知道要输出什么、输入什么"的概念。

**Q：AI 生成的代码能用吗？**
> 可以用，但必须读懂再提交。答辩时如果被问到细节答不上来，算你自己的问题。

**Q：Git 是什么？我没用过。**
> Git 就是"代码的云盘"。胡希会初始化好仓库，clone 下来直接用，不会的单独教。

---

## 部署

### 生产环境一键启动

```bash
# 1. 克隆 + 安装
git clone https://github.com/cooooooosdas/Filemate.git && cd FileMate
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填入真实 LLM key

# 2. 命令行模式（无界面）
python main.py --watch-dir C:\Users\胡希\Downloads\CourseFiles

# 3. Gradio 界面模式
python -m filemate.ui.app
```

### 打包为可执行文件（可选）

```bash
pip install pyinstaller
pyinstaller --onefile main.py
```

### Docker（计划中，W5 前完成）

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "filemate.ui.app"]
```

---

## 项目文档索引

> 桌面 `FileMate_*.md` 系列为项目总纲级文档，clone 仓库后可从项目主页链接过去。

| 文档 | 位置 | 内容 |
|---|---|---|
| 项目总纲 | `FileMate_项目总纲_v1.0_2026.07.14.md` | 项目概述、技术决策、里程碑、分工 |
| 开会前速查手册 | `FileMate_开会前速查手册_2026.07.14.md` | 名词大白话 + 发言稿 + 常见追问 |
| 技术决策定稿 | `FileMate_技术决策定稿_v1.0_2026.07.14.md` | 6 项技术决策 + 理由 + 影响范围 |
| 核心框架架构 | `FileMate_核心框架架构_v1.0_2026.07.14.md` | 目录结构 + LLM 封装设计 + Pipeline + SQLite Schema + 接口契约 |
| 暑假任务里程碑 | `FileMate_暑假任务里程碑_v1.0_2026.07.14.md` | 8 周逐周计划 + 交付物 + 依赖图 + 风险矩阵 |
| Prompt 库 | `filemate/docs/PROMPT_LIB.md` | Prompt 模板 + 迭代记录（W6 前整理） |
| API 规范 | `filemate/docs/API_SPEC.md` | 5 个接口契约（W4 后冻结） |
