# FileMate v1.3.0-alpha.2 集成发布验收

基线：2026-10-02，`main` 的 `c916cd956c7ff527af633da4c86fb2458ae0cb92`（V2.5 合并后）。本阶段仅做 A5/B3 发布收口，不引入新的学习数据模型或修改已发布 migration。

## 用户影响

- V2.1 数字人讲解、V2.2 证据知识图谱、V2.3 Windows C++ 隔离练习、V2.4 本地面试复盘、V2.5 求职训练使用同一版本基线。
- 桌面和 Caddy 的 CSP 允许本地视觉模型所需的 WebAssembly 编译，但不开放 JavaScript `unsafe-eval`；录制回放与 Worker 资源有明确策略。
- 临时演示网关修复目标、可信与记忆 API 转发，WASM 返回正确 MIME，并统一添加安全响应头。
- 网关在前端目录更新期间返回可重试的 503，而不因缺失 index.html 退出；缺失模型/脚本资源返回 404，不返回 HTML 冒充资源。求职页保留一个主内容区域，修复嵌套 main 的辅助阅读歧义。
- 桌面 C++ 工具链副本放在应用数据目录的 `cpp-toolchain`，不再随 PyInstaller 临时解包目录消失。首次准备仍需本机已安装 MSVC 与 Windows SDK。
- Sidecar 验收校验精确版本、五模块接口、面试记录持久化、真实 PDF 导出和优雅退出。localhost 检查仅在验收进程内绕过代理，并在退出时恢复，不改系统设置。
- 安装包验收仅允许一次性 Windows CI/虚拟机，防止在开发者电脑误卸载已有安装；手工虚拟机运行需显式 `-IsolatedRunner`。

## 公共合同

没有 API、路由、schema 的破坏性变化。已有 `FILEMATE_CPP_TOOLCHAIN_DIR` 在桌面启动时被设置为持久应用目录；开发模式默认目录不变。Python、Node、Rust、Tauri 清单和锁文件同步为 alpha.2，没有升级依赖版本。

