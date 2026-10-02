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

本机打包后端验证已通过：版本 alpha.2，五模块合同成功，面试作答保存成功，PDF 为 61,731 字节，优雅退出、端口释放和 Uvicorn shutdown 完成。部分 Windows 进程 API 不提供退出码；证据明确保留 `exit_code_available=false`，不编造退出码。证据文件：`_working/sidecar-integrated-evidence.json`。

离线合成检索回归 41 案例：Recall@1 0.9756、Recall@3 1.0、MRR 0.9878；5 个模型不可用案例标记为本地降级而非已评分。SQLite 合成压力回归 10 线程、5,000 操作、0 错误。这些只支持工程回归，不支持真实教学效果结论。

## 发布门槛和限制

本地后端最终回归为 639 通过、18 跳过、5 个 e2e 未选择、3 项警告；发布合同专项 20/20。真实生产构建浏览器回归为 44/44 页面检查（22 路由×两种宽度）、18/18 JSON API，0 控制台错误、0 横向溢出。完整门禁日志在 `_working/verify-release-final.log`；页面证据在 `_working/integrated-browser-stable/browser-acceptance.json`。

前端 15/15 单元测试、Vue 类型检查和生产构建通过。浏览器验收必须给独立后端显式设置 `FILEMATE_CORS_ORIGINS` 为网关 Origin；被拒绝的 Origin 不以弱化安全校验来绕过。

Windows CI 安装/运行/卸载验证、跨版本升级、网站切换及本机分发尚不能宣布全部完成。最终状态以同一提交的 CI 和实际部署证据为准。

- 网站在本轮检查时正常运行，但返回 alpha.1；不得仅凭源码或新安装包宣称网站已升级。
- Windows 编程执行须隔离自检成功；Linux 网站只能展示题库和不可用边界，不降级为不隔离执行。
- 账号界面仍为预览，不是真实登录/注册；网站继续匿名设备级分库。
- 真实学生试用、导师盲评和专家校准仍待评测（本次校准输入 0 个真实样本）。
- NSIS 未签名，SmartScreen 提示可能出现；跨版本升级与真实机器试用尚需独立证据。
- 前端部分块超过 500KB，依赖弃用警告未清零；当前没有把性能警告伪装为运行失败。

## 数据和回滚

安装程序、源代码同步与旧版本目录不得覆盖或删除用户数据库、上传、归档和身份密钥。旧的 Downloads v1.0 目录包含真实数据库，必须保留。部署前备份全部租户数据库、`identity.secret` 及受管上传/归档；SQLite 使用 backup API，并对独立备份执行 `integrity_check`。原发布目录与安装包保留，部署失败先切回已知可用代码，若迁移已执行则在停止写入后恢复对应全量备份。不得让旧代码继续写入新 schema 的数据库。
