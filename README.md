# FileMate

基于多模态语义理解的课程文件归档与任务提醒助手。

> 国家级大学生创新创业训练计划项目（2026 暑期阶段）
> 负责人：胡希 | 成员：汤新阳、张金宝、徐书和、余恒、杨乐

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/<你的用户名>/FileMate.git
cd FileMate

# 2. 安装依赖
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt

# 3. 配置 LLM
cp .env.example .env
# 填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL

# 4. 处理单个文件
python main.py <file_path>

# 5. 监控目录模式（持续运行）
python main.py --watch-dir C:\Users\胡希\Downloads\CourseFiles
```

## 四层架构

```
感知层 (perception/)   →  理解层 (understanding/)   →   确认层 (ui/)    →   执行层 (execution/)
  文件解析                  分类/抽取/命名              Gradio 确认界面         文件归档/.ics/SQLite
 watchdog 监控             规则引擎 + LLM              人工确认后执行            哈希去重 + 日志
 OCR（可选）                                                       
         ↓                        ↓                       ↓                      ↓
       core/ (PipelineWorker — 胡希)
```

## 模块说明

| 模块 | 路径 | 负责人 | 状态 |
|---|---|---|---|
| LLM 统一封装 | `llm_client/` | 胡希 | ✅ 骨架 + 实现 |
| 感知层 | `perception/` | 汤新阳 | ⬜ TODO |
| 理解层 | `understanding/` | 张金宝 | ⬜ TODO |
| Pipeline + Session | `core/` | 胡希 | ✅ 骨架 + 实现 |
| 执行层 | `execution/` | 徐书和 | ✅ 骨架 + 实现 |
| Gradio 界面 | `ui/` | 余恒 | ⬜ TODO |
| 功能设计协调 | 各模块 | 杨乐 | ⬜ TODO |
| 测试 | `tests/` | 全体 | 🟡 部分 |

## 里程碑

| 里程碑 | 日期 | 验收标准 |
|---|---|---|
| W4 单文件链路 | 2026-08-03 | `python main.py <file>` 跑通完整流程 |
| W7 端到端原型 | 2026-08-24 | Gradio + 批量处理 + 演示视频 |

## 运行测试

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## 关键文档

- `FileMate_项目总纲_v1.0_2026.07.14.md` — 项目总纲
- `FileMate_技术决策定稿_v1.0_2026.07.14.md` — 6 项技术决策
- `FileMate_核心框架架构_v1.0_2026.07.14.md` — 四层架构 + 接口契约
- `FileMate_暑假任务里程碑_v1.0_2026.07.14.md` — 8 周计划
- `filemate/docs/PROMPT_LIB.md` — Prompt 库
- `filemate/docs/API_SPEC.md` — 5 个接口契约
