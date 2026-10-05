# FileMate 自动化验收脚本

2026-10-04面试模型专项：`interview_analysis.mjs`覆盖8份原创合成回答（不会的短答、概念、口语、换行、英文、项目、长答及无标点），从真实页面提交到逐题分析、原句核对、报告持久化/刷新及PDF/JSON/Markdown下载；使用当前真实模型，不替换响应。还验证仅本轮合成失效密钥的明确错误、旧报告保留、重新分析恢复、跨访客拒绝、缓存幂等和预览确认清理。默认连接`https://filemate.asia`，需部署模型可用；本机可设置`FILEMATE_WEB_URL`/`FILEMATE_API_URL`。设置新的`FILEMATE_EVIDENCE_DIR`后执行`node scripts/acceptance/interview_analysis.mjs`，不读取用户密钥或真实面试。

脚本先串行请求`/api/auth/me`初始化自己的空游客空间，再创建合成会话，避免首屏并发初始化与验收写入竞争身份。每例默认间隔20秒，`FILEMATE_INTERVIEW_INTERVAL_MS`只允许延长；保留生产限流，不自动重试失败用例。网络证据只记录路径、状态和耗时，失败记录附本轮合成会话ID，不记录密钥、Cookie或请求正文。`FILEMATE_BROWSER_DIRECT=1`仅让本次无头浏览器直连以排查本机代理，不改系统设置；默认沿用浏览器网络配置。最终实际网站直连复测9/9通过，前三轮超时/429现场独立保留，见[交付报告](../../docs/INTERVIEW_ANALYSIS_FIX_2026-10-04.md)。

DEV-01资料入口专项：`workspace.mjs`追加Markdown和C++实际浏览器上传、原文/块引用/哈希复用/会话重载以及无自动模型调用检查，共25项（原23＋新增2）。Markdown中的HTML和脚本内容作为原文读取，源码不执行；后端另覆盖新增10种后缀、大小写、错误编码/空白、其他后缀拒绝及Python无执行副作用。新卡采用`_working/learning-text-inputs-20261003/`独立证据，不改写此前UI基线的23项历史结果。

2026-10-03布局与图标收口新增`knowledge_layout.mjs`。在实际TLS预检追加`--layout-checks`，与`--visual-checks --review-checks --workspace-checks`组合使用；使用新的输出目录与对应最终编译包。检查知识库大字/无下拉、资料名筛选/范围/引用、反馈问题快照、真实学习链、迟到响应隔离、故障重试、弹窗键盘及编辑保护、JSON校验/保存/重载/下载/删除、四宽度布局及导航底板对齐、减弱动画、实际学习入口和许可证分发。场景资料与模型均为明确本地合成工程夹具，正常HTTP响应不替换，延迟/中断由浏览器显式注入；不使用真实用户资料或外部模型。启动、凭据隔离、端口冲突检查和进程清理沿用`gateway_preflight.py`。

本目录存放由产品/评测侧维护的可复现验收脚本，不修改 `server.py`、`storage.py`、`api.ts` 等高冲突文件。

## 2026-10-02 集成总验收入口

### 合成教材与实际模型

`uv run python scripts/acceptance/synthetic_learning.py --out _working/新的合成学习目录` 会生成7份明确标记为synthetic的原创TXT资料，连接既有模型适配层，检验分类/实体/命名、多阶段通知、学习产物、带引用问答、无依据零调用拒答、作答复练、去重及新Python进程读取。最多64次模型调用，单次30秒且不做连接级重试。输出目录必须尚未存在且位于项目 `_working`，不会填充或改写历史 `datasets/raw`。结果、材料SHA256及仅含合成内容的模型返回均保留；这些数据不证明真实学生学习效果。

### B2 统计证据页面

在已通过构建的隔离前端副本执行统一运行器，使用 `--cases evidence_profile`。新增9项验收覆盖待评测、明确合成的SQLite行为夹具、来源题集回看、只读刷新、注入读取失败重试以及375/768/1440布局。夹具不构造导师评分或实际参与者，面试记录为未评估的本地回退。

### B3 RC只读准备

