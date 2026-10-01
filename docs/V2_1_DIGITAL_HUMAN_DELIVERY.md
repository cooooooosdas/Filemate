# FileMate V2.1 AI 数字人学习导师交付报告

日期：2026-09-29。范围：只实现 V2.1，不包含知识图谱、编程评测、面试增强或求职中心。

2026-10-01 的加固改动与重新验收见 [V2.1.1 交付报告](V2_1_1_DIGITAL_HUMAN_DELIVERY.md)。本文保留首次交付时的历史测试结果。

## 1. 现役项目核对

| 项目 | 当前事实 |
|---|---|
| 技术栈 | Vue 3 + TypeScript + Vite；FastAPI；SQLite WAL；Python；Tauri 2 桌面壳 |
| 核心目录 | `filemate/web/src/` 为前端；`server.py` 为 HTTP 层；`filemate/execution/storage.py` 为版本化存储；`filemate/tests/` 为回归测试 |
| 数据身份 | 桌面/本机模式使用本地库；公网匿名模式由签名 HttpOnly Cookie 选择独立租户数据库、上传和归档目录；登录/注册页面尚非正式账号体系 |
| 文件/AI | 资料经 `/process` 导入并持久化为 Source/Context/Artifact；现役模型调用走 LLM 封装，AI 对话回答已保存在 Context；面试页已有零散的浏览器 Web Speech 朗读 |
| 可复用组件 | FileMate 原有校园导师形象和表情素材、学习工作区会话、统一 Axios API、SQLite 迁移、自然绿设计令牌 |
| 潜在冲突 | 工作区原有未提交的 v16 错因、目标反推和面试改动仍在进行。本模块只在其后新增 v17，未重写既有业务或覆盖原有改动 |

## 2. 最小实现及用户影响

从学习工作区已保存的 assistant 回答点击“让 AI 导师讲解”，可进入 `/digital-human` 并恢复原文；也支持手动输入。真实链路为文字 → 浏览器 Web Speech 语音合成与扬声器播放 → `onstart` / `onboundary` / `onend` 事件驱动字幕、进度与口型近似动画。超过 140 字时分段朗读，避免一次性提交长文本。默认采用 FileMate 品牌近景形象，并可切换全身形象和设备上可用的中文声线；形象配置和 `DigitalHumanProvider` 接口分别位于独立模块。

支持播放、暂停、继续、重播、停止、语速、音量、字幕、全屏、形象/声音切换，以及舞台内右下角悬浮卡片的拖动、缩放、收起与展开。编辑讲解稿时会停止旧播报，避免音画文本错位。失败保留原讲解稿，显示错误和重试入口，不修改原 AI 答案。

## 3. 修改文件、数据库与接口

| 类别 | 文件/变化 |
|---|---|
| 前端 | `filemate/web/src/views/DigitalHuman.vue`；`filemate/web/src/digital-human/provider.ts`、`avatars.ts`；路由、侧栏、学习工作区回答入口；`services/api.ts` |
| 后端 | `server.py` 增加独立数字人日志接口及开关；`filemate/execution/storage.py` 增加 v17 迁移和播报记录方法 |
| 测试 | 新增 `filemate/tests/test_digital_human.py`；现有迁移测试更新至 v17 |
| 文档 | `README.md`、`filemate/docs/API_SPEC.md` 和本报告 |

SQLite v17 新增 `digital_human_playbacks`：`playback_id`、会话/消息引用、字数、形象、声线、Provider、`module_version=2.1`、状态、错误码、创建/更新时间、软删除时间。不保存讲解正文、生成音频或额外用户标识；本地/匿名租户库本身决定身份。会话引用必须指向当前身份已保存的 assistant 消息，避免跨用户或非 AI 内容越权引用。

新增 API：

- `GET/POST /api/digital-human/playbacks`
- `PATCH/DELETE /api/digital-human/playbacks/{playback_id}`
- `POST /api/digital-human/playbacks/{playback_id}/restore`

