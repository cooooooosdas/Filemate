# 错题复盘2.0 E级验收与交付计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成原任务书8.1—8.5工程验收，形成逐项证据、可恢复交付与明确发布边界。
**Architecture:** 复用现役Vue/FastAPI/SQLite、C/D验收脚本及原创合成账户，禁止修改生产资料；旧引擎通过SQLite官方3.26可执行程序验证实际迁移SQL、数据读取与快照恢复，不将Windows结果冒称生产Linux验证。
**Tech Stack:** Python、PowerShell、Edge/Playwright、官方SQLite3.26 shell、既有备份CLI。
**Spec:** 原错题复盘任务书第八节及2026-10-25-wrongbook-2-design.md；最新用户要求“完整执行，不再确认”覆盖旧的逐级暂停。发布另授权。

## Task 1: 关闭引用去重遗留并核实旧引擎

Files: analysis_models.py、对应领域测试、scripts/acceptance/wrongbook_release_runtime.py、E审计目录。
- [ ] 同候选重复原答引用补RED，严格结构校验拒绝重复；定向回归GREEN。
- [ ] 全新合成v34库保留实际错题与作答，官方SQLite3.26执行现役35/36迁移，核对NULL判题、FK/integrity及旧记录；注入失败证明事务回滚。
- [ ] .backup／.restore到新路径并由当前仓储读取，原库内容不覆盖；记录引擎source_id、官方包SHA及范围。
- [ ] 本地提交，记录输出路径及失败／未执行边界。

## Task 2: 全流程、规模、重启与恢复

Files: 复用wrongbook_workspace.mjs、wrongbook_learning.mjs及fixture；新增完整场景脚本／报告，必要的同范围缺陷修复。
- [ ] 全新四合成账户0/100/1000/10000错题，实际HTTP查询与搜索，每次30项以内，记录冷热及并发分布，不更改既定500ms p95目标。
- [ ] 当前源码复跑C工作台21组及D学习11组，覆盖真实UI、来源、排期、今日、图谱、错误、窄屏和身份隔离。
- [ ] 场景1—9明确逐项核对：新错题、原答解析、诊断重答、正确排期、再次错答历史、今日同口径、精确图谱、AI失败基础练习、刷新重登及服务重启持久化；场景10由Task1旧库真实迁移支撑。
- [ ] 新目录执行全包备份CLI预览／创建／验证／恢复及重启实际HTTP读取，复用既有规则；按需补错题专属数据校验。不得把只有来源的备份探针冒称含错题结果。

## Task 3: 总门禁与交付

Files: E_DELIVERY.md、E审计结果、README/API/索引、执行账本。
- [ ] 当前最终源码运行scripts/verify.ps1 -IsolateFrontend，核对所有跳过理由；两前端开关构建及原预算。
- [ ] 一次新上下文独立审阅E增量，Important一轮TDD修复，无重复复审；不重新派审D范围。
- [ ] 原任务书8.5十二项逐项对照：文件、结构、迁移、API、页面、规则、自动测试、手工浏览器、能力遗留、风险、启动验证、后续建议。记录每条证据及无法替代的真实模型／真人／生产Linux依赖。
- [ ] 生成可回溯源码交付zip（仅Git已跟踪内容，排除密钥、数据库、用户资料）、SHA及验证方法；本地提交归档。发布不纳入本目标，不要求再次确认后才做工程收尾。
