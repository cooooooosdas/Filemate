# FileMate Frontend Clarity Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. 本轮按用户此前自主组合的授权直接实施；低风险样式和静态文案不添加镜像实现的测试，使用现有功能测试与真实浏览器验收。

**Goal:** 减少首页选择步骤和重复入口，让现役页面说明更自然、明确。

**Architecture:** 沿用Vue3现有路由、设计令牌和SVG图标。首页直接任务链接替代方向选择器；其他页面只编辑经过语义核对的静态说明，不动授权和数据逻辑。

**Tech Stack:** Vue3、TypeScript、Tabler、现有CSS。

**Spec:** `docs/superpowers/specs/2026-10-16-frontend-clarity-design.md`

## Global Constraints

钴蓝/冰蓝、系统字体、无新增依赖；保持功能开关和路由；触达至少44px、正文17px；保护用户资料、原文引用、模型授权和历史产物。

## Review Focus

- 关闭编程、图谱、语音等开关后首页不出现对应链接（现有导航测试加源码核对）。
- 375px长中文任务名/文件名不横向溢出（真实浏览器DOM尺寸与截图）。
- 空归档记录不被描述为没有学习资料（浏览器空态）。
- 模型错误仍显示明确失败且旧内容保留（已有可靠性50项与本地浏览器证据）。
- 键盘、减少动画和手机导航不被新样式覆盖（现有测试、CSS检查与浏览器）。

### Task 1: 首页与公共导航

**Files:** `filemate/web/src/views/Home.vue`、`filemate/web/src/App.vue`。

- [x] 将选择方向再进入的面板改为三个直接任务行，保留功能开关、相关功能和真实数据。
- [x] 精简公共导航说明与次要动作；保留主导入入口、手机可访问性。
- [x] 首页两栏、窄屏单栏；统一字号/触达、短时反馈和减少动画规则。
- [x] `npm test`、`npm run build`、`npm run check:bundle`通过；浏览器验证四种宽度和三个任务入口。

### Task 2: Humanizer静态说明与交付

**Files:** 学习工作区、导入、知识库、求职、简历、技能、学期、账号中需要澄清的文案；设计MASTER与交付记录。

- [x] 只改具体存在的问题；不改生效状态、AI使用条件、删除确认和数据依据。
- [x] 核对每条修改前后信息，更新设计规则和本地结果。
- [x] 再运行前端门禁及默认 `scripts/verify.ps1 -IsolateFrontend`；独立审阅差异并处理重要问题；保存本地可审阅版本与截图。

实际结果与边界见[交付记录](../../FRONTEND_CLARITY_DELIVERY_2026-10-16.md)：1163后端/55前端、类型/构建/体积通过；四档宽度按实际CSS尺寸记录；最终浏览器还验证了合成模型失败、旧内容保留、重试及刷新后持久化。一次较早的注销409未重现，原因未知；中间磁盘故障和最终成功复跑均如实保留。
