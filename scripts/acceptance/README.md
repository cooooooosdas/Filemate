# FileMate 自动化验收脚本

本目录存放由产品/评测侧维护的可复现验收脚本，不修改 `server.py`、`storage.py`、`api.ts` 等高冲突文件。

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

本机已有Vite运行时，全量校验可执行 `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend`。后端照常检查，前端复制到新建的 `_working/verify-web-*` 后执行npm ci/test/build，避免Windows原生依赖文件锁影响现有服务；无此参数时命令行为保持原样。副本是临时验证证据，不提交。
