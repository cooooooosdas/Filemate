# FileMate V2.1.1 数字人学习导师交付报告

日期：2026-10-01（北京时间）。本轮仅加固现有 V2.1；未开发 V2.2–V2.5。V2.1 专项验收通过，但全项目门禁仍有一项已有 V2.2 失败，不能据此宣称整个项目可发布。

## 版本与现役项目分析

本轮模块版本为 **V2.1.1**，应用版本仍为 `1.3.0-alpha.1`，播报记录的 `module_version` 继续使用 `2.1`。开始时工作区已有 V2.1 页面、Provider、播报表及首次交付报告，另有大量未提交的知识图谱、目标规划和面试工作；本轮保留这些内容，在本地分支 `codex/v2-1-playback-reliability` 工作，未提交、推送或部署。

| 核对项 | 代码事实与复用方式 |
|---|---|
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia；页面在 `filemate/web/src/views`，API 在 `services/api.ts` |
| 后端与数据库 | FastAPI、Python、SQLite WAL；当前迁移最高版本 v20，数字人独立表由已有 v17 创建 |
| 身份与文件 | 本机模式用本地数据库；生产匿名 Cookie 选择独立租户库、上传和归档目录；登录页尚未接入正式账号体系 |
| 已有页面 | 工作台、今日学习、上传/分类/命名/日程、历史、学习工作区、知识库、计划、错题、面试、成长和隐私中心；数字人入口已存在于已保存的 assistant 回答旁 |
| AI 与解析 | 文件解析走 `perception`，模型走 `LLMClient` 和 Provider；AI 回答已保存于 Context，无需再次调用模型生成讲解内容 |
| TTS 与形象 | 复用浏览器 Web Speech、`DigitalHumanProvider`、两个品牌形象配置；面试页原有朗读未迁移，以控制范围 |
| 日志与导出 | 复用独立播报元数据记录、删除/恢复 API；其他模块已有导出能力；浏览器 TTS 不提供本轮可保存的音频文件 |
| 部署与视觉 | 本机 Web、Tauri Sidecar 与已有容器部署配置；沿用浅色自然绿、系统字体、品牌人物与 10/14 px 圆角 |

实施方案：保留现有文字 → 浏览器 TTS → 播放语音 → 语音事件驱动近似口型的闭环，补齐超时、取消、暂停/重播、上下文切换和日志恢复；先完成专项回归，再执行项目门禁及真实浏览器验收。

## 本次新增与用户影响

- 每段语音等待启动最多 15 秒；开始后按字数和语速设置完成超时。暂停会暂停计时，继续恢复剩余时间，防止长时间暂停被误报为失败。
- 暂停后重播会恢复浏览器语音队列；停止、失败或新讲解会释放旧计时器、保留当前 utterance 引用并忽略迟到/重复事件。
- 捕获语音启动、暂停、继续和声线读取异常，显示可重试错误，保持讲解正文可用。
- 50/500/5000 字分段不丢字；不会在两个 UTF-16 代理项之间拆开生僻字。页面字数与后端使用一致的 Unicode 字符计数。
- 同页只改变 `ctx` / `message` 时，重新读取已保存回答；旧请求晚到不会覆盖新稿。读取失败的“重试”会重新读取答案。
- 日志请求超时缩短为 15 秒。完成/停止/失败同步异常时提供“重试同步”，只补写终态，不重新播报或创建记录。播放中删除记录会先停止并同步，再软删除；可以撤销。
- 拖动在指针取消、形象/尺寸变化和页面卸载时清理监听；舞台尺寸变化会复位位置。选择框有明确无障碍名称，导师按钮点击目标至少 44 px。
- 前端关闭模块后，旧 `/digital-human` 链接返回学习工作区，避免空白路由；侧栏和答案入口保持隐藏。
- 修复一项旧测试的 TXT 注册表污染：使用 pytest `monkeypatch` 恢复原解析器，不改动生产解析逻辑。

## 修改文件

以下只列本轮文件，不把工作区已有其他模块改动算作本轮实现：

| 文件 | 本轮变化 |
|---|---|
| `filemate/web/src/digital-human/provider.ts` | 语音任务生命周期、超时、暂停恢复、Unicode 分段与错误翻译 |
| `filemate/web/src/views/DigitalHuman.vue` | 路由重载、异步取消、日志同步重试、拖动清理和无障碍控件 |
| `filemate/web/src/router/index.ts` | 关闭数字人时旧链接重定向 |
| `filemate/web/src/services/api.ts` | 数字人日志客户端 15 秒超时 |
| `filemate/web/tests/digital-human-provider.test.mjs` | 新增 9 项语音 Provider 自动回归，明确标记 MOCK |
| `filemate/tests/test_digital_human.py` | 增补 10 项后端回归，专项共 14 项 |
| `filemate/tests/test_perception.py` | 修复旧测试注册表清理导致的顺序污染 |
| `scripts/acceptance/digital_human.mjs` | 可重复浏览器验收，区分真实 TTS 与 MOCK 异常场景 |
| `scripts/acceptance/seed_digital_human.py` | 只能在 `_working` 内准备合成会话 |
| `filemate/web/package.json`、`scripts/verify.ps1`、`.github/workflows/ci.yml` | 将 Node 24 原生测试纳入本地与 CI 前端门禁，无新增 npm 依赖 |
| `README.md`、`filemate/docs/API_SPEC.md`、`scripts/acceptance/README.md`、两份 V2.1 交付报告 | 同步现役行为、运行方式、证据和限制 |

## 数据库变化与新增接口