`release_readiness.py --capture-baseline <新JSON路径>`保存测试前代码指纹；测试后传入 `--baseline`、`--gate-log`、`--browser-summary`、`--synthetic-report` 和新 `--output` 汇集证据，禁止覆盖已有输出。报告区分工程通过和正式冻结，未采集真实数据时保持0样本与团队待办；命令退出0只表示报告生成，`--require-ready`在人工冻结前退出1。复跑命令与覆盖范围见[RC清单](../../docs/RC_ACCEPTANCE_CHECKLIST.md)，本轮结果见[B2/B3交付](../../docs/B2_B3_ENGINEERING_CLOSEOUT_2026-10-02.md)。工具不提交、部署、改版本或停止服务。

运行 `scripts/verify.ps1 -IsolateFrontend` 后，将日志中生成的前端副本路径传入：

```powershell
uv run python scripts/acceptance/programming_native.py --out _working/新总验收目录/native
uv run python scripts/acceptance/integrated_browser.py --web-root _working/verify-web-实际ID --out _working/新总验收目录/browser
uv run python scripts/acceptance/website_health.py --base https://filemate.asia --output _working/新总验收目录/website.json
```

Windows整合浏览器验收中的编程与岗位算法练习需要已准备并通过真实自检的MSVC隔离工具链；先执行上方native验收，再运行集成浏览器，避免把未准备的环境当作网站功能失败。公网Linux的真实GCC/gVisor链路另按`linux_judge.py`与`production_api.mjs`验证，不使用Windows结果替代。

`integrated_browser.py` 默认顺序执行17组验收，每组创建全新SQLite与上传/归档目录，启动并停止自己持有的API/Vite进程。默认8028/5198已占用时直接拒绝；可用 `--api-port`、`--web-port` 修改。支持 `--cases` 定向复跑，输出目录必须尚未存在，不覆盖失败现场。真实TTS与编译需要Windows现有设备/工具链；视觉合成夹具沿用下文固定SHA256文件。

Vite代理统一读取 `VITE_API_URL`，未设置时继续使用8001；生产编译包仍由生产代理提供同源API。新版路由冒烟覆盖22页/9接口，并等待真实页面内容就绪。新增 `digital_human_disabled.mjs` 验证4页、5个关闭路由及3个原接口。网站探测仅顺序GET，不上传、提交或调用模型；首页失败或健康探测失败均以非零退出码报告，健康接口成功不能代表页面可用。

`collect_audit.py --evidence _working/integrated-audit-20261002` 汇总本轮既有证据布局、资源SHA256与最新复测结果，不启动服务，也不合并真实/合成样本。其他日期使用同一组织布局并指定新目录；首轮失败与复测分别保存。详细结果与边界见 [总验收报告](../../docs/INTEGRATED_AUDIT_2026-10-02.md)。

## 目录

- `flow2_api.py`：流程 2 端到端验收（导入 → 摘要/知识卡/笔记 → 知识库 → 重启可查）；运行前需配置可用的 LLM 环境变量。
- `flow4_api.py`：流程 4 API 闭环验收（出题→作答→错题→今日复习→掌握）。
- `a3_lifecycle.py`：A3 数据生命周期验收（创建→重启可读→删除预览→删除→外部文件不删→重复删除 404）。
- `browser_smoke.mjs`：Playwright 浏览器路由冒烟（需先启动 FastAPI 与 Vue）；任一路由/API/控制台检查失败时返回非零退出码。
- `digital_human.mjs`：数字人真实语音、响应式与异常操作验收。50/500 字使用真实浏览器语音，其余异常场景明确使用 MOCK 设备事件并连接真实隔离 API。Node 24、根目录 Playwright 依赖；Windows 默认使用已安装 Edge，其他平台使用 Playwright Chromium。
- `seed_digital_human.py`：仅允许在 `_working` 内创建合成回答会话，拒绝指向真实应用数据目录。
- `knowledge_graph.mjs`：真实公开教材上传、解析、本地提取、确认、图谱、UI作答、错题复练、画像、计划与撤销闭环；异常网络使用明确标记的故障注入。
- `knowledge_graph_disabled.mjs`：另起 `VITE_ENABLE_KNOWLEDGE_GRAPH=false` 的5174前端和 `FILEMATE_ENABLE_KNOWLEDGE_GRAPH=0` 的8002后端，核对4个页面、9个关闭接口及3个原有接口。支持 `FILEMATE_DISABLED_WEB_URL` / `FILEMATE_DISABLED_API_URL` 更改地址。
- `seed_graph_exercise.py`：在临时数据库中为已导入的《Hello 算法》节选添加一题自编练习；不填作答、不假冒模型生成。节选出处与 CC BY-NC-SA 4.0 许可在 `fixtures/hello_algo_heap_excerpt.txt`。

