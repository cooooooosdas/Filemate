# FileMate Web 与桌面端

本目录包含 Vue 3 前端和 Tauri 2 Windows 桌面宿主。当前优先支持队友本地开发运行；桌面版工程会继续保留，待产品功能稳定后再进行安装包发布验收。

## Web 开发

```powershell
npm ci
npm run dev
```

另开一个终端，在仓库根目录运行 `uv run filemate-server`。浏览器开发环境通过 Vite 代理访问后端。

Windows 用户也可以直接从仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
```

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
3. 自动启动本机 `127.0.0.1:8001` 后端；
4. 退出时先请求后端优雅关闭，再执行进程兜底清理。

正式发布前，CI 会在 Windows runner 上先验证 sidecar 的启动、SQLite 创建与优雅关闭，再构建 NSIS/MSI，最后执行静默安装、隔离 Python PATH 启动、桌面退出、静默卸载和用户数据保留测试。该门禁不再阻塞当前功能开发，但正式提供安装包下载前仍必须通过。
