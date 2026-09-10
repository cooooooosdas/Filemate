# FileMate 网站部署与桌面端交付方案

## 1. 当前交付边界

FileMate 采用同一套 Vue 3 前端和 FastAPI 业务接口，按两阶段交付：

1. **网站端先上线**：`filemate.asia` 作为公开竞赛体验环境，用脱敏或公开资料验证稳定性与核心流程；不得上传敏感或未经授权的资料。
2. **Windows 桌面端后交付**：网站功能冻结后，用现有 Tauri 2 壳打包为 NSIS `.exe` 安装程序；桌面端继续复用相同页面与 API 合同。

移动端不在当前范围内。网站与桌面端保持同样的任务入口、结果页和数据模型，但底层文件能力有所不同：网站端使用上传、下载和服务器工作区；桌面端通过本机 sidecar 访问用户明确选择的文件。浏览器安全模型不允许网页静默读写任意本地目录，因此不能把两者实现为完全相同的文件通道。

> 当前 SQLite 数据模型适合单机或小团队私有 Alpha，不适合直接开放匿名注册。公开多用户版本必须先补账户体系、租户隔离、对象存储、配额、限流、审计和备份恢复演练。

当前公开体验站只用于产品展示，已启用 HTTPS、Host/CORS 白名单、接口限流、上传体积限制、安全响应头，并关闭公网模型密钥设置、内部关停接口和 API 文档。以上措施减少暴露面，但不能替代账户体系和租户隔离。

### 1.1 三天冲刺：无服务器临时上线

在服务器和备案尚未完成时，可用 Cloudflare Quick Tunnel 发布受密码保护的演示站：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_quick_tunnel.ps1
```

脚本会完成以下操作：

- 使用现有 Vue 生产构建，不暴露 Vite 开发服务器。
- 在 `127.0.0.1:8010` 启动独立 FastAPI 演示后端。
- 将数据库、上传和归档放在 `_working/quick-tunnel/data`，不读取正式 `.filemate-data`。
- 在 `127.0.0.1:8080` 启动带 HTTP Basic Auth 的静态站点/API 网关。
- 下载 Cloudflare 官方 `cloudflared`，获得随机 `https://*.trycloudflare.com` 地址。
- 限制单次请求体为 64 MB，并阻止公网访问 `/internal/shutdown`。

访问凭据保存在本机忽略目录 `_working/quick-tunnel/credentials.json`，不得提交仓库或发到公开渠道。停止命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_quick_tunnel.ps1
```

这是答辩和小范围内测方案，不是生产托管：Cloudflare 不保证 Quick Tunnel 的 SLA，进程重启后随机网址会变化，且电脑必须保持开机、联网和禁止睡眠。正式域名可在 Cloudflare Zero Trust 中创建 Named Tunnel，将 `demo.<域名>` 指向 `http://127.0.0.1:8080`；域名购买、Cloudflare 登录和 DNS Nameserver 修改需要负责人亲自完成。

操作入口：

