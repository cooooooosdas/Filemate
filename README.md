# FileMate

基于多模态语义理解的课程文件归档与任务提醒助手。

## 快速开始

```bash
cp .env.example .env   # 填入 LLM_API_KEY
pip install -r requirements.txt
python main.py <file_path>
```

## 文档

- `FileMate_项目总纲_v1.0_2026.07.14.md` — 项目总纲（桌面）
- `FileMate_技术决策定稿_v1.0_2026.07.14.md` — 技术决策
- `FileMate_核心框架架构_v1.0_2026.07.14.md` — 架构设计
- `FileMate_暑假任务里程碑_v1.0_2026.07.14.md` — 里程碑计划

## 目录

```
filemate/
├── llm_client/      # LLM 统一封装（胡希）
├── perception/      # 感知层（汤新阳）
├── understanding/   # 理解层（张金宝）
├── core/            # Pipeline + Session（胡希）
├── execution/       # 执行层（徐书和）
├── ui/              # Gradio 界面（余恒）
├── tests/           # 测试用例
└── docs/            # Prompt 库 + API 规范
```