## 运行方式

```powershell
# 流程 4 / A3：使用临时 SQLite，不污染真实数据
.venv\Scripts\python.exe scripts\acceptance\flow4_api.py
.venv\Scripts\python.exe scripts\acceptance\a3_lifecycle.py

# 浏览器冒烟：先启动 FastAPI 和 Vue，再安装 Playwright 后运行
cd _working\playwright-runner
npm install playwright
node <repo>\scripts\acceptance\browser_smoke.mjs
```

输出写入 `_working/`，属于临时证据，不入库。

三个脚本都以退出码作为验收结论，不能只检查是否生成 JSON 文件。

数字人验收须先在独立终端配置临时数据，再启动后端；不得连接真实用户数据库：

```powershell
$env:FILEMATE_DATA_DIR = Join-Path (Get-Location) '_working/digital-human/data'
$env:FILEMATE_DB_PATH = Join-Path $env:FILEMATE_DATA_DIR 'acceptance.db'
$env:FILEMATE_UPLOAD_DIR = Join-Path $env:FILEMATE_DATA_DIR 'inbox'
$env:FILEMATE_ARCHIVE_DIR = Join-Path $env:FILEMATE_DATA_DIR 'archive'
$env:FILEMATE_IDENTITY_MODE = 'local'
uv run python scripts/acceptance/seed_digital_human.py --db $env:FILEMATE_DB_PATH
uv run python server.py
# 另开终端，启动 Vue：uv run python scripts/run_vite.py
# 再开终端，在项目根目录执行：
node scripts/acceptance/digital_human.mjs
```

`FILEMATE_WEB_URL` 可修改页面地址，`FILEMATE_EVIDENCE_DIR` 可修改临时证据目录，`FILEMATE_BROWSER_CHANNEL` 可指定已安装的浏览器渠道。结果写入 `results.json`；真实语音事件只能证明设备语音流程推进，不能代替音质或音素对齐测量。

知识图谱验收使用一个全新的临时库，按上述方式将数据目录、DB、上传目录和归档目录全部改到 `_working/v2-2-acceptance`，以 `FILEMATE_IDENTITY_MODE=local` 启动 API/Vue，然后执行：

```powershell
$env:FILEMATE_ACCEPTANCE_DB = Join-Path (Get-Location) '_working/v2-2-acceptance/acceptance.db'
$env:FILEMATE_EVIDENCE_DIR = Join-Path (Get-Location) '_working/v2-2-acceptance'
node scripts/acceptance/knowledge_graph.mjs
```

`FILEMATE_ACCEPTANCE_DB` 必须与正在运行的隔离后端数据库一致，且位于项目 `_working`。真实资料内容通过现役上传 UI 导入；自编题只补充测试输入，知识提取、判题、画像、错题和计划均调用真实实现。无需外部 LLM；这不是模型质量测量或真实用户研究。首次空库断言要求每次从新库开始，结果与375/768/1024/1440截图写到证据目录。

## V2.3 编程评测

Windows x64需要已安装MSVC与Windows SDK。原生脚本使用原创题和测试程序，真正编译并执行，覆盖8题×5判定、最大规模数据和9项隔离探针，输出49项证据：

```powershell
uv run python scripts/acceptance/programming_native.py --out _working/v2-3/native
# 仅重跑隔离探针：添加 --security-only
```

UI验收使用全新 `_working` 数据库，设置 `FILEMATE_DATA_DIR`、`FILEMATE_DB_PATH`、上传与归档目录。默认独立后端端口8002，CORS仅允许 `http://127.0.0.1:5174`；前端设 `VITE_API_URL=http://127.0.0.1:8002` 并启动5174。运行：

```powershell
$env:FILEMATE_WEB_URL='http://127.0.0.1:5174'
$env:FILEMATE_API_URL='http://127.0.0.1:8002'
$env:FILEMATE_EVIDENCE_DIR=Join-Path (Get-Location) '_working/v2-3/ui'
node scripts/acceptance/programming.mjs
```