- [腾讯云域名注册](https://cloud.tencent.com/product/domain)
- [Cloudflare 免费账号注册](https://dash.cloudflare.com/sign-up)
- [Cloudflare Quick Tunnel 官方说明](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)

## 2. 推荐服务器

### 首选：腾讯云轻量应用服务器（中国大陆）

- Ubuntu 24.04 LTS
- 2 核 CPU、4 GB 内存
- 90–100 GB SSD
- 6–7 Mbps 带宽，月流量 800–1000 GB
- 适用阶段：私有 Alpha、答辩演示、几十名受控测试用户
- 官方标准价格参考：约 80–90 元/月；活动价和地域库存以购买页为准

选择大陆节点便于后续正式面向国内用户，但域名必须完成 ICP 备案后才能对外提供网站服务。用于腾讯云备案的大陆资源通常需包月购买满 3 个月、剩余有效期不少于 1 个月，并具备公网 IP/带宽。建议为报销一次购买 1 年，并保留订单、发票和合同。

### 临时快速演示：香港轻量服务器

香港节点可不等待 ICP 备案就部署域名，但中国大陆访问延迟和稳定性通常弱于大陆节点，而且香港资源不能用于大陆 ICP 备案。它适合短期私密演示，不建议作为最终国内生产节点。

### 何时升级

- OCR、Embedding 或本地模型改为服务器运行：升级到 4 核 8 GB 起。
- 开放多用户注册：将 SQLite 迁移到 PostgreSQL，上传文件迁移到 COS，并为每位用户建立数据隔离和配额。
- 日活或文件量明显上升：把 Web、API、数据库和对象存储拆分，并接入监控告警。

官方参考：

- [腾讯云轻量应用服务器价格调整说明](https://cloud.tencent.com/document/product/1207/119345)
- [腾讯云 ICP 备案快速入门](https://cloud.tencent.com/document/product/243/39038)
- [可用于备案的云服务资源要求](https://cloud.tencent.com/document/product/243/18908)
- [大陆与境外服务器备案说明](https://cloud.tencent.com/document/faq/243/43878)
- [Docker Compose `env_file` 规范](https://docs.docker.com/reference/compose-file/services/#env_file)
- [Caddy `basic_auth` 规范](https://caddyserver.com/docs/caddyfile/directives/basic_auth)

## 3. 上线前由负责人准备

购买和运营选择由项目负责人完成。部署执行前需提供：

- 服务器公网 IP、SSH 用户和密钥登录方式
- 已购买域名及 DNS 控制台权限，或配合添加 A 记录
- 选择的地域、服务器配置与系统版本
- 大陆节点的 ICP 备案状态；未完成时只进行内网/IP 验收，不开放域名业务
- 若采用私有 Alpha，准备访问用户名和强密码；公开竞赛体验站不启用共享预览密码
- 模型供应商、模型名、Base URL 与服务器端 API Key

不要在聊天群、截图、仓库或会议纪要中发送服务器密码和 API Key。优先使用 SSH 密钥，敏感配置只写入服务器的 `deploy/.env.production`。

模型统一使用 DeepSeek V4 Flash。先在 <https://platform.deepseek.com/api_keys> 创建密钥并确认账户余额，再在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/configure_deepseek.ps1
```

脚本以安全输入方式更新 `.env`，不会把密钥打印到终端。

## 4. 服务器部署

### 4.1 基础环境

在云防火墙/安全组中仅开放：

- TCP 22：SSH，最好限制为管理员固定 IP
- TCP 80：HTTP，用于跳转和证书签发
- TCP/UDP 443：HTTPS 与 HTTP/3

安装 Git、Docker Engine 和 Docker Compose 插件。将仓库克隆到服务器后进入 `deploy` 目录：

```bash
cp .env.production.example .env.production
docker run -it --rm caddy:2-alpine caddy hash-password
```

命令会交互读取密码，避免明文进入 Shell 历史。编辑 `.env.production`，写入真实域名和生成的密码哈希，并用单引号包住完整哈希，例如 `FILEMATE_BASIC_PASSWORD_HASH='$2a$…'`；Compose 对单引号值不做变量插值。随后在 DNS 控制台将域名 A 记录指向服务器公网 IP。

### 4.2 启动

```bash
docker compose --env-file .env.production up -d --build
docker compose ps
docker compose logs --tail=100 api web
```

Caddy 会在域名解析生效且 80/443 端口可达后自动申请和续签 HTTPS 证书。检查：

```bash
curl -u '用户名:密码' https://你的域名/api/health
```

期望返回 `success: true`。随后人工验证访问认证、文件上传、处理、知识库、问答、错题本、面试题库和数据导出流程。

### 4.3 更新与回滚

更新前先备份数据，再拉取已验证版本：

```bash
docker compose exec -T api python -c "import sqlite3; src=sqlite3.connect('/data/filemate.db'); dst=sqlite3.connect('/data/filemate-backup.db'); src.backup(dst); dst.close(); src.close()"
git pull --ff-only
docker compose --env-file .env.production up -d --build
```

生产更新必须使用 Git tag 或明确 commit，不直接部署未测试的开发分支。若新版本异常，切回上一个已知正常 tag，恢复备份后重新构建。

## 5. 数据、备份与安全

- `filemate_data` Docker 卷包含 SQLite、上传目录和归档目录；删除容器不会删除该卷。
- 每天执行 SQLite 在线备份，并把备份同步到另一存储位置；至少保留 7 个每日版本和 4 个每周版本。
- 每月执行一次“从备份恢复到临时实例”的演练，仅有备份文件但未验证恢复不算完成。
- 全站启用 HTTPS；私有 Alpha 使用共享密码，公开竞赛体验站展示数据使用脱敏或公开资料；不得公开 API 端口 8001。
- 生产环境显式配置 `FILEMATE_ENV=production`、`FILEMATE_ALLOWED_HOSTS` 与 `FILEMATE_CORS_ORIGINS`，关闭 API 文档和公网设置接口。
- 网关限制并发、请求频率和请求体大小，设置 CSP、点击劫持、MIME 嗅探与权限策略响应头。
- 不上传真实隐私资料作为演示数据；日志中不得记录文档全文、密码或模型 API Key。
- 上线后观察磁盘、内存、5xx、接口响应时间和模型调用失败率。

## 6. 从私有 Alpha 到公开产品的门槛

以下事项完成前，不开放匿名注册或公开传播：

1. 用户登录、找回密码、会话失效和管理员停用机制。
2. 所有业务表增加用户/租户归属，并通过后端强制校验，防止越权读取。
3. 上传类型、大小、数量限制；恶意文件隔离；下载授权。
4. API 限流、模型调用额度和成本上限。
5. PostgreSQL、对象存储、自动备份与恢复演练。
6. 隐私政策、用户协议、数据删除流程和 ICP/公安备案要求确认。
7. 错误监控、运行指标、告警联系人和故障应急手册。

## 7. Windows 桌面端路线

网站端稳定并冻结 API 后执行：

1. 运行 `npm run desktop:sidecar`，用 PyInstaller 生成 FastAPI sidecar。
2. 运行 `npm run desktop:smoke-sidecar`，验证 sidecar 启动、健康检查和退出。
3. 运行 `npm run desktop:bundle`，由 Tauri 生成 NSIS `.exe` 安装包。Alpha 版本号含文字预发布标识，不生成受 MSI 数字版本约束的产物。
4. 在干净 Windows 10/11 虚拟机执行安装、升级、卸载和数据保留测试。
5. 补代码签名证书，降低 SmartScreen 警告；发布安装包 SHA-256 校验值。

桌面端默认只监听 `127.0.0.1:8001`，数据存放在系统应用数据目录，不向局域网暴露。网站部署通过 `FILEMATE_HOST=0.0.0.0` 在容器内部监听，只有 Caddy 能从公网转发访问。

## 8. 发布验收清单

- 后端测试、Vue 类型检查与生产构建全部通过
- 真实浏览器逐页验收，无控制台错误和关键接口 5xx
- HTTPS、访问边界（公开体验或私有密码）、健康检查和自动重启有效
- 上传/下载、处理、知识库、学习记录和面试题库流程可复现
- 数据卷持久化，备份和恢复演练成功
- 页面在常用桌面分辨率下无横向溢出
- 桌面安装包可在无开发环境的干净 Windows 机器一键安装运行
- 网站与桌面端的功能矩阵逐项一致；实现差异有明确说明
