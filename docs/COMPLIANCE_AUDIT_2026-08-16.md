# FileMate 文档与实现一致性审计

> 审计日期：2026-08-16
> 基线：`main` = `049d7d6`，审计分支 `codex/product-evaluation-2026-08-16`
> 目的：对照 README、API 规范、FastAPI 路由、SQLite migration 和 Vue 路由，找出需要修正的文档缺口。

## 结论

当前主链整体一致：README 描述的技术栈、目录结构、SQLite v8、`314 passed` 测试基线与实际代码基本吻合。主要缺口集中在 `API_SPEC.md` 和旧的 `DEVELOPMENT.md`。

## 发现清单

### 1. `filemate/docs/API_SPEC.md` 缺少大量现役 HTTP 路由

以下路由在 `server.py` 中存在，但 `API_SPEC.md` 的 HTTP API 章节未收录：

- `POST /process`
- `GET /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/ics`
- `GET /knowledge/artifacts/{artifact_id}`
- `PATCH /knowledge/artifacts/{artifact_id}`
- `GET /knowledge/search`
- `POST /quiz/attempts`
- `GET /wrongbook`
- `GET /review/today`
- `GET /study-plans`、`GET /study-plans/{plan_id}`、`PATCH /study-plans/{plan_id}/days/{day_index}`
- `POST /interviews`、`GET /interviews/{interview_id}`、`POST /interviews/{interview_id}/answers`
- `GET /analytics/overview`
- `POST /evaluation/feedback`、`GET /evaluation/feedback/summary`、`GET /evaluation/feedback/export.csv`
- `GET /api/health`

### 2. `API_SPEC.md` 命名模块阈值与代码不一致

- 文档写的是：`task` 长度 > 20 字时精简。
- 代码 `filemate/understanding/namer.py` 实际是 > 15 字时精简，失败截断到 15 字。

### 3. `filemate/docs/DEVELOPMENT.md` 仍是旧 Gradio 主链

- 仍指导运行 `python -m filemate.ui.app`。
- 仍把“四个 Tab 的 Gradio 界面”作为 UI 目标。
- 当前现役主链是 FastAPI + Vue 3，Gradio 只作为兼容入口。

### 4. 已核对且一致的内容

- README 声称 SQLite v8，实际 `_MIGRATIONS` 为 v1–v8。
- README 声称非 e2e 测试 `314 passed`，本轮实际执行一致。
- README 声称 13 个 Vue 路由，`filemate/web/src/router/index.ts` 实际 13 个。
- README 声称单文件最大 25 MB，`server.py` 的 `MAX_UPLOAD_BYTES` 一致。
- API_SPEC 中分类置信度 0.65–0.92 与 `classifier.py` 的公式一致。

## 本轮修正

1. `API_SPEC.md` 已新增 4.8 节，按 `server.py` 现役路由补齐文件处理、知识库与学习闭环 API。
2. `API_SPEC.md` 命名模块阈值已从“20 字”改为“15 字”。
3. `DEVELOPMENT.md` 的 UI 章节已改写为 FastAPI + Vue 3 版本，第一周目标也已更新；顶部仍保留历史提示说明 Gradio 仅兼容入口。