该脚本从新库开始，通过实际键盘输入Monaco、编译/评测、复盘、取消、重复键、撤销/恢复和375/768/1024/1440截图验收。模型失败和读取故障两项明确标为注入测试，不进行外部LLM质量测量。原创参考代码只作为测试输入，不参与评测引擎的输出判定。

关闭模块验收使用另一个新库：后端8003设 `FILEMATE_ENABLE_PROGRAMMING=0`，CORS允许5175；前端5175设 `VITE_API_URL=http://127.0.0.1:8003`、`VITE_ENABLE_PROGRAMMING=false`，运行 `node scripts/acceptance/programming_disabled.mjs`，验证12个关闭接口、旧URL回退和3个原有接口。

本机已有Vite运行时，全量校验可执行 `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`。后端照常检查，前端复制到新建的 `_working/verify-web-*` 后执行npm ci/test/build/check:bundle，避免Windows原生依赖文件锁影响现有服务；无此参数时命令行为保持原样。副本是临时验证证据，不提交。

`integrated_browser.py --cases browser_smoke frontend_production`依次复核22页/9接口与生产包8项专项。专项使用真实隔离API，编译JS/CSS原样加载；只有资源中断和API延迟为明确故障注入。首页累计入口、Home及递归静态依赖，预算为JS450KiB、估算gzip140KiB、CSS150KiB；`--measure-only`仅用于记录历史超预算包，不能代替门禁。详见[当前交付](../../docs/FRONTEND_PRODUCTION_QUALITY_DELIVERY_2026-10-03.md)。

## V2.4 面试增强

使用两个全新 `_working` 数据库，避免私人记录参与测试。开启增强的后端默认8014，设 `FILEMATE_INTERVIEW_LOCAL_ONLY=1`、`FILEMATE_ENABLE_INTERVIEW_REVIEW=1`、`FILEMATE_IDENTITY_MODE=local`，CORS允许 `http://127.0.0.1:5184`；前端5184设 `VITE_API_URL=http://127.0.0.1:8014`，增强开关默认开启。两端分别运行 `uv run uvicorn server:app --host 127.0.0.1 --port 8014` 和 `npm.cmd run dev -- --host 127.0.0.1 --port 5184 --strictPort`，前端命令在 `filemate/web` 执行。

合成人脸视频使用 [scikit-image 的 NASA 宇航员公共领域图片](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut)，不是本机用户摄像头或真实试用记录。取得固定版本输入并运行：

```powershell
New-Item -ItemType Directory -Force _working/v2-4-20261001 | Out-Null
Invoke-WebRequest 'https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png' -OutFile _working/v2-4-20261001/astronaut.png
$env:FILEMATE_FACE_FIXTURE=Join-Path (Get-Location) '_working/v2-4-20261001/astronaut.png'
$env:FILEMATE_EVIDENCE_DIR=Join-Path (Get-Location) '_working/v2-4-20261001/ui'
node scripts/acceptance/interview_review.mjs
```

夹具 SHA256：`88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`。后端数据目录另设 `FILEMATE_DATA_DIR`、`FILEMATE_DB_PATH`、`FILEMATE_UPLOAD_DIR`、`FILEMATE_ARCHIVE_DIR` 到 `_working` 中，每次验收使用新库。可用 `FILEMATE_WEB_URL`、`FILEMATE_API_URL`、`FILEMATE_BROWSER_CHANNEL` 调整地址和浏览器（默认msedge）。

脚本真实运行 MediaPipe Worker 与 MediaRecorder，但设备输入来自 canvas 合成流，语音识别回调为注入。14项包含模型资源本机加载、人脸/暗光/无人脸、语音口头语/停顿、录像定位、五轮保存、已接收请求丢响应后的幂等重试、PDF/JSON/Markdown/录像实际下载、读取与模型故障、375/768/1024/1440截图、刷新恢复、取消确认和整场删除。网络记录核对无音视频/帧外发；不会调用真实外部模型。输出 `summary.json`、`results.json`、截图和下载文件。

关闭验收另起8015后端，`FILEMATE_ENABLE_INTERVIEW_REVIEW=0`、CORS允许5185；前端5185设 `VITE_API_URL=http://127.0.0.1:8015`、`VITE_ENABLE_INTERVIEW_REVIEW=false`。在新库运行 `node scripts/acceptance/interview_review_disabled.mjs`，核对八个增强路由503、原文字练习正常、增强控件隐藏及健康/资料/题库可用，共14项。