## 可复现验收

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
cd filemate/web
npm run desktop:sidecar
npm run desktop:smoke-sidecar
npm run desktop:bundle
```

浏览器回归使用真实生产构建、同源认证网关及独立 SQLite；不会给业务 API 安装模拟响应。`scripts/acceptance/browser_smoke.mjs` 检查 22 个页面的 1280px/390px 两种宽度与 18 个接口。网关凭据通过 `FILEMATE_ACCEPTANCE_GATEWAY_USER/PASSWORD` 提供；可用 `FILEMATE_BROWSER_CHANNEL=msedge` 选择已安装浏览器。证据写入 `FILEMATE_EVIDENCE_DIR`。

真实本地视觉验收使用公开静态人脸生成的合成视频和实际 MediaPipe CPU/Worker。正常路径和注入一次位图传输故障均已完成 4/4，0 JavaScript 错误；实际网关提供 CSP，不使用 API 路由拦截。这不是用户摄像头实验，不代表心理识别或真实面试评分有效性。

本机打包后端验证已通过：版本 alpha.2，五模块合同成功，面试作答保存成功，PDF 为 61,731 字节，优雅退出、端口释放和 Uvicorn shutdown 完成。部分 Windows 进程 API 不提供退出码；证据明确保留 `exit_code_available=false`，不编造退出码。最终证据文件：`_working/sidecar-alpha2-font-fixed-evidence.json`。

离线合成检索回归 41 案例：Recall@1 0.9756、Recall@3 1.0、MRR 0.9878；5 个模型不可用案例标记为本地降级而非已评分。SQLite 合成压力回归 10 线程、5,000 操作、0 错误。这些只支持工程回归，不支持真实教学效果结论。

## 发布门槛和限制

本地后端最终回归为 643 通过、18 跳过、5 个 e2e 未选择、3 项警告；发布合同专项 24/24，完整门禁日志为 `_working/verify-release-closeout.log`。真实生产构建本地浏览器回归为 44/44 页面检查（22 路由×两种宽度）、18/18 JSON API，0 控制台错误、0 横向溢出；页面证据在 `_working/integrated-browser-stable/browser-acceptance.json`。

前端 15/15 单元测试、Vue 类型检查和生产构建通过。浏览器验收必须给独立后端显式设置 `FILEMATE_CORS_ORIGINS` 为网关 Origin；被拒绝的 Origin 不以弱化安全校验来绕过。

Windows 干净环境验收已全部通过：[Actions 36971016770](https://github.com/cooooooosdas/Filemate/actions/runs/36971016770)，对应源码 `f455e8dd0b0702fe1a5c76acfc4ed5480eede1b8`；[PR #49](https://github.com/cooooooosdas/Filemate/pull/49) 已合并为 `main` 的 `f5307c44026f6bfd5ae3ae91aeb409d6de0ec5cd`，两者代码树一致。验证包含：安装、PATH 无 Python、应用启动、后端就绪、凭据安全存储、退出、Sidecar 停止、卸载和数据保留；不是跨版本升级验收。

首次 Windows CI 捕获干净环境 PDF 导出失败：未安装项目的隔离 PyInstaller 环境未收集到中文字体，尽管开发环境可导出。打包脚本补充显式 assets 目录后，真实 CI 中文 PDF 导出已通过。后续修复子 PowerShell 不可用的 `Get-FileHash` 为 .NET SHA-256，并关闭未使用且引发结束阶段失败的桌面 uv 缓存；最终流水线全绿，没有跳过运行/安装检查。

- 网站已部署 alpha.2；同源真实浏览器与本地验收分别记录，不将本地通过当成线上证据。
- Windows 编程执行须隔离自检成功；Linux 网站只能展示题库和不可用边界，不降级为不隔离执行。
- 账号界面仍为预览，不是真实登录/注册；网站继续匿名设备级分库。
- 真实学生试用、导师盲评和专家校准仍待评测（本次校准输入 0 个真实样本）。
- NSIS 未签名，SmartScreen 提示可能出现；跨版本升级与真实机器试用尚需独立证据。
- 前端部分块超过 500KB，依赖弃用警告未清零；当前没有把性能警告伪装为运行失败。

## 数据和回滚

安装程序、源代码同步与旧版本目录不得覆盖或删除用户数据库、上传、归档和身份密钥。旧的 Downloads v1.0 目录包含真实数据库，必须保留。部署前备份全部租户数据库、`identity.secret` 及受管上传/归档；SQLite 使用 backup API，并对独立备份执行 `integrity_check`。原发布目录与安装包保留，部署失败先切回已知可用代码，若迁移已执行则在停止写入后恢复对应全量备份。不得让旧代码继续写入新 schema 的数据库。

## 2026-10-02 实际部署与分发

服务器 44 个原数据库已在独立目录迁移演练到 v24，完整性与各原表行数检查通过。最终切换前全量备份保存在 `/var/backups/filemate/alpha2-20261002T060724Z`，身份密钥字节保持一致；旧发布和第一轮回滚备份仍保留。真实数据库和密钥不进入仓库、Downloads 或验收报告。

首轮切换发生短时 502：新运行环境由 root 创建且服务账户不可读；初版回滚复制又遗漏原 UID/GID，导致身份密钥不可读。已恢复原所有权，验证旧站恢复，再修复新环境服务组权限与回滚所有权清单后切换成功。保留 systemd 原安全策略，不通过放宽整个数据目录解决问题。

线上页面验收继续捕获两项配置问题：前端符号链接使用容器不可解析的宿主机绝对路径，页面 500；旧 `/interview` 前缀误代理 `/interview-vision`，模型资源 404。已分别修正为挂载目录内相对链接和独立静态资源 location，并启用公开脚本/WASM 压缩。Nginx 配置检查、模型 JS/WASM MIME 与资源缺失 404 均通过，原接口限流未降低。

真实线上视觉链路使用合成人脸画面、禁用麦克风、真实 CPU/Worker 推理完成 4/4，0 JavaScript 错误；自己创建的面试记录已预览确认删除。两组匿名客户端验收证明：原创建者可读，另一客户端读取和删除预览均 404；Cookie 为 Secure/HttpOnly，同样只清理自己的合成记录。这不是正式账户登录、真实摄像头或面试准确率研究。

修复静态路由与压缩后，真实 `https://filemate.asia` 全页面重验为 44/44、JSON API 18/18，0 控制台错误、0 横向溢出；证据为 `_working/public-browser-alpha2-r3/browser-acceptance.json`。首次冷加载超时和模型路由失败证据仍保留在早期 r1/r2 目录，不删失败记录、不用本地 mock 冒充线上通过。

本机分发遵从负责人选择：保留 `D:\FileMate-Project` 与原桌面联接为开发草稿；新版单独放在 Downloads 的 `FileMate_1.3.0-alpha.2`，新增桌面文件夹入口，不静默安装/卸载。旧数据库、旧版本和竞赛文书不动。交付目录包含经过上述干净环境验证的 EXE、干净 Git 源码、校验值和不含隐私的工程证据。

CI 安装包 `FileMate_1.3.0-alpha.2_x64-setup.exe` 为 76,685,134 字节，SHA-256：`571c002d41d91f38cc73799a44cf719ff50ed3fb5936c478747f930648d8b036`。安装包未签名；本机仅分发，不把日常电脑当一次性卸载测试环境。正式签名、跨版本升级、真实用户试用与专家校准仍是后续依赖。
