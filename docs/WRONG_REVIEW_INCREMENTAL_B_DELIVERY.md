# 错题复盘 2.0 增量 B 级交付｜2026-10-30

## 结论

**CONDITIONAL PASS（本地工程候选，尚待用户验收）**。可信推荐、本次时长预览和开始前只读核验已实现；原有到期排序、作答、调度与复习记录继续复用。常规合成库通过原 500ms 门槛，但高差异到期时间的万题四并发仍有 P2，不能宣称全部容量验收通过。

一次独立只读审阅完成，未建立可复现的新增 Critical、Important 或 Minor 缺陷。审阅未重复执行运行测试，采用本轮新门禁证据；完整边界见[审阅记录](audits/wrong-review-incremental-b-2026-10-30/review.md)。

本轮仅对应用户已通过的增量 A 后续 B，不代表原需求全部完成。C 级可见控件／界面优化未挂载；没有推送、部署、生产迁移或新发布压缩包。历史 A/E 冻结证据没有重写。

## 范围与用户影响

| 项目 | 本轮行为 | 证据 |
|---|---|---|
| 默认队列 | 继续按到期时间；四种既有排序保留 | workspace_reads 回归及全项目校验 |
| 推荐排序 | 可选 recommended；只纳入筛选后有效、可复习、已到期记录，全范围排序后分页 | insights 测试；原页以外最高分与同分稳定用例 |
| 推荐说明 | 上海自然日逾期、保存的历史错答次数、本人标注错因；每项带规则版本 | 纯函数／SQL 排名一致性与跨午夜测试 |
| 本次预览 | 按可用时长及每题估时挑题，最多 20 题；零分钟返回空选择；不创建计划 | session_preview 边界、全范围计数及重复只读测试 |
| 开始前核验 | 在同一读取快照核对题目摘要、资料、题号、修订和排期；变化统一 409 | 暂停、删除、替换题目、变更排期／修订、跨账号用例 |
| 作答及历史 | 原作答、首次订正、延迟复习、再次错答均持久化；请求键重放不重复写入 | 同一注册账号 4 条作答／5 条事件／1 个题目摘要 |
| 开关／故障 | 关闭 V2 时新端点 503、既有历史可读；坏参数 422、超大请求 413；数据库故障安全降级 | API 合同与故障测试 |
| 前端合同 | 类型与共享客户端函数就绪，不绕过统一认证，不引入密钥头 | 新增 3 项 Node 合同测试、类型检查与构建 |
| 证据工具 | source_hashes 移除对 Python 3.12 Path.walk 的硬依赖 | 真实 Python 3.11.15 调用、兼容回归、Ruff py310 |

推荐规则 `review2-priority-v1`：`min(逾期天数,30)×3 + min(历史错答次数,10)×4 + 本人标注错因×4`。按分数降序、到期时间升序、ID 升序；该推荐顺序不受旧 direction 字段翻转。它是队列启发式规则，不是掌握率、模型能力评分或学习效果结论；旧导入记录的 error_count 不保证都来自客观判题。

新端点：`GET /wrongbook/v2/session-preview`、`POST /wrongbook/v2/session-check`，受既有 V2 开关与账号空间约束。核验只返回当前可用快照，不锁题、不预留配额、不授权后续写入。真实作答仍由原 attempts 端点验证。预算估计不承诺用户实际完成时间；暂停、历史只读、旧已掌握、坏日期、坏元数据、无有效引用等不入选。

