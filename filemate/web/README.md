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
