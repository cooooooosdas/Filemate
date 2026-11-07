# 生产部署与 D／试行开关启用清单（2026-11-07）

**状态：用户已给出 D 阶段验收确认；本轮未执行生产部署，生产开关仍全部关闭。** 本文档记录真实阻塞、可复用的启用配置与逐步执行清单，供在具备服务器凭据时按原子发布流程执行。**不要将本文当作已上线回执。**

## 为什么本轮没有真的部署

| 阻塞 | 实测事实 |
|---|---|
| 部署脚本须在服务器本机 root 执行 | `scripts/deploy_existing.py` 断言 `os.geteuid() == 0`，且读写 `/opt/filemate/current/.env.production`、`/var/backups/filemate`、systemd unit、nginx 配置；Windows 开发机无法满足。 |
| 无生产主机与凭据配置 | `~/.ssh/config` 只配置 `github.com`；仓库内无 `.env.production`（仅 `.env.production.example`）；无目标主机别名、无 release 上传通道。 |
| 公网当前不可达 | `https://filemate.asia/api/health` 在本机网络下无响应，无法做部署前后健康对比。 |
| 无真实供应商密钥 | 6 个常见模型密钥环境变量均为 unset；`LLM_API_KEY` 模板为空。既有 2026-11-06 一次真实调用（`deepseek-v4-flash`）结果为 `invalid_output` / `rule_fallback`、`passed=false`。开启依赖模型的教练能力前必须配置密钥、重跑真实调用并记录 usage。 |

按项目规则「文件操作先预览确认；失败可回滚」，在没有健康基线、备份快照与回滚路径的情况下静默覆盖生产属于高风险不可逆操作，不应由本地会话代做。

## 已确认的验收状态

- 用户于 2026-11-07 明确给出 D 阶段验收确认，D 工程验收候选可由 CONDITIONAL PASS 转为**用户已验收**。
- 这不等于部署完成、不等于开关已开、不等于 E 级真人实验已完成；三者各有独立边界。
- 线上 Web 仍为 `185f7b3`、API 为 `fdf6f40`；业务 schema 36、治理 3。本轮交付源码 `86b8774`（实现 `9ffe47d`）尚未上线。

## 待启用的开关（生产默认值仍为关闭）

后端（`deploy/.env.production`，需在服务器上修改，密钥不得入库）：

```ini
FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=1
FILEMATE_ENABLE_LEARNING_COACH=1
FILEMATE_ENABLE_TRIAL_WORKSPACE=1
VITE_ENABLE_LEARNING_COACH=true
VITE_ENABLE_TRIAL_WORKSPACE=true
```

前端 `VITE_*` 为构建期变量，必须与新 Web 产物同批构建；`FILEMATE_ENABLE_COURSE_GRAPH` / `VITE_ENABLE_COURSE_GRAPH` 保持既有值，不在本次变更范围。

同时确认：`FILEMATE_ENV=production`、`FILEMATE_ALLOWED_HOSTS` 与 `FILEMATE_CORS_ORIGINS` 使用真实域名、`FILEMATE_BASIC_PASSWORD_HASH` 为真实哈希、`LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` 按授权配置。

## 合成夹具内的开关验证（本轮已真实执行，非生产）

在独占回环合成夹具中开启上述开关后，真实 Edge 156 验证：

- `/api/trial/capabilities` 返回 `enabled=true`；教练 capabilities 返回 `enabled=true`，供应商调用被阻断。
- 完整闭环通过：选目标 → 读取范围 → 本周复盘 → 核对并保存 → 「复盘已保存」 → 「带着复盘请教教练」 → 教练问题框确实包含复盘正文。
- 关闭开关的对照夹具中 `/today` 正常加载且复盘入口不出现，原主流程未受影响。
- 320/390/1024/1440px 均无横向溢出，正文 17px；四主题表面可应用；键盘 Tab 可达；关闭复盘后焦点回到「本周复盘」触发按钮。
- 证据：`_working/final-trial-20261106/edge-matrix-evidence.json`、`edge-flow2-evidence.json`、`edge-fault-evidence.json`。

## 生产执行清单（在服务器上按顺序执行）

1. **前置**：确认当前线上版本与健康基线；`GET https://filemate.asia/api/health`，记录版本与 schema。
2. **备份**：按既有原子发布流程创建数据、配置、nginx、systemd、judge 环境快照，并做一次恢复演练；保留回滚目录。
3. **上传**：将 `FileMate-20261107-trial-d-final.zip` 的源码与 `release/web.tar.gz` 上传为独立 release 目录，校验 SHA256 `887bfda984c3640d17fc229484ee179b99cefa13e5bccfd470c1a7196ee4851e`。
4. **配置**：在新 release 的 `.env.production` 中写入上节开关与真实密钥；确认权限 `0640`、归属服务组。
5. **stage**：`python scripts/deploy_existing.py stage --release-id alphaN-<sha> --commit 86b8774... --version <版本> --backend-sha256 <...> --web-sha256 <...>`。
6. **activate**：同脚本 `activate`，它会在切换前做健康检查、备份恢复演练与原子链接切换，失败自动回滚。
7. **核验**：公网健康、版本号、`/api/trial/capabilities` enabled、教练 capabilities、一次真实只读流程、四主题与窄屏、模型调用的真实 usage 与失败码。
8. **回滚条件**：健康失败、schema 不符、开关未生效、真实流程异常或 usage 异常时立即按脚本回滚；**用户写入后不得用旧数据快照覆盖新数据**。
9. **回执**：记录实际 commit、产物哈希、开关状态、健康检查、真实流程结果、回滚可用性，形成发布回执文档。

## E 级真人实验

见 [E 级协议](LEARNING_ORCHESTRATOR_2_0_E_PROTOCOL_2026-11-07.md)。工程准备已完成，真人数据尚未采集，必须经伦理确认、招募与知情同意后开展；`learning_improvement` 保持 `null`。