## 验证结果

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`：**退出 0**，Ruff 通过；后端 **1790 passed / 22 skipped / 5 deselected / 3 warnings**，539.79 秒；前端 **281 passed / 0 failed / 0 skipped**；vue-tsc、Vite 构建和包体门禁通过。
- 分步证据：兼容测试 1 项；推荐及既有读取回归 73 项；Task 3 全 wrongbook 238 项；新增账号链路 1 项。最终全项目校验已经包含新增账号链路，不把分步计数与全量计数相加。
- 当前环境为 Windows、Python **3.12.13**、SQLite **3.53.1**。Python 3.11.15 只实测源码摘要工具，未宣称全应用兼容验收；无 Python 3.10 运行验收。无 JSON1 分支做了强制能力关闭的语义回归，不等同于真实 SQLite 3.26 部署或容量测试。
- 22 项跳过：Linux 专属运行／资源限制、Windows 符号链接权限、缺少可选 OCR 依赖／模型，以及缺少 DOCX/PDF/PPT 与大文件样本。5 项由既有 `not e2e` 门禁排除。3 个警告分别为 Starlette/httpx 测试客户端、PyPDF2、逐请求 cookie 的弃用提示；Vite 仍有既有大分包警告，包体门禁通过。完整逐项记录见 full-gate.log。
- 合成账号使用真实 ASGI 路由、认证和 SQLite；原题通过测试夹具直接建立，服务时钟受控，**未覆盖上传解析、浏览器手工点击、真实学生试用或模型质量**。测试禁用模型调用。另一账号列表为空、详情 404、预览核验 409；重新登录能读回自身历史。

## 性能与仍保留的 P2

同一台 Windows 主机，独立新进程／全新四规模合成资料库，通过登录后的真实 loopback HTTP 请求测量；各场景 20 次暖请求及 5 轮×4 并发，原门槛均为 P95≤500ms。未清空操作系统缓存，首次请求另列原始 JSON；不是公网响应或生产 Linux 负载结果。

| 错题数量 | 默认列表四并发 P95 ms | 默认搜索四并发 P95 ms | 推荐四并发 P95 ms | 本次预览四并发 P95 ms |
|---:|---:|---:|---:|---:|
| 0 | 48.47 | 52.98 | 64.27 | 54.67 |
| 100 | 55.08 | 44.03 | 78.47 | 65.80 |
| 1000 | 65.46 | 65.58 | 62.58 | 74.16 |
| 10000 | 185.98 | 197.44 | 314.38 | 365.83 |

万题推荐搜索四并发 P95 **351.11ms**。17 个常规 HTTP 场景的暖请求与四并发均通过。优化前的新基线默认列表／搜索也已低于 500ms，故不能将本轮全部速度变化归因于代码修复。

额外复制自有合成数据库，将大部分题的到期时间改为不同的有效微秒时间，共 **9992 个不同到期时间**。直接存储服务四并发 20 次 P95 **1624.01ms**，超过 500ms；单请求暖耗时 147.98–175.15ms。此探测不是 HTTP 测试，但足以保留容量问题，不允许用常规夹具达标掩盖它。

**P2-INC-B-01 继续开放**：大量不同到期时间下，逐时间 Python 回调和并发竞争仍有成本。本轮 JSON1 与快照内按时间分组优化仅改善部分分布，不改变严格日期解析、隔离规则或原门槛；后续需在独立子卡评估可索引的规范化时间／读取模型，并实测旧 SQLite 与生产 Linux。无 JSON1 的大规模性能亦未验收。不能据此宣告旧 E 的万题容量 P2 已关闭。

## 数据、安全与恢复边界

本轮无迁移、无新持久表，不改已发布迁移。预览／核验不写任务、作答或事件，不调用 AI；最大 20 条引用、64KiB 请求体、参数白名单、严格类型及统一安全错误。实际作答继续使用既有幂等键、快照与调度事务。

新增能力可由既有 V2 开关关闭，关闭不抹除历史。未重复执行整库备份恢复或生产迁移；旧 E 的恢复结论只在原版本语境成立，本轮不以旧验收代替新发布验收。历史数据在本轮回归中可读取，不能由此推导所有外部旧库均已验证。

保留的 24 个用户既有测试改动逐字节摘要一致，未纳入本轮提交；不接触用户真实学习库。最终源码摘要对应本地工作树（含这些保留改动），不冒称纯 HEAD 或生产构建。归档只含代码摘要、测试／性能日志和合成汇总，不含密钥、账户凭据、数据库或真实用户文件。归档文本仅统一为 LF 换行；清单同时记录转换前后摘要，原始工作日志保留在 _working。

## 后续顺序

1. 用户验收本 B 工程候选，并保留容量限制。
2. C 级接入推荐选择、时长预览、核验冲突恢复与两栏／手机单题引导；不重复创建学习计划。
3. P2 容量专项及真实旧 SQLite／Linux 验证，随后才评估发布。真人学习效果仍须另行采集，不能由合成回归代替。

## 证据与实现索引

- [验证清单](audits/wrong-review-incremental-b-2026-10-30/verification.json)、[执行裁定](audits/wrong-review-incremental-b-2026-10-30/execution-ledger.md)、[完整门禁](audits/wrong-review-incremental-b-2026-10-30/full-gate.log)。源码摘要共 649 项，证据摘要与已有改动保留核验见清单。
- [常规 HTTP](audits/wrong-review-incremental-b-2026-10-30/after-performance.json)、[新增端点 HTTP](audits/wrong-review-incremental-b-2026-10-30/after-new-performance.json)、[高差异到期时间未达标结果](audits/wrong-review-incremental-b-2026-10-30/unique-time-capacity.json)、[持久化流程汇总](audits/wrong-review-incremental-b-2026-10-30/flow-proof.json)。
- 归档保留首次慢实现、仅 JSON 优化、分组优化的直接服务采样，不用失败中间结果充当最终 HTTP 结果。基线以 baseline-http-performance.json 为准；最初测量脚本误用 /health 导致启动检查失败，修正为 /api/health 后完成新基线，不属于产品故障。
- 实现：filemate/wrongbook/insights.py、queries.py、session_preview.py、api.py；前端 types/wrongbook.ts、services/review-api.ts；新测试 test_acceptance_compat.py、test_insights.py、test_session_preview.py、test_incremental_b_flow.py 和 wrongbook-session-api.test.mjs。
- [实施计划](superpowers/plans/2026-10-30-wrong-review-incremental-b.md)、[API 合同](../filemate/docs/API_SPEC.md)。测量脚本以 .py.txt 保存以便复核，默认只操作本项目 _working 下的全新合成资料库。
