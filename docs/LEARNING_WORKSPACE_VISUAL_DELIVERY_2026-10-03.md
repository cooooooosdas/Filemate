# 学习工作区：大字阅读与任务整合交付

核对日期：2026-10-03。本卡承接[三份样例与六站参考](FRONTEND_VISUAL_UPGRADE_DELIVERY_2026-10-03.md)和[资料一体审核](INTEGRATED_FILE_REVIEW_DELIVERY_2026-10-03.md)，属于独立前端子卡。采用已选的自然绿“知识生长”方向，保留现役 Vue / FastAPI / SQLite v24 与 Source / Artifact / Context；没有新增业务API、数据库迁移或生产开关，没有同步线上版本。

## 用户可见变化

- 标题36–48px、正文18px、任务按钮17–18px。原先拥挤的三栏改为桌面对话/阅读两栏；资料目录通过「资料」展开，手机和平板通过三个可见入口切换。
- 笔记、卡片、练习、摘要用四个直接按钮选取；卡片与练习显示5/10数量上限。没有原先的类型、数量和产物下拉框，仍遵守API的1–10上限合同。
- 已有内容默认阅读。点击「创建学习内容」才展开任务和生成动作，「返回阅读」收起；首次导入且没有产物时直接显示四种任务。截图复核后收起占位较大的生成区，避免正文排在长串配置后面。
- 学习内容用横向书架直接打开，选择更新原 `source` / `ctx` 下的 `artifact` 深链。笔记、原文、解释、选项和反馈放大，卡片有有限翻面过渡；减弱动画时保持静态。
- 讲解和生成共用明确模型授权，重新打开页面需要再次勾选。导入、阅读、打开引用和新建会话不调用模型。资料保存在当前学习空间，本机部署与托管部署不混称“保存在本机”。
- 尚未发送的问题在任务/产物切换时保留；切换资料、会话、导入另一份资料或离开时可取消或明确舍弃。顶部刷新与进行中的请求有保护，取消导入发生在实际写入之前。

生成仍经过原HTTP模型适配层和后端结构校验；成功才保存到原资料，错误保留原结果。练习用现役判题、作答和错题链；导出下载真实保存内容。原文引用、完整对话、覆盖范围提醒和失败重试继续保留。

## 改动文件与合同

| 文件 | 作用 |
|---|---|
| `filemate/web/src/views/LearningWorkspace.vue` | 两栏/目录切换、直接任务、按需创建、书架与深链、模型授权、输入和刷新保护 |
| `filemate/web/src/components/LearningArtifact.vue` | 放大阅读、练习和反馈、可减弱的卡片过渡；原持久化与导出调用保留 |
| `scripts/acceptance/workspace.mjs` | 编译前端、真实TLS/API/SQLite/模型HTTP适配器的23项专项 |
| `scripts/acceptance/workspace_model_fixture.py` | 仅回环运行、一次性合成凭据的HTTP合同夹具；支持有效内容、非法JSON、503和有限延迟 |
| `scripts/acceptance/gateway_preflight.py` | 可选工作区专项、端口检查、自有进程清理与凭据隔离；基础网关先运行，写入专项再接入夹具 |
| `scripts/acceptance/file_review.mjs` | 为归档专项通过实际草稿API填写明确合成课程与截止日期，不依赖模型提取质量 |
| `scripts/verify.ps1` | 新夹具纳入现役Ruff检查 |
| README / API_SPEC / MASTER / 当前索引与执行计划 | 同步实际布局、行为、验收口径和下一子卡 |

生产API、schema、路由与环境变量没有变化。验收新增 `--workspace-checks` 与 `--fixture-port`；`FILEMATE_UI_FIXTURE_BASE`、`FILEMATE_UI_FIXTURE_TOKEN` 仅在自有验收子进程内设置，正式网站不使用它们。验收进程设置 `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`，并实际断言凭据来源是合成环境变量或无凭据，避免访问操作系统中保存的模型凭据；不修改系统凭据库。

## 直接证据与测试

证据根目录 `_working/workspace-redesign-20261003/`，最终编译包 `frontend-final/`，实际TLS结果 `production-final/`。分支 `codex/v2-1-playback-reliability`，HEAD `a523b36f74511df6a6f268e99b88fba80139c2ef`；现有大量未提交改动保留，没有新建远端PR或CI结果。