终态幂等，删除可撤销，重复删除/恢复安全。详细请求合同见 `filemate/docs/API_SPEC.md`。

## 4. 测试结果

仓库门禁 `scripts/verify.ps1`：Ruff 通过；后端非 e2e 测试 **476 通过、18 条环境条件跳过、5 条 e2e 按脚本约定未运行**；前端 TypeScript 检查与 Vite 生产构建通过。新增后端测试覆盖 50/500 字播报元数据、持久化、无正文/音频存储、重复终态、软删除/恢复、无效输入、非 assistant 会话、内容变更、功能关闭和两个匿名浏览器间隔离。

浏览器手工自动化验收在隔离临时数据库与 Chromium 中进行，使用的是明确的合成测试文案，而非真实用户实验：

| 场景 | 观察结果 |
|---|---|
| 50 字 | 页面可打开，`speechSynthesis.speaking=true`、讲解/口型状态推进，完成后记录为 `completed` |
| 已保存回答入口 | 在合成学习会话中点击“让 AI 导师讲解”，进入带 `ctx`/消息序号的页面，恢复原 51 字 assistant 回答并完整播报，没有重新生成或复制答案到 URL |
| 500 字 | 分段播放至完成；暂停时浏览器 `paused=true`，继续后进度和口型继续；停止记录为 `stopped` |
| 形象/声线 | 全身与近景切换有实际视觉变化；可选设备中文声线；声音与形象独立配置 |
| 错误/重试 | 浏览器离线时显示网络错误，500 字讲解稿保留，恢复在线后重试成功 |
| 控件/记录 | 收起/展开、全屏、删除记录和立即撤销删除均已在页面实测 |
| 响应式 | 375、768、1024、1440 px 下页面无横向溢出；手机尺寸仍可操作主要控件 |

## 5. 已知限制与待优化

1. Web Speech 是浏览器/系统的语音能力；某些声线可能依赖网络，不能承诺完全离线。FileMate 播报日志 API 不接收原文，但敏感内容是否离开设备还取决于浏览器声线实现，页面已有提示。
2. 口型根据语音开始/边界/结束事件和播放期间节律切换，属于基本近似同步，不是音素级驱动。浏览器没有向页面提供可复用的 PCM 音频文件；本轮不提供音频导出。
3. 声线列表、边界事件精度及实际扬声器输出受操作系统和浏览器影响。浏览器验收观察了 TTS 状态和字幕/口型，没有录制扬声器音频进行声学评分；不把它表述成音质或对齐精度评测。
4. 数字人页面本轮聚焦已保存 AI 回答与手动稿；不会自动朗读所有摘要、错题和提醒，也未接入外部数字人供应商。
5. 当前工作区包含其他用户未提交改动；本轮未做 Git 提交或部署，以免把那些工作误并入 V2.1。应用壳仍显示现役 `v1.3 α`，V2.1 是本次模块交付标识，并非已发布安装包版本。

## 6. 关闭与回滚

- 前端构建时设 `VITE_ENABLE_DIGITAL_HUMAN=false`：隐藏路由、导航和学习回答入口；旧页面不受影响。
- 后端设 `FILEMATE_ENABLE_DIGITAL_HUMAN=0`：独立数字人接口返回 503；健康检查、资料、AI 对话、面试等路由继续工作。
- SQLite v17 表为独立新增表。停用/回退应用代码时保留表与现有记录，不删除用户数据；需要彻底清理时必须另行取得数据删除授权并先备份。
- 单条播报记录可在页面软删除并立即撤销。停止语音不会改写原 AI 回答。

## 7. 下一版本建议

等待明确继续指令后再进入 V2.2。V2.1 后续小版本优先考虑可验证的本地 TTS Provider、真实音素/音频驱动口型、跨浏览器兼容测试，以及将面试页现有 TTS 迁移到同一 Provider 接口；不在本轮扩大实现范围。