生产包视觉验收在已构建前端目录运行 `npm.cmd run preview -- --host 127.0.0.1 --port 5186 --strictPort`。运行 `node scripts/acceptance/interview_vision_production.mjs`，默认将同源API请求转到独立8014测试后端，模型/WASM资源直接访问生产包；合成摄像头和拒绝麦克风情况下，核对预览播放、实际采样保存与同源生产Worker。设置 `FILEMATE_INJECT_BITMAP_FAILURE=1` 另测一次图像分配失败后的canvas本地转换回退；此项为明确故障注入。通过 `FILEMATE_EVIDENCE_DIR` 选择不同 `_working` 输出，避免覆盖常规与故障证据。

PDF导出嵌入项目中文字体；人工渲染核对分页和长回答换行。真实导师校准需另提供匿名配对数据：

```powershell
uv run python evaluation/calibrate_interview.py evaluation/datasets/interview_expert_scores.template.csv --output _working/v2-4-20261001/expert-calibration.json
```

空模板输出“真实专家校准待评测”。本工具不生成专家分数、不混合合成样本，也不把相关性作为准确率。

## V2.5 求职训练中心

`career_state.mjs`补充岗位/训练浏览器后退、草稿离开确认，以及岗位证据→原知识点→学习计划保存/撤销/恢复四项回归。使用明确标注的合成岗位与资料，不调用模型或推断招聘效果；沿用下列URL和证据目录环境变量。

每次使用全新的 `_working` 测试目录，设置 `FILEMATE_DATA_DIR`、`FILEMATE_DB_PATH`、`FILEMATE_UPLOAD_DIR`、`FILEMATE_ARCHIVE_DIR` 到该目录，`FILEMATE_IDENTITY_MODE=local`、`FILEMATE_INTERVIEW_LOCAL_ONLY=1`。默认开启测试为后端8016、前端5187，CORS只允许 `http://127.0.0.1:5187`；前端设 `VITE_API_URL=http://127.0.0.1:8016`。分别运行：

```powershell
# 根目录，环境变量在本终端设置完成后
uv run uvicorn server:app --host 127.0.0.1 --port 8016
# 另开终端，在 filemate/web 配置 VITE_API_URL 后
npm.cmd run dev -- --host 127.0.0.1 --port 5187 --strictPort
# 第三个终端，在根目录
node scripts/acceptance/career.mjs
```

默认msedge，沿用根目录验收脚本所需的Playwright运行时。`FILEMATE_WEB_URL`、`FILEMATE_API_URL`、`FILEMATE_EVIDENCE_DIR` 可选择其他**独立且未占用**的端口与 `_working` 输出，不重启用户现有服务。脚本从空库开始，保存核对过的目录快照，使用合成回答/自编参考代码，不导入私人资料或采集音视频，不调用真实外部模型。

13项检查包括：搜索/类别/空态、来源核对与取消、训练快照、完整基础作答与幂等、实际隔离C++ AC及提交深链、V2.4真实本地会话回答与报告、JSON/Markdown实际下载、编辑旧快照与过期修订、撤销恢复、读取故障、TXT导入及已接收请求丢响应的同键重试、响应式和预览确认删除。写入 `results.json`、`summary.json`、下载与截图。移动端截图须等待有限CSS过渡完成，同时断言内容实际边界在视口内；只检查scrollWidth不能发现动画中的遮挡。

C++检查要求V2.3工具链已准备且隔离自检通过；未就绪时应明确报告该项不通过，不能伪造AC。其余流程无模型密钥依赖。网络故障两项为明确注入，真实外部模型失败和匿名隔离由 `test_career.py` 的合成接口回归覆盖，不代表真实供应商质量实验。

关闭检查使用另一个全新目录：后端8017、`FILEMATE_ENABLE_CAREER=0`、CORS允许5188；前端5188设 `VITE_API_URL=http://127.0.0.1:8017`、`VITE_ENABLE_CAREER=false`。运行 `node scripts/acceptance/career_disabled.mjs`，核对状态可读、21种操作503（含四种岗位计划操作）、旧URL回退、原面试作答及4个旧接口、成长页求职面板隐藏，共29项。关闭不会删除记录，数据恢复由专项测试验证。

