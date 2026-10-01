# V2.4 面试增强阶段交付

日期：2026-10-01。范围仅为五大升级的第四模块，沿用现役面试、题库、资料引用和学习资产。V2.4 是模块阶段号；应用版本仍为 `v1.3.0-alpha.1`，不是已完成真实试用的稳定版。

## 1. 当前状态

独立分支 `codex/v2-4-interview-review` 从已合并 V2.3 的 `main` 提取面试模块，本地检查通过。GitHub PR/CI/合并状态以本文件末尾的交接凭证为准；本地验收不代表生产网站已部署或下载的 EXE 已更新。

未将原工作目录里的 V2.5 草稿、竞赛文书及无关改动带入本次提交。复核现场保留在 `_working/release-v24/`，没有删除旧分支、worktree、数据库或用户文件。

## 2. 新增能力与保留功能

- 原文字回答、语音识别、问题朗读、摄像头预览、本地录制回放、逐题训练、题库及资料/错题/目标引用继续保留。默认本地出题和记录，逐题内容分析需单独确认外发。
- 可选本地 CPU 视觉 Worker 约每 500ms 处理一帧，采集人脸存在、亮度、头部/嘴角/眼部方向系数变化。忙时丢帧，保留有限计数与时间事件；不保存像素、关键点、系数，不识别人或推断紧张、自信、人格、录用结论。
- 时间轴整合视觉动作与语音回调证据。只有共同录像起点且本题内存录像仍存在时可点击定位；不把独立语音/视觉时间基准假装成录像位置。
- 六项内容复盘覆盖回答完整度、逻辑结构、专业知识覆盖、技术表达、问题相关性、STAR 结构，附四维原句及关键词。引用必须是原回答子串；本地表达线索不等于专业知识正确。
- 复盘保存为现役 `interview_report` Artifact，支持 PDF、JSON、Markdown 真正下载。PDF 嵌入 Noto Sans SC 开放许可字体，中文换行、分页和页脚经过渲染检查。
- 支持取消分析、确认清空分析、整场删除预览/确认、原页面录像下载/删除/替换。录像每段最多 30 分钟/100MB，刷新、离开页面后不恢复；不会自动重启摄像头。

## 3. 数据、接口和隐私合同

从 SQLite v22 追加迁移至 v23，未改写已发布迁移。回答新增 `visual_metrics`、`content_analysis`、`answer_key`、`answer_digest`；`interview_review_state` 保存报告引用和修订号，`interview_review_events` 保存有限操作事件。

同一回答键的重试不重复推进题号；冲突键和过期题号返回 409。报告输入变化后旧报告失效，重新生成复用同一 Artifact。取消、清空、删除、新回答使迟到分析不能覆盖当前数据。清空保留回答及语音节奏；删除只影响已预览的本场及其关联私有 Agent 记录，不删除原资料或其他练习。

读取时重新校验观察和原句。无效内容证据不计入单场、成长均分或维度统计；仅跳过损坏分析，其他有效观察及原回答保留，不改写原库字节。报告只读保护沿用学习资产 API。

新增状态、报告读取/生成、逐题分析、取消/清空、删除预览/确认、三格式导出等接口，完整合同见 [API_SPEC 4.12](../filemate/docs/API_SPEC.md)。现役匿名设备分库继续保护面试、报告、清空和删除，不因知道其他设备的 ID 获得访问权。

音视频只在浏览器当前页内存；主动下载由用户决定，业务服务不接收视频或帧。外部内容分析只发送这一题的问题、回答、目标方向，供应商保存策略需另行核对。浏览器语音识别可能使用厂商在线服务，页面明确提示；本阶段未调用真实外部模型。

取消能阻止迟到结果落库，但不能保证已经发送的远端请求停止处理。语速和停顿来自识别回调/转写，不是音频静音检测或医学卡顿诊断。

## 4. 开关和运行依赖

| 配置 | 行为 |
|---|---|
| `FILEMATE_ENABLE_INTERVIEW_REVIEW=0` | 八个增强路由及观察摘要提交返回 503；状态接口仍返回关闭；原面试和题库可用 |
| `VITE_ENABLE_INTERVIEW_REVIEW=false` | 隐藏增强视觉和报告，保留原训练页面 |
| `FILEMATE_INTERVIEW_LOCAL_ONLY=1` | 独立阻止外部模型分析 |

关闭开关不删除已存数据，恢复后可以读取。视觉依赖浏览器安全上下文、Worker、OffscreenCanvas、WASM，模型/运行时同源按需加载，失败保留文字和录像训练。

`@mediapipe/tasks-vision` 固定为 1.0.1；模型约 3.8MB，三种 WASM 兼容资产合计约 35.4MB，每次只加载匹配的一种。字体约 10.6MB，PDF 按实际使用字符子集嵌入。来源与许可见 [视觉资产](../filemate/web/public/interview-vision/README.md)、[PDF 字体](../filemate/interview_review/assets/README.md) 及同目录 OFL。

Python 主依赖和桌面精简依赖均包含 ReportLab；wheel 已检查包含字体及 OFL，sidecar 配置收集字体和 ReportLab 数据。精简依赖的隔离环境已验证 PDF 导入，**未构建/安装本轮 EXE**。

## 5. 改动入口

