# FileMate 项目规则

## 项目定位

FileMate 是面向大学生的本地优先 AI 学习工作台，现役主链为 Vue 3 + FastAPI + SQLite v8 + Python，Tauri 2 作为桌面壳。

## 开始前

1. 阅读 `README.md` 和任务相关源码、测试。
2. 公共合同阅读 `filemate/docs/API_SPEC.md`。
3. UI 任务阅读 `design-system/filemate/MASTER.md`。
4. 以当前代码、migration、路由和测试为事实源；`docs/ARCHITECTURE.md` 是 2.0 目标设计，不是现役实现。
5. 分阶段开发任务按 `docs/AGENT_DEVELOPMENT_EXECUTION_PLAN.md` 执行，不跨任务卡扩张范围。

## 常用命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
uv run pytest filemate/tests -q -m "not e2e"
```

## 目录与技术约定

- Python：`filemate/`、`server.py`、`main.py`；PEP 8、类型提示、`pathlib.Path`、UTF-8。
- Vue：`filemate/web/src/`；API 统一放 `services/api.ts`，共享类型放 `types/`。
- SQLite：只通过版本迁移升级，不修改已发布的 v1–v8 迁移。
- 评测：`evaluation/`；必须区分合成回归、演示数据和真实用户实验。
- 临时证据放 `_working/`，不得提交 `.env`、密钥、数据库或真实用户资料。

## 不变量

- 文件操作先预览确认；禁止静默覆盖；失败可回滚；重复确认/撤销必须幂等。
- AI 结果应持久化为 Source/Artifact/Context 或学习证据，不能只存在前端内存。
- 外部模型、Embedding、语音和数字人走适配层；密钥只从环境变量读取。
- 无数据时显示待评测，不生成虚假准确率、趋势、画像或用户研究结果。
- 修改 API、schema、路由或环境变量时，同步调用方、测试、README/API 文档。
- 前端采用浅色自然绿；不使用暗色主界面、紫粉 AI 渐变、Emoji 功能图标。

## Git 与交付

- Conventional Commit：`type(scope): 中文简述`。
- 保留用户已有改动，不删除或覆盖无关文件。
- 完成前运行与风险相称的测试；默认执行 `scripts/verify.ps1`。
- 最终说明用户影响、改动文件、测试结果、已知限制和后续依赖。

## 当前目标

- 2026-08-31：可稳定本地运行的 `v1.3.0-alpha` 初步版本。
- 2026-09-30：真实试用、质量加固、接口与文档冻结后的 `v1.3.0` 最终版本。
- 安装包暂不阻塞初步版本；数字人、Neo4j、向量数据库属于条件满足后的扩展项。