`career_growth.mjs` 使用独立8019后端和5191前端，沿用上述临时数据目录与本地面试环境变量，CORS允许5191，前端 `VITE_API_URL=http://127.0.0.1:8019`。从没有求职岗位的临时库开始，先等待真实成长页面就绪，再核对接口；六项覆盖空态、真实作答/面试计数、只读刷新与原记录深链、读取失败保留及重试、375/768/1440布局、撤销保留历史和删除保留原面试。运行 `node scripts/acceptance/career_growth.mjs`，默认输出 `_working/v2-5-20261001/growth`。更早保留的独立面试不计入求职汇总。

`career_production.mjs` 验证已构建的前端资产。另取没有求职岗位的临时库，后端8019按前述方式启动，CORS允许5190；在已通过构建的前端目录运行 `npm.cmd run preview -- --host 127.0.0.1 --port 5190 --strictPort`，在项目根目录运行 `node scripts/acceptance/career_production.mjs`。脚本仅将浏览器本机XHR/fetch请求转至真实隔离后端，不修改编译产物或伪造接口响应。四项验证目录只读、确认保存与基础题真实判分、本地面试作答及对比快照、成长实际计数与原记录链接；要求JS错误和外部请求均为零。默认输出 `_working/v2-5-20261001/production`，沿用URL、浏览器渠道和输出目录环境变量。此项为本机预览，不执行发布或安装包更新。

## B2 岗位学习计划

`career_planning.mjs` 从没有求职岗位的隔离库开始，默认后端8020、前端5192。临时数据、数据库、上传、归档目录均指向 `_working/b2-career-plan-20261002/runtime`，身份模式local、面试local-only，CORS允许5192。前端设 `VITE_API_URL=http://127.0.0.1:8020` 后启动5192；在项目根目录执行 `node scripts/acceptance/career_planning.mjs`。输出默认 `_working/b2-career-plan-20261002/ui`。

十项检查覆盖：预览待评测/取消不写入、实际新作答使旧确认失效、已接受请求丢响应同指纹重试一次保存、现役学习页每日进度和实际CSV/ICS下载、撤销恢复保留进度、新答案另存计划、读取故障保留列表与重试、撤销岗位保留历史、375/768/1440列表与弹窗边界、计划进度参与删除确认并清除本岗位计划。网络故障明确注入；基础判题、SQLite、计划、导出和状态调用真实实现，无模型密钥或私人资料依赖。

编译产物复测使用构建目录的preview5193，API8020的CORS额外允许5193。每次仍从没有求职岗位的隔离库开始；设置 `FILEMATE_WEB_URL=http://127.0.0.1:5193`、`FILEMATE_API_URL=http://127.0.0.1:8020`、`FILEMATE_PRODUCTION_PROXY=1`、`FILEMATE_EVIDENCE_DIR=_working/b2-career-plan-20261002/production`，再执行同一脚本。仅本机XHR/fetch传输转到真实隔离API，编译JS/CSS资产原样加载，接口响应不伪造。不得并发运行这些写入流程脚本共享同一临时库。

## 完整托管备份恢复

运行`uv run python scripts/acceptance/backup_restore.py --out _working/<新演练目录>`，默认独立端口8032，先拒绝已占用端口。脚本仅使用原创合成资料，实际启动匿名HTTP服务和管理员CLI，覆盖三个库、正文/会话、原Cookie、跨访客隔离、重复确认与损坏拒绝。只停止自有进程，恢复前保留原合成数据并检查移动路径在新证据目录内；无私人库或线上写入，不调用外部模型。操作合同见[备份恢复手册](../../docs/BACKUP_RESTORE_RUNBOOK.md)。

## 实际HTTPS生产网关预检

先用`verify.ps1 -IsolateFrontend`生成带manifest的独立生产前端。另准备Caddy官方发行二进制并核对官方校验值、Node、curl、Playwright/Edge，以及V2.4公开图片合成夹具。运行：

```powershell
uv run python scripts/acceptance/gateway_preflight.py --caddy <已核验的Caddy绝对路径> --web-root _working/<完整前端验证副本> --out _working/<不存在的新目录>
```

