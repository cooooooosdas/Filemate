# FileMate Tauri Desktop

该目录是完整的 Tauri v2 Rust 宿主。桌面程序启动时会自动运行 PyInstaller 打包的 FastAPI Sidecar，前端通过 `http://127.0.0.1:8001` 访问本机 API。

## 环境要求

- Node.js 24
- Rust stable-msvc（最低 1.77.2）
- uv 与 Python 3.10–3.12
- Windows WebView2；生成 MSI 还需要 Tauri 对应的 Windows 打包依赖

## 构建

在 `filemate/web` 下执行：

```powershell
npm ci
npm run desktop:build
```

该命令先运行 `scripts/build_sidecar.ps1`，生成带 Rust target triple 后缀的 Python Sidecar，再执行 `tauri build`。开发模式使用：

```powershell
npm run desktop:dev
```

## 运行数据

- SQLite、待确认 Inbox：系统应用数据目录中的 FileMate 目录。
- 已确认归档：用户“文档/FileMate”目录。
- API Key：从启动进程的环境变量或后续设置模块读取，不写入安装包。

退出桌面程序时，Rust 宿主向仅监听回环地址的后端发送一次性令牌关闭请求；随后终止 Sidecar 作为兜底，防止后台残留。
