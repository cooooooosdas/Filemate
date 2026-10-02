# FileMate Web 与桌面端

本目录包含 Vue 3 前端和 Tauri 2 Windows 桌面宿主。alpha.2 安装包已有一次性 Windows CI 验收；开发草稿和真实数据不得作为静默卸载测试对象。

## Web 开发

```powershell
npm ci
npm run dev
```

另开一个终端，在仓库根目录运行 `uv run filemate-server`。浏览器开发环境通过 Vite 代理访问后端。

Windows 用户推荐直接从仓库根目录执行；命令会检查环境、启动 FastAPI 与 Vue，并打开操作页面：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
```

首次安装完成后，后续启动可省略 `-Setup`：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

页面地址为 `http://127.0.0.1:5173`，后端接口文档为 `http://127.0.0.1:8001/docs`。若页面顶部显示“本地服务尚未连接”，先运行上述启动命令，再点击“重新检查”。

## 页面可访问性验收

`npm test` 包含设计令牌对比度回归；它不能代替真实浏览器和读屏验收。浏览器脚本单独运行，连接隔离 API，禁止使用真实用户库作为夹具：

```powershell
# 仓库根目录，先用 _working 内的新库启动 8019 后端
# 生产构建在 5189 preview；不得让默认代理读到已有的 8001 服务
npm.cmd install --prefix _working/a11y-tools --no-audit --no-fund axe-core@4.13.0 playwright@1.62.1
$env:FILEMATE_WEB_URL='http://127.0.0.1:5189'
$env:FILEMATE_API_URL='http://127.0.0.1:8019'
node filemate/web/tests/accessibility.browser.mjs
```

脚本将相对 API 请求转发到显式指定的真实隔离后端，不 Stub 返回数据；静态资源仍来自生产构建。对网站直接验收时，两地址设为同一 HTTPS 地址，并设 `FILEMATE_ROUTE_SETTLE_MS=5000` 避免触发网关限流。Windows 默认 Edge，其他平台需预先安装 Playwright Chromium；可用 `FILEMATE_BROWSER_CHANNEL` 指定渠道。

优先使用 `scripts/demo_gateway.mjs` 的真实同源网关连接隔离 API 和生产构建，两地址均设为网关地址。网关启用 Basic Auth 时，通过环境变量成对提供 `FILEMATE_ACCEPTANCE_GATEWAY_USER` / `FILEMATE_ACCEPTANCE_GATEWAY_PASSWORD`；凭据不写入证据或仓库。此方式不启用请求转发，可复核实际 CSP 与浏览器 HTTP 行为。

覆盖 22 条路由的 375/768/1280 px 默认页面、控制台、主内容与横向溢出；另外验证手机导航模态/焦点循环/同页导航/宽度切换、表单错误焦点、题库编辑弹窗、设置/查找弹窗、跳过导航和减少动画。任何失败返回非零退出码。JSON 与截图只写入 `_working/a4-accessibility`，`FILEMATE_EVIDENCE_DIR` 可选本项目 `_working` 内的新目录。不会放宽部署 CSP，也不会保存账号、创建题目或调用模型。

以下为源码状态盘点，不代表每个加载/错误/成功分支均已做本轮浏览器故障注入；本轮自动扫描主要覆盖空/默认页面及上述瞬态表面。模型、归档和持久化成功流程另见 `scripts/acceptance/README.md` 的专项验收。

| 路由 | 默认/空状态 | 加载与错误恢复入口 |
| --- | --- | --- |
| `/` | 零记录、下一步导入 | 概览加载、错误重试 |
| `/today` | 空学习队列 | 汇总提示、重试/刷新队列 |
| `/import` | 选择文件入口 | 上传进度、逐项/全部重试 |
| `/classification` | 未选择资料 | DataState 加载、读取重试 |
| `/naming` | 未选择资料 | DataState 加载、读取重试 |
| `/schedule` | 未选择资料/无日程 | 读取重试、导出失败提示 |
| `/history` | 空处理记录 | 表格加载、DataState 重试 |
| `/ai-tools` | 无资料工作区 | 资料/会话加载、重新读取与生成重试 |
| `/study-plan` | 未生成计划 | 生成禁用态、错误重试 |
| `/wrongbook` | 无待复习题 | 读取提示、重试/刷新 |
| `/interview` | 未开始训练 | 创建/作答禁用态、错误与重试 |
| `/interview-bank` | 内置题库、空筛选 | DataState 加载/重试、保存禁用态 |
| `/growth` | 零样本、待评测 | 汇总提示、DataState 重试 |
| `/knowledge` | 空知识库 | 读取提示、DataState 重试 |
| `/digital-human` | 空讲解/播放记录 | 播放状态、失败重试、记录同步重试 |
| `/knowledge-graph` | 空图谱与提取历史 | 读取/操作提示、刷新与重新提取 |
| `/programming` | 内置原创题、无提交 | 环境状态、操作禁用态、刷新记录 |
| `/career` | 岗位目录、无训练 | 读取/操作提示、刷新记录 |
| `/goals` | 无目标 | 读取提示、DataState 重试、生成禁用态 |
| `/trust` | 空授权/执行记录 | 读取提示、DataState 重试 |
| `/login` | 账号服务未接入的界面预览 | 字段错误定位；无真实登录加载状态 |
| `/register` | 账号服务未接入的界面预览 | 字段错误定位；不会创建账号 |

axe-core 的自动规则通过仅代表本次可自动检测的表面；JSON 中 `manual_review` 仍需人工检查，不构成完整 WCAG 合规认证、真人可用性实验或供应商模型质量结论。

## 桌面开发与打包（最终发布阶段）

先安装 Node.js 24、uv、Rust stable MSVC 工具链以及 Visual Studio C++ Build Tools，然后执行：

```powershell
npm ci
npm run desktop:dev
npm run desktop:build
```

`desktop:dev` 和 `desktop:build` 会先调用 `../../scripts/build_sidecar.ps1`，使用 `requirements-desktop.txt` 的最小运行时依赖生成与当前 Windows 架构匹配的 `src-tauri/binaries/filemate-server-*.exe`。Prompt 和分类规则会作为资源一并打包。安装包输出到 `src-tauri/target/release/bundle/`。

桌面应用启动时会：

1. 在应用数据目录创建 SQLite、上传缓存和运行数据；
2. 在用户“文档/FileMate”下保存确认归档的学习资料；
3. 自动启动本机 `127.0.0.1:8001` 后端，固定本地身份、非生产模式及 Host/CORS 白名单，不继承网站环境配置；
4. 退出时先请求后端优雅关闭，再执行进程兜底清理。

发布构建仅允许 `tauri://localhost`、`http://tauri.localhost`、`https://tauri.localhost`；debug 构建额外允许 Vite 的 `http://localhost:5173` 和 `http://127.0.0.1:5173`。这些约束不改变直接启动 Python API 的网站配置，也不覆盖 LLM 凭据、功能开关和外发同意设置。

手动触发 `FileMate CI` 时，Windows runner 先验证 Sidecar，再构建 NSIS，最后执行静默安装、隔离 Python PATH、父进程环境污染场景、桌面退出、静默卸载和数据文件保留检查。出现已有 FileMate 数据目录时拒绝开始安装；失败证据明确记录 `passed=false` 和阶段。正式提供新构建下载前必须通过，不能把数据库文件存在当作跨版本资料内容已完整保留。