| 文件 | 用户影响 |
|---|---|
| `filemate/interview_review/` | 有限观察合同、证据验证、持久复盘、隐私操作及三格式导出 |
| `filemate/execution/storage.py` | v23、幂等回答、有效评分读取和成长统计 |
| `filemate/understanding/interview.py`、`server.py` | 增强原评分流程及 HTTP 合同 |
| `filemate/web/src/views/Interview.vue`、`components/InterviewReviewPanel.vue` | 授权、录像生命周期、证据复盘、时间轴及确认操作 |
| `filemate/web/src/interview/`、`types/interviewReview.ts`、`services/api.ts` | 本机采样、Worker、共享类型和统一调用 |
| `filemate/web/vite.config.ts`、`public/interview-vision/` | 开发/生产同源模型资产 |
| `pyproject.toml`、`requirements-desktop.txt`、`scripts/build_sidecar.ps1`、锁文件 | PDF 及视觉运行依赖、字体打包 |
| `evaluation/calibrate_interview.py`、匿名模板 | 专家配对校准工具，不内置分数 |
| 专项测试、浏览器验收脚本、CI、`scripts/verify.ps1` | 可重复执行的工程验收 |
| `README.md`、API 文档、`AGENTS.md` | 能力索引、现役合同和迁移事实源 |

## 6. 验收结果

以下均为合成工程回归，不是真实学生试用或模型效果实验。公开 NASA/scikit-image 图片构成 canvas 流，实际运行 MediaPipe CPU 推理和 MediaRecorder；语音识别回调及设备/网络/模型故障明确注入。不使用用户真实摄像头或私人资料。

本机证据目录以下均相对于独立验收 worktree `_working/release-v24/`，不提交临时数据库、截图、录像或日志。

| 检查 | 结果 | 证据 |
|---|---|---|
| 完整门禁 `scripts/verify.ps1 -IsolateFrontend` | Ruff 通过；582 passed、18 skipped、5 deselected；前端 15/15；类型检查、生产构建通过 | `_working/acceptance/verify-release.log` |
| 面试+旧流程+存储专项复查 | 107 passed（包括面试增强 24 项） | `_working/acceptance/interview-after-fixes.log` |
| 增强开启浏览器 | 14/14，页面脚本错误 0；录像、三格式导出、丢响应重试、五题训练、清空/删除和刷新恢复 | `_working/acceptance/ui-verified/summary.json` |
| 增强关闭浏览器 | 14/14，页面脚本错误 0；增强接口关闭、原训练及其他接口可用 | `_working/acceptance/disabled-verified/summary.json` |
| 最终生产包视觉 | 4/4，页面脚本错误 0；同源 Worker/模型/WASM、实际人脸采样和保存 | `_working/acceptance/production-verified/production-summary.json` |
| 最终生产包画面转换回退 | 4/4，页面脚本错误 0；一次 ImageBitmap 分配失败后继续本机观察 | `_working/acceptance/production-fallback-verified/production-summary.json` |
| 异常引用 HTTP 诊断 | 单场/成长/报告分数 null、已评估计数 0、维度空；有效视觉样本 20，原回答保留 | `_working/acceptance/corrupt-evidence.log` |
| PDF 渲染 | 两页中文、换行、页脚及标题与后文分页通过人工核对 | `_working/acceptance/report-final-1.png`、`report-final-2.png` |
| 响应式及 CLI 操作 | 375/768/1024/1440 无横向溢出；CLI 创建、提交、生成报告，375px 文档宽度实测 375px | `_working/acceptance/ui-verified/`、`_working/acceptance/.playwright-cli/` |
| 打包依赖 | wheel 包含字体 10,595,876 bytes 与 OFL；精简桌面依赖可导入 ReportLab 4.5.1 | `_working/acceptance/wheels/`、`desktop-deps.log` |

18 项跳过来自既有夹具、可选 OCR、符号链接条件缺失；5 项真实模型 e2e 按门禁排除。保留已有依赖弃用、Vite 大块和 setuptools 许可配置警告，不将其写成已解决。

本次检查修复：旧迁移列表期望遗漏 v23、桌面精简依赖遗漏 ReportLab、无效引用仍参与均分/维度统计、视觉加载取消的待决 Promise、重置后的识别迟到回调及旧语音指标残留、PDF 页底孤立标题。初次失败日志保留，修正后的完整门禁和页面流程重跑通过。

验收说明见 [scripts/acceptance/README](../scripts/acceptance/README.md)。本轮独立端口为后端 8024/8025、前端 5194/5195、生产预览 5196，不重启用户原有服务。

## 7. 专家校准与已知限制

`evaluation/datasets/interview_expert_scores.template.csv` 只有表头，不内置导师分数或真实身份。字段为 `case_id,dimension,model_score,expert_score,scoring_mode,sample_kind`，真实专家 `expert_real` 与合成 `synthetic` 分组统计；维度限定内容、结构、表达、岗位匹配。

每维度至少 5 组才计算含并列秩处理的 Spearman；常数序列或不足样本返回 null。空模板实测真实/合成配对均为 0，产品保持“待校准”；相关性不等于准确率，脚本不能验证专家身份或样本真实性。

待外部验证：真实学生及专家试用、不同设备/光照/人群覆盖、真实模型输出质量和延迟、浏览器兼容性。随附字体未覆盖的特殊字符仍需字体扩展。本阶段不报告真实心理状态、专家准确率或学生效果。

## 8. 知识与发布交接凭证

| 事实面 | 状态 |
|---|---|
| 代码 | changed-and-verified：独立 v23 快照及现役调用方本地通过 |
| 运行态 | 本地 changed-and-verified；生产网站、EXE pending |
| 文档 | changed-and-verified：README、API、阶段报告与依赖一致 |
| 规则 | changed-and-verified：将过期的固定 v8 描述改为迁移事实源；不扩张任务卡 |
| 记忆 | out-of-scope：未读写宿主生成记忆 |
| 工作区 | 原目录及后续草稿保留；独立复核现场保留，不执行清场 |

GitHub：待本阶段 PR/CI 验证完成后补入确切结果。下一模块为 V2.5 企业求职训练中心；网站部署、安装包构建/安装与真实用户/专家实验仍属于后续交付，不因本阶段通过而宣布总体目标完成。