默认端口8034/5202，先拒绝端口占用。工具使用实际`deploy/Caddyfile`，只改测试域名/回环绑定/上游/静态根，额外关闭配置自动保存和系统证书安装、TLS材料存至证据目录；启动生产匿名FastAPI、真实自签HTTPS与原样编译资产，不代理浏览器API也不伪造响应。自签校验忽略仅用于这个回环夹具，不改操作系统信任。临时文件和原创资料在新输出目录，只停止自有进程，不操作线上或私人库。

从现役Python路由提取91个路径，用GET的状态码/内容类型与真实上游比较，不能代替每个写接口的业务验收。28项浏览器检查包含22页、Monaco、CSP与375/768/1440布局；另4项检查真实本地Worker/WASM、录像和保存的观察样本，视频为公开图片合成流、麦克风明确拒绝。检查25 MiB文件拒绝、32 MiB已声明请求的Expect拒绝、不产生资料、身份隔离和预览认证；8个独立匿名客户端各16次读取，记录128次延迟及5秒p95门禁。该小型本机工作负载不包括模型、编译或上传容量，不代表真实服务器吞吐或SLA。

输出`summary.json`、`capacity.json`、各浏览器结果、截图、实际网关日志与前后源码指纹。视觉脚本的`FILEMATE_PRODUCTION_GATEWAY=1`启用直接同源模式；`FILEMATE_ACCEPTANCE_INSECURE_TLS=1`和临时Basic凭据只属于验收进程环境。正式网关不使用这些验收开关。完整事实与失败修复过程见[交付报告](../../docs/GATEWAY_PREFLIGHT_DELIVERY_2026-10-03.md)。

追加`--visual-checks`运行`visual_upgrade.mjs`：实际编译首页在375/768/1024/1440的字号/点击区/布局、主要导航和完整工具查找、方向切换、减弱动画、滚出暂停及SPA往返清理。追加`--review-checks`运行`file_review.mjs`：原创TXT通过真实浏览器上传，分类/命名/日程同屏预览、草稿/刷新、离开保护、归档字节与幂等、撤销及ICS下载、已有目标冲突。确认响应丢失和确认后读取失败为明确注入，业务执行和文件检查使用真实隔离服务；物理文件断言仅限本次`FILEMATE_DATA_DIR`内。每轮选新候选和输出目录，不覆盖早期失败或已验收证据。

追加`--workspace-checks`运行`workspace.mjs`：23项检查实际编译学习工作区的导入/会话、四类产物、阅读与按需创建、授权、原文引用、实际判题与错题、下载/恢复、输入/刷新保护及375/768/1024/1440布局。使用原创合成TXT与独立回环HTTP模型，通过现役适配器和真实SQLite保存；模型非法JSON、503和延迟明确注入，不代表真实模型质量或学习效果。`--fixture-port`默认8036，在需要归档或工作区专项时同样先拒绝占用。夹具要求一次性合成凭据，不记录原提示词或密钥；操作系统凭据后端仅在验收子进程中禁用，凭据来源实际断言。

基础网关先在无模型凭据环境下运行，归档/工作区写入专项再重启自有API接入合成合同夹具，不重启用户服务。现役`/process`初始化模型客户端，因此归档专项也需要此夹具；课程/日期通过实际草稿接口明确填写为合成值。它不声称无密钥文件分类可用，也不把夹具分类字段当准确率；无模型导入与阅读由独立`/knowledge/import`专项验证。最终同包45项父级、28页面、4本地视觉、10首页、17归档和23工作区结果见[工作区交付](../../docs/LEARNING_WORKSPACE_VISUAL_DELIVERY_2026-10-03.md)。

## P1完整账户复验

p1_full_product.mjs连接FILEMATE_WEB_URL/FILEMATE_API_URL，使用独立空白匿名部署和新FILEMATE_EVIDENCE_DIR。实际注册后在同账户执行22步；模型配置仅在后端验收子进程环境提供，浏览器不携带部署密钥，不替换响应。原生C++工具链须实际就绪。原生TTS独立记录，未完成保持CONDITIONAL/整体passed:false。所有账号、课程、岗位、回答均原创合成；私有下载/库只放_working，不提交。生产身份/限流/判题代理不同，不能直接把本机编译器结论当Linux公网验收。
