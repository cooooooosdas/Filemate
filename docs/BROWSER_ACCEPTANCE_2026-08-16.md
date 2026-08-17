# FileMate 浏览器验收记录（2026-08-16）

> 执行方式：Playwright Chromium 自动化 + 浏览器路由冒烟 + 关键 API 步骤
> 服务：FastAPI `http://127.0.0.1:8001`、Vue `http://127.0.0.1:5173`
> 基线 commit：`049d7d6`（验收分支 `codex/product-evaluation-2026-08-16`）

## 1. 13 个前端路由冒烟

全部 13 个路由均返回 200，页面标题正确，无控制台错误。

| 路由 | 结果 |
|---|---|
| `/`、`/today`、`/import`、`/classification`、`/naming`、`/schedule`、`/history` | 通过 |
| `/ai-tools`、`/study-plan`、`/wrongbook`、`/interview`、`/growth`、`/knowledge` | 通过 |

发现并修复：Vite 代理把 `/ai-tools`、`/knowledge`、`/wrongbook` 当 API 转发导致 404/空页，已在 `filemate/web/vite.config.ts` 增加 bypass。

## 2. 核心 API 可用性

以下接口均返回 200：

- `/api/health`
- `/sessions`
- `/knowledge/sources`
- `/wrongbook`
- `/review/today`
- `/study-plans`
- `/analytics/overview`
- `/evaluation/feedback/summary`

## 3. 六条核心流程浏览器验收结果

| 流程 | 状态 | 说明 |
|---|---|---|
| 1. 导入→编辑→确认→撤销 | 通过 | 浏览器上传 TXT 成功；分类 PATCH、确认、撤销接口均通过 |
| 2. 导入→摘要/知识卡/笔记→知识库 | 部分 | 路由和知识库 API 正常；AI 生成依赖 LLM 额度，当前未完成真实生成 |
| 3. 导入→检索→引用/拒答 | 部分 | 检索 API 与页面正常；A2 拒答阈值未合并 |
| 4. 出题→错题→复习 | 部分 | 错题/复习 API 与页面正常；A1 统一题目主链未合并 |
| 5. 学习计划→每日任务→导出 | 部分 | 计划 API 与页面正常；生成依赖 LLM 额度 |
| 6. 模拟面试→五轮→反馈→成长 | 通过 | 浏览器完成 5 轮回答，总分 51，四维反馈和回答记录均显示 |

## 4. 证据文件

- `_working/browser-acceptance.json`：13 路由 + API 冒烟结果
- `_working/browser-flow1.json`、`_working/browser/flow1-import.png`：流程 1 上传
- `_working/browser-flow6.json`、`_working/browser/flow6-interview.png`：流程 6 面试
- `_working/browser/*.png`：13 个路由截图

## 5. 已知限制

- 浏览器环境为 headless Chromium，未验证真实语音输入。
- AI 生成类流程受 StepFun 配额限制，仍依赖 A1/A2 合并和有效 LLM 配置。
- 测试样本仍缺 `.docx/.pdf/.pptx`，部分感知层测试继续跳过。
