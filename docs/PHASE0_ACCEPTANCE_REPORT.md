# FileMate Phase 0 可信基础验收报告

更新时间：2026-08-13
目标版本：`v1.2 Reliable Foundation`
当前结论：**核心可信链路、前后端构建、Sidecar 与队友本地一键运行均已通过；Windows 安装包按产品决策延期到最终发布阶段。**

## 1. 验收矩阵

| 门禁 | 证明要求 | 当前证据 | 结论 |
|---|---|---|---|
| 数据迁移 | 空库和旧库均能升级到当前 schema | SQLite v1–v8 迁移测试 | ✅ 通过 |
| 可信确认 | 预览不写文件；确认后才归档 | confirmation executor 与 API 测试 | ✅ 通过 |
| 冲突与回滚 | 不覆盖同名文件；中途失败恢复原文件 | 冲突、失败回滚、幂等测试 | ✅ 通过 |
| 一键撤销 | 已归档文件和日历可恢复，重复撤销安全 | undo 单元与 API 集成测试 | ✅ 通过 |
| API 契约 | 错误统一为 `{success,data,error}` | FastAPI handler 与持久化测试 | ✅ 通过 |
| 完整后端回归 | 非 e2e 测试无失败 | `314 passed, 17 skipped, 5 deselected` | ✅ 通过 |
| 静态检查 | 安全关键路径 Ruff 无错误 | `All checks passed!` | ✅ 通过 |
| 前端生产构建 | TypeScript 与 Tauri 模式构建成功 | Vite 8.1.5，2274 modules | ✅ 通过 |
| Python Sidecar | 无源码解释器启动、SQLite 创建、优雅关闭、端口释放 | `scripts/smoke_sidecar.ps1` 机器可读证据 | ✅ 通过 |
| 队友本地运行 | 单命令启动双端、API/页面就绪、单命令停止 | `doctor.ps1` 全绿；API `1.2.0`；Web 200 且包含应用挂载点 | ✅ 通过 |
| Tauri Rust 主程序 | Cargo 编译成功 | 项目内 Rust 1.97.1 已验证；安装包构建按产品决策暂停 | ⏸ 最终发布阶段 |
| NSIS 与 MSI | 两种安装包均实际生成 | CI 与验收脚本已准备，当前不阻塞功能开发 | ⏸ 最终发布阶段 |
| 干净机安装/卸载 | 无 Python PATH 启动、卸载保留用户数据 | 验收脚本已实现，待正式发布候选版本执行 | ⏸ 最终发布阶段 |
| 可复现依赖 | Python、Node 有锁定输入与环境诊断 | `uv.lock`、npm lock、setup/doctor 脚本 | ✅ 当前开发门槛通过 |

## 2. 队友本地运行证据

- 环境：Python `3.12.13`、Node.js `24.15.0`
- 诊断：后端依赖、前端依赖、LLM 配置、8001/5173 端口全部通过
- 启动：`scripts/dev.ps1 -NoBrowser` 成功拉起 FastAPI 与 Vue
- 后端：`GET http://127.0.0.1:8001/` 返回版本 `1.2.0`
- 前端：`GET http://127.0.0.1:5173/` 返回 HTTP `200`，包含 `#app` 挂载点
- 停止：`scripts/stop-dev.ps1` 按记录 PID 正常停止双端进程

## 3. 已验证 Sidecar 产物

- 文件：`filemate-server-x86_64-pc-windows-msvc.exe`
- 大小：`46,008,582` bytes（约 43.88 MiB）
- SHA-256：`620DEB598C9C46C4051ACD0AE7EC09CF08726844FE3245B9BA43792415C935CA`
- Python：PyInstaller 6.22.0 + CPython 3.12.13
- 嵌入资源：分类规则、四份 Prompt、FastAPI/Uvicorn、文档解析器与 icalendar 运行数据
- 冒烟结果：API `1.2.0` 就绪、SQLite 创建成功、令牌关闭成功、Uvicorn 完成 shutdown、8001 端口释放

该 exe 是本机临时验收产物并被 Git 忽略；正式发布必须使用 Windows CI 从仓库源代码重新构建，并以 CI artifact 的哈希为准。

## 4. 可重复执行的验收命令

```powershell
# 完整后端回归
uv sync --extra dev
uv run pytest filemate/tests -q -m "not e2e"

# 前端生产构建
cd filemate/web
npm ci
npm run build -- --mode tauri

# 队友本地一键运行与停止
cd ../..
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
powershell -ExecutionPolicy Bypass -File scripts/stop-dev.ps1

# Sidecar 构建与运行冒烟
npm run desktop:sidecar
npm run desktop:smoke-sidecar

# Rust、前端、Sidecar 与安装包完整构建
npm run desktop:build

# 安装包验收（构建完成后）
../../scripts/smoke_windows_installer.ps1 `
  -BundleRoot ./src-tauri/target/release/bundle
```

## 5. 正式安装包发布判定规则

只有同时满足以下条件，README 才能出现正式桌面下载链接，并允许打 `v1.2.0` 发布标签：

1. GitHub Actions 的 backend、frontend、desktop 三个 job 全绿；
2. `FileMate-Windows-installers` 同时包含 `.msi` 与 `-setup.exe`；
3. `FileMate-desktop-acceptance-evidence` 中安装器验收 JSON 全部为 `true`；
4. 将首次成功构建生成的 `Cargo.lock` 纳入版本控制并再次构建；
5. 至少一台非 CI Windows 11 机器完成中文路径、无 Python、安装/卸载人工复核；
6. 未签名开发包必须明确显示测试版提示，竞赛现场使用的包需提前处理 SmartScreen 风险。

上述安装包证据不再阻塞 Phase 1 功能开发；但在证据齐全前，README 不提供正式桌面下载链接，也不把开发构建描述成可发布安装包。
