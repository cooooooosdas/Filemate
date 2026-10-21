# 面试 2.0 第六阶段：六维标准与可重算报告

> Implementation: executing-plans，当前会话连续实施，最终一次独立审阅。

**Spec:** `docs/superpowers/specs/2026-10-19-interview-2-design.md`。用户已验收第五阶段并授权本阶段；不包含第七阶段、部署或专家校准。

## Global constraints

- 只追加 schema 30；旧四维报告和回答版本不改写、不转换为六维。
- 每次重算生成独立评估及 Artifact，保留标准快照、模型及规则版本、原句证据。
- 缺证据不评分，核心维度缺失则总分为空；可选维度缺失按已评估权重归一并明示。
- 不从文字推断口头清晰度、心理状态；不把旧 ASR 回调或摄像头摘要用于新能力评分。
- 显式外发授权、来源权限、会话互斥、有界重试与预算、过期发布保护；失败保留旧成果。
- 新数据纳入备份、恢复、清空、删除和关闭开关；恢复不重放 AI。
- 保留 24 个既有测试改动。使用现有隔离工作区，分阶段本地提交。

## Task 1 — 版本化标准与证据校验

Produces: rubric(category/track)、snapshot、parse_result、compare_reports。
1. 先测试各场景六维/权重/锚点、伪造引用/非有限分数/重复维度拒绝、证据缺失、核心缺失总分为空、可选缺失归一、跨版本不可比。
2. 实现纯规则与严格结构校验；有限两次 JSON 修复调用，总预算 60 秒。
3. 运行 `uv run --no-sync pytest filemate/tests/test_interview_assessment.py -q`。Expected: 全绿。
4. Commit `feat(interview): 添加版本化六维标准与原句核验`。

## Task 2 — 持久化、API 与生命周期

Consumes: Task 1；Produces: schema30、assessment context/create/read/export/history/compare。
1. 先测试原子迁移、追加报告、幂等、授权/租户/开关、阻塞模型期间健康接口、晚到结果、清空/全版本删除、备份恢复。
2. 实现评估声明/完成状态机；独立保存结果与最新回答引用，报告为 Artifact；关联回答以 FK 表保存。
3. 已结束实战可显式重算，每场重算另有最多 6 次模型申请（每次最多 2 次调用）；保留全局模型治理，避免绕过运行中会话限制。
4. 运行 Task1+API+privacy 测试。Expected: 全绿；更新 API/README/环境变量。
5. Commit `feat(interview): 持久化可重算报告并接入数据生命周期`。

## Task 3 — 六维报告交互

Consumes: Task2 typed API；Produces: 六维卡、证据、部分雷达、历史比较和导出。
1. 先测缺轴不补零、版本不可比、异步切换/过期结果、默认关闭回退。
2. Vue3 小组件实现六维工作区；旧报告和媒体证据折叠保留，唯一清空/删除入口沿用。
3. 前端 tests、vue-tsc、build、bundle gate。Expected: 全绿。
4. Commit `feat(interview): 展示六维证据报告与可比历史`。

## Task 4 — 总体验证、独立审阅与交付

1. scripts/verify.ps1；合成浏览器验证浅深主题/窄屏/缺证据/生成/历史/导出/故障恢复，标明非真人校准。
2. 按 executing-plans 对 aa96455..HEAD 做一次全分支独立审阅。Critical/Important 合并一次 TDD 修复；Minor 留账；不重复审阅。
3. 再跑必要的总体验证，核对 24 个既有测试哈希。
4. 写 A–E 交付报告及版本边界。Commit `docs(interview): 记录第六阶段验收与发布边界`。

## Review focus

权限与外发边界；重复请求/慢调用/重答/清空/删除的竞态；恢复后旧调用不发布；缺失维度和不兼容历史不伪造分数；部分雷达不补零；HTML/Markdown/PDF 内容安全；旧四维内容兼容；失败后旧报告可读；全局及会话预算；默认关闭仍能读/导出/删除。
