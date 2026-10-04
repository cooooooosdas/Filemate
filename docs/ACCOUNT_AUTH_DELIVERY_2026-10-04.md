# 邮箱账号与恢复码交付 — 2026-10-04

2026-10-04后续用户修订：新密码已改为9–128字符、字母和数字混合，旧密码登录兼容；见[密码规则交付](PASSWORD_POLICY_2026-10-04.md)。以下15字符与NIST引用属于首次账号发布的历史规则，不是现役规则。

用户选择先完成邮箱＋密码、恢复码找回的可用版本。alpha.4 / schema v25 已推送主分支并上线，实现真实注册、登录、保持登录、退出和恢复密码。2026-10-04首次账号发布提交为 `6d4e0c73bd6ec5fddf7643f2191277ae10a69b25`；后续接口修复和当前运行提交见[实际API复核](API_CONNECTIVITY_AUDIT_2026-10-04.md)及站点 `/release.json`。

## 用户流程

- `/register`：昵称、邮箱、15–128字符口令，选择保留当前游客资料；注册后显示一次恢复码，可复制或下载，确认保存再进入学习空间。
- `/login`：登录后使用该账号资料空间；保持登录30天，不勾选时服务器会话最长12小时。换设备仍可访问原账号资料。
- 顶栏“我的账号”：显示昵称和邮箱，退出只撤销当前设备；过期会话提示重新登录或明确退出后使用游客空间。
- `/recover`：邮箱＋保存的恢复码＋新密码；旧恢复码立即失效，所有设备退出，再显示新恢复码并返回登录。

邮箱暂不验证归属，不能当作已验证联系地址。密码和恢复码一起丢失时，当前版本没有邮件或人工找回流程。恢复码具有重设密码的权限，必须私密保存；前端不持久化密码、恢复码或会话秘密。

## 合同与实现

`filemate/accounts.py` 负责 scrypt密码派生、原子账号归属、服务端会话和恢复码轮换。SQLite迁移仅追加v25，原v1–v24及业务资料目录不改写。注册保留资料时绑定当前游客目录；绑定后的旧游客Cookie不能再访问该空间。现役租户路由按有效账号会话选择目录，全部业务资源继续共享该归属合同。过期/撤销会话返回401，防止失败会话把写入悄悄落到新游客库。

新增 `/api/auth/me|register|login|logout|recover`，共享类型和API调用统一在前端规定目录。生产会话Cookie为HttpOnly/Secure/SameSite=Lax，无令牌进入JavaScript。写入要求JSON、自定义头及Origin白名单；按邮箱持久限制尝试次数，Nginx另按IP限制认证动作。

采用 [OWASP密码存储建议](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) 中32MiB的scrypt配置，并按 [NIST密码规则](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/) 使用至少15字符的单因素密码长度；这不等于整体通过NIST合规认证。

部署工具改为验证完整旧迁移及SQL未变，仅允许末尾追加迁移。上线前完整备份和恢复演练包括主库、身份签名秘密、所有用户分库和托管资料。开放账号写入后不得回退至游客版alpha.3；回退代码必须保留v25及账号归属检查，禁止用旧快照覆盖新数据。

## 当前工程证据

- `filemate/tests/test_accounts.py`：9项专项通过，涵盖资料归属、跨设备、退出、撤销会话、旧恢复码失效、并发单次使用、CSRF、尝试限额、秘密摘要和可用备份。
- `_working/account-auth/verify-release.log`：账号发布快照的Windows全量793通过、19跳过、5排除；Ruff、33前端行为测试、Vue类型、构建和体积门禁通过。跳过原因包括现役可选OCR/外部真实文档及Linux部署工具，未把失败改为跳过。后续图谱补丁的全量结果独立记录在API复核中，不相加。
- [账号发布Linux CI](https://github.com/cooooooosdas/Filemate/actions/runs/37146838089)：802后端通过、18跳过、5排除；33前端、构建、Python打包及合成评测流程通过。Windows安装包任务只在手动触发时执行，本轮未生成新安装包。
- `_working/account-auth/gateway-release/summary.json`：账号发布对应编译包的实际TLS网关47组/96路径、72无障碍检查通过；另有17归档、25学习工作区、18知识布局及12视觉检查。源码指纹在检查期间一致，模型来自明确的合成HTTP夹具，此项不是公网模型质量研究。
- `scripts/acceptance/accounts.mjs` 与 `_working/account-auth/live-accounts/summary.json`：公网12组真实UI操作通过，包含注册/登录/找回/恢复码四页面状态在375/768/1024/1440px的16个布局/无障碍组合。验证了Secure/HttpOnly/SameSite Cookie、游客资料绑定、旧游客隔离、跨设备、退出、全设备恢复撤销、旧密码/旧码拒绝、新密码取回资料与确认删除。修复表单错误焦点及无障碍关联；截图隐藏恢复码，临时下载已清理。
- `_working/account-auth/live-routes/summary.json`：公网23页面、9读取接口通过，无JS异常或横向溢出。上述用例仅创建原创合成账号与资料，不读取或修改真实用户资料。

首次部署完整备份与新目录恢复演练通过：`/var/backups/filemate/alpha4-6d4e0c73-20261003T191656Z`，90数据库/103文件，包含旧分库及当前主库、身份秘密与权限。备份不提交Git。运行包为 `alpha4-6d4e0c73`，后端SHA256 `3f7f04c28aea796808f8da3975052557e34c37beb2dca578b73a509dc0d8ac1c`，前端SHA256 `de17843ca6e5c611d950d9565718c95afcf65cf7bdbba8c0f2b3f98a349d236c`；源码和前端76源文件/99编译文件一致，网关保留旧哈希资源供已打开页面使用。后续每次发布重新备份，不能以此旧快照覆盖新账号写入。

真实学生学习效果数据尚未采集。工程验收证明当前账号操作和资料隔离可用，不能代替真人学习效果实验。

图谱补丁发布 `f0b92ba1` 后再次执行 `_working/account-auth/live-accounts-final/summary.json`：同12组公网账号流程、16个布局/无障碍组合及零JS异常通过；当前实际运行提交、98库完整备份和API结果见[API复核](API_CONNECTIVITY_AUDIT_2026-10-04.md)。
