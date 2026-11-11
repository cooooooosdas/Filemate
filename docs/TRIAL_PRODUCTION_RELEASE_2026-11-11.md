# FileMate 试行版生产发布回执

2026-11-11 已完成主站发布及公网验证。当前整体为 CONDITIONAL PASS，继续按试行版开展产品体验，规模与真人验证事项见末节。

## 现役版本

- Web/API 均为 `c28dc2b1ae7c5cbf047321286eb09f73223dac46`，版本 `1.3.0-alpha.4`。[打开主站](https://filemate.asia/)
- 业务 schema 36，资源治理 schema 3。发布目录为 `/opt/filemate/releases/alpha4-c28dc2b1ae7c`，静态目录为 `/clouddream/nginx-proxy-manage/data/filemate/releases/alpha4-c28dc2b1ae7c`。
- `FILEMATE_ENABLE_LEARNING_ORCHESTRATOR`、`FILEMATE_ENABLE_LEARNING_COACH`、`FILEMATE_ENABLE_TRIAL_WORKSPACE` 已启用。公网 capabilities 回读 enabled=true，教练 Prompt 为 `learning-coach-v2`。
- 独立面试音频、视频开关当前为 false。已发布的逐题面试、运行时与评分能力继续按各自现役配置提供。

## 发布验证

已部署源码对应的干净 Linux CI 为 `42812514732`，2191 项后端、444 项前端通过。主分支的后续文档提交记录发布事实，业务实现以本回执的部署提交为准。

- 后端产物 SHA256 为 `03002b5b7531b3577d5070ff22b65d0e3979dd6571ba118cd8a021cd20adee05`。
- Web 产物 SHA256 为 `5ef6046d8dd2c9962c7adc3ec79441bc952e70ea54df400fed7a1eae7c3cde57`。
- 隔离 stage、依赖检查、临时 API、完整数据备份、恢复演练、Nginx 配置与静态资源、公开健康与 release marker 均通过。
- 正式备份为 `/var/backups/filemate/alpha4-c28dc2b1ae7c-20261111T010346Z`，包含 532 个数据库、1452 份文件。恢复演练完成后释放本次演练副本约 754MiB，验证通过的 data 备份及回执仍可使用。
- 生产回退按已有脚本保留新写入，使用兼容 schema 36、账号和 D 级 Artifact 协议的代码版本。切换前的代码回退点为 `alpha4-fdf6f406a5d1`。

## 真实运行与 API

实际 Linux 为 Python 3.11.13、SQLite 3.26.0。native 与 forced-noJSON1 两种配置各 10 项通过，包含事务回滚、签名备份恢复、权限 epoch 更新、历史回执、旧来源读取、模型与数据库故障恢复及关闭功能后的原流程。强制配置实际拒绝 JSON1 调用 7 次。

DeepSeek `deepseek-v4-flash` 真实调用成功，使用 `learning-coach-v2`。单次调用耗时 2316ms，用量为 4270 prompt、569 completion、合计 4839 tokens，结果 effective_mode=model，持久化重读一致。合成案例已清理，金额字段依据供应商提供情况保留 null。

125 项公网 API 检查通过，覆盖注册、登录、登出重登、模块读取、原创 Markdown 上传及回读、目标到本周复盘、规则教练持久化、反馈幂等及跨账号隔离、个人导出、预览确认删除。实际编译隔离得到 AC 7/7 与 CE，结果均持久化。两个合成账号通过正常 API 注销，12 项清理检查通过，测试凭据文件已失效化。

公网健康单访客短窗口抽样为 12/12，平均 33.93ms，P95 为 88.48ms。此读数对应本次健康接口采样窗口。

真实 Edge 页面验证今日行动、本周复盘与试用反馈入口。390、768、1440px 稳态布局均无横向溢出，手机和平板导航在抽屉关闭状态显示，标题字号为 29／34／34px。初次窄屏截图捕捉了导航过渡过程，交付证据使用名称含 steady 的稳定画面。LOGO 为透明清晰版本。

## 服务器恢复

VNC 与上一启动周期日志确认多次全局 OOM，涉及无限额的 `dnf-makecache.service`。实例为 2 核、约 2GB 内存。正常重启后恢复 SSH、Nginx 与 API，随后完成本次发布。

本轮运维配置增加 `/swapfile-filemate-recovery`，容量 512MB、权限 0600，并登记 fstab。后台缓存任务使用 MemoryHigh=384M、MemoryMax=640M、CPUQuota=25%、Nice=15、OOMScoreAdjust=500。配置回退资料位于 `/var/backups/filemate/ops-20261111`。发布后复测约有 1GB 可用内存、1.9GB 系统盘余量，日常上传仍需关注剩余容量。

## 本机交付与证据

- 当前开发副本为 `D:/FileMate-Worktrees/release-alpha3/FileMate-Project`，主仓库为 `D:/FileMate-Project`，资料与发布包为 `D:/FileMate-Archive`。
- 用户已清理 C 盘大工作副本备份，复查可用空间约 33GB。旧开发路径已恢复为指向 D 盘的兼容联接。仍有 11 组历史迁移备份目录，自动清理再次被审批以 `blocked by policy` 拦截。
- 23 份既有用户测试的 SHA256 一致。业务源码、构建、迁移、API 合同与项目规则已核对，README、当前索引和 D 交付入口统一指向本回执。Agent 记忆为 out-of-scope。
- 私有原始证据统一位于 `D:/FileMate-Project/_working/final-trial-20261106`，包括 `production-activation-20261111.json`、`coach-linux-c28dc2b-runtime-20261111.json`、`coach-real-provider-c28dc2b-20261111.json`、`public-api-20261111.json`、`public-api-cleanup-20261111.json`、`website-health-20261111.json` 及 browser 下的稳态布局证据。
- 最新公开交付包为 `D:/FileMate-Archive/FileMate-20261111-试行版已上线.zip`，随附 SHA256 和 manifest，包含文档源码、实际部署的后端及 Web 产物、汇总发布回执。历史余量归档继续作为本机私有迁移资料使用。

## 继续保留的事项

- 万题四并发查询容量 P2 继续保留，既有 P95 509–571ms，门槛 500ms。
- 实体摄像头、麦克风及真实语音转写供应商仍需专项设备验证。
- 真人学习效果数据尚未采集，E 级协议与评测工具用于后续知情同意后的试用研究。
- 现场 Edge 记录 3 条消息通道连接错误，页面另有扩展注入脚本，仓库及发布脚本未发现对应 Chrome 运行时调用。日志尚待堆栈归因，公网功能与稳态布局检查通过。