| 检查 | 结果与范围 |
|---|---|
| 全门禁 `verify.ps1 -IsolateFrontend` | Ruff、740项后端通过；18项跳过、5项排除、3项警告；18项前端、类型、构建和预算通过，见 `verify-final.log` |
| 最后阅读区调整 | 后端源码和依赖未变；最终前端18项、类型/构建/预算重新执行，见 `frontend-tests-final.log`、`build-final.log`、`bundle-final.log` |
| 实际Caddy网关总检查 | 45项通过，91个路径GET状态/类型与实际上游匹配，测试源指纹前后相同；GET比较不代替所有写接口验收 |
| 页面与资源 | 28项网关浏览器检查、4项真实本地视觉Worker/WASM/录像检查通过；视觉输入为公开图片合成流 |
| 首页与一体归档 | 同一最终包的10项视觉和17项真实上传/草稿/归档/撤销/ICS/冲突操作通过 |
| 新学习工作区 | 23项通过：空态、真实导入、共享授权、输入保护、检索引用、四类生成、阅读/创建展开、数量、翻面、实际正误判定及错题、深链/恢复、下载、模型故障和重试、目录/会话、导入取消、四种宽度、减弱动画、缺失资料和零浏览器错误 |
| 首屏预算 | JS363567字节，gzip估算133386字节，CSS100165字节；450/140/150 KiB原门禁未放宽，无重型模块提前加载 |
| 有限读取工作负载 | 8个独立匿名访客128次读取全部成功，本轮p95约1698ms；开发机回环TLS、5秒门禁，不包括模型/上传/编译，不表示线上容量或SLA |

23项工程验收使用原创“栈与队列”TXT和明确合成模型内容，实际经过编译Vue → Caddy → FastAPI → 现役模型HTTP适配器 → SQLite；没有替换业务API响应或在产品中加入假成功。非法JSON/503/延迟为明确夹具注入；归档响应丢失与读取故障也是明确注入。分类夹具的0.5只是合成合同字段，不作为提取准确率。真实学生和导师仍为0，不能据此证明学习收益、一般模型质量或市场领先。

最终manifest SHA256：`696c2139fa7d9cc51b7bb7cf4de46ec16a9fd6ef5dafaded1a09ecbd07b1fa66`。服务端和生产Caddy与上一卡一致，指纹及逐项结果见 `summary-final.json` / `production-final/summary.json`；截图在 `production-final/workspace/`。只停止自有进程，测试端口8034/8036/5202及8038/8040/5206已清理，不重启用户原服务。

## 失败与修复记录

早期候选与日志全部保留：系统凭据优先级使最初合成请求被拒绝；随后启用进程内null凭据后端并验证来源。引用阅读后主入口未返回学习内容是实际UI问题，已修复。测试脚本的首页选择器、草稿请求 `edits` 信封和弹窗关闭等待也修正，没有放宽门禁。

组合复测还揭示现役 `/process` 会初始化模型客户端，无密钥会失败；归档专项现在接入明确本地合成模型，并通过实际草稿API补充合成课程/日期。本卡不宣称无模型的文件分类链已经可用；工作区独立 `/knowledge/import` 的无模型阅读入口已实际验证。生产凭据行为保持现役合同，后续业务加固另卡处理。

`production-8/` 是22项工作区及整组通过的早期阅读布局；截图自评后将创建区收起，最终包另跑 `production-final/` 的23项，不把多轮通过数累加成一个结果。默认全门禁副本为 `verify-web-a290f3875ff3436685ec7e5455fa97e8`，最后前端调整的冻结包为上述 `frontend-final/`，两者的前端快照不混称同一包。

## 复跑与剩余范围

先获得可信官方Caddy、已通过构建的完整前端副本、Node/Playwright/Edge及原视觉夹具，再在未占用端口运行；输出目录必须不存在且候选与输出都在 `_working` 内：

```powershell
uv run python scripts/acceptance/gateway_preflight.py --caddy _working/operations-preflight-20261003/tools/caddy.exe --web-root _working/workspace-redesign-20261003/frontend-final --out _working/<新证据目录> --api-port 8038 --web-port 5206 --fixture-port 8040 --visual-checks --review-checks --workspace-checks
```

本卡不重新执行上一卡所有19组模块关闭/业务流程，不能宣称全项目最新包19组全通过。整体仍需五模块界面整合、指标/准入/配额、Linux隔离运行、正式身份与干净机器桌面、真实采集、候选版本/远端CI/线上同步和冻结。下一独立子卡先处理知识与证据的阅读/操作入口，再按账本串行推进其他模块。

尚未发送的问题和本轮练习标记不跨浏览器重启保存，页面已有提示；模型授权是当前页面意图，后端仍按既有API合同处理。回滚只恢复本卡前端组件和相关说明/验收入口；不反向迁移数据库、不删除学习记录、不回退或覆盖用户其他改动。