本轮 **无新增迁移、无新增 HTTP API、无新增用户数据字段**；没有改动 `server.py` 或 `storage.py`。继续复用已有 v17 `digital_human_playbacks` 和 GET/POST/PATCH/DELETE/restore 接口。日志仍不存讲解正文或音频，按当前本地/匿名身份隔离，终态更新和删除/恢复仍幂等。

当前全库 v20 是已有工作区事实，不能将 v18–v20 记为本轮数字人变更。Provider 超时只是前端行为，不改变既有接口请求/响应结构。

## 测试结果

全部资料和文案为**合成工程回归数据**，不是真实用户研究，不代表音质、能力或学习效果评测。

| 检查 | 实际结果 |
|---|---|
| 数字人后端专项 | **14 / 14 通过**；含持久化、5000 字生僻字、参数错误、答案保留、全部接口关闭、租户隔离、重复终态与删除/恢复 |
| Node 24 语音 Provider | **9 / 9 通过**；含 50/500/5000 字、空输入、无效设置、无声线、不支持 TTS、网络错误、无响应超时、暂停超时、重复/迟到事件和取消 |
| Edge 浏览器完整验收 | **10 / 10 通过，0 页面异常**；375/768/1024/1440 px 无横向溢出，舞台内卡片可见，形象/字幕/全屏可用 |
| 真实语音 | 50 字及 500 字均播报至完成；500 字实际暂停/继续、暂停后重播和停止成功；设备返回 Huihui/Kangkang/Yaoyao 本地中文声线 |
| 异常 UI | 明确 MOCK 设备事件 + 真实隔离 API：创建失败重试、响应前取消、终态同步重试、暂停失败、答案读取重试、删除/恢复均通过 |
| 最新播放中删除回归 | **1 / 1 通过**；停止、删除、撤销后原回答保留，无悬挂同步重试 |
| 前端关闭模块 | 首页、学习工作区、知识库及旧链接重定向 **4 / 4 检查通过**；导师入口隐藏 |
| 静态与生产构建 | 仓库 Ruff 和新增文件 Ruff 通过；Vue 类型检查、Vite 生产构建、`git diff --check` 通过 |
| 全项目 `scripts/verify.ps1` | **未通过：502 passed、1 failed、18 skipped、5 deselected**；脚本在后端失败后按合同停止，前端测试/构建另行执行并通过 |

唯一剩余失败是 `test_knowledge_graph.py::test_local_extraction_is_grounded_and_supports_relations`：已有 V2.2 本地定义提取正则要求至少两个汉字，漏掉“栈”这个单字术语。单独运行也失败；该源码及测试在本轮开始时已存在，本轮未修改。这是进入下一阶段或正式发布前的依赖，不能通过跳过测试来包装门禁通过。

原本另一项资料导入失败经独立运行通过，确认是旧 `test_truncation` 删除了已经加载的 TXT 解析器。修正测试隔离后，全量回归中资料导入恢复通过。Windows 目录联接下直接构建曾触发 Vite 路径错误；按已有 `verify.ps1` 的约定在真实目录 `D:\FileMate-Project\filemate\web` 执行构建后通过。

机器可读临时证据：

- `_working/v2-1-20261001/browser-final/results.json`：10 项完整验收，含真实语音与宽度证据。
- `_working/v2-1-20261001/active-delete/results.json`：最新播放中删除验收。
- `_working/v2-1-20261001/disabled-results.json`：模块关闭的 4 项页面检查。
- 同目录的浏览器截图与隔离 SQLite；不提交这些资料、构建产物或进程日志。

复跑方式见 `scripts/acceptance/README.md`；`FILEMATE_CASE_FILTER` 可以只复跑指定浏览器场景。Node 测试已加入本地门禁及 CI 配置，但本轮未触发远端 CI，也不报告远端状态。

## 已知问题与待优化

1. 口型仍由语音事件和播放节律近似驱动，尚无音素级对齐。浏览器语音流程和画面状态已经实测，没有采集扬声器录音进行音质或声学同步评分。
2. 声线能力受浏览器/系统影响；其他设备可能使用网络语音，本轮不能保证所有环境完全离线。页面维持说明。
3. 终态同步重试队列只在当前页面保留。离开或刷新时网络仍不可用，记录可能保留 `started`，历史明确标识“播放中或未正常结束”，不伪造完成状态。
4. 已有 V2.2 测试失败阻止全项目发布门禁；已有前端主包体积警告仍在，未在本轮扩大性能重构。
5. 没有接入外部数字人、STT 或服务端音频生成，也没有修改其他学习业务、完成新知识图谱版本或生成正式安装包。

Web Speech 的事件、暂停和取消行为参考 [MDN SpeechSynthesisUtterance](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance)、[pause](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/pause) 和 [cancel](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/cancel)。播放超时预算为本项目的保守工程策略，并非浏览器规范保证。

## 回滚方式

- 前端构建/启动设置 `VITE_ENABLE_DIGITAL_HUMAN=false`：隐藏导师导航和答案入口，旧讲解链接返回工作区。
- 后端设置 `FILEMATE_ENABLE_DIGITAL_HUMAN=0`：仅数字人接口关闭；已保存答案、知识库和健康接口已验证可用。
- 单条日志可软删除并撤销；停止或失败不改写原 AI 回答。
- 本轮无 migration，关闭功能或回退本轮代码即可。不要删除数据库或已有 v17 表，也不要用整库 `git reset --hard` 回滚当前包含其他未提交工作的工作区。
- 测试使用独立 `_working` 数据与本机服务；验收后停止这些服务，正常应用仍按原启动脚本使用自己的数据目录。

## 下一版本建议

先处理已记录的 V2.2 既有门禁失败，再由用户明确指示是否进入 V2.2。V2.1 的后续小版本可评估可离线 TTS 与音素驱动 Provider，并保留当前业务接口；本轮没有自动开始后续模块。
