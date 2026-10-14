# FileMate 发布执行回执 · 2026-10-14

后续状态：10-14 深夜再次发生整机失联，10-15 00:25 已恢复并加固；根因仍开放，见[故障记录](INCIDENT_2026-10-15.md)。下文保留本批上线时的验收事实，不能替代后续稳定性结论。

## 结论

**DEPLOYED / 本轮更新已上线，产品整体仍为 CONDITIONAL PASS。**

2026-10-14 22:43（UTC+8）完成 Web/API 备份、恢复演练和切换，22:55完成独立Judge启动修复。正式地址为 [filemate.asia](https://filemate.asia/)。公网就绪、主要接口、两种自然语音和专用合成账户业务流程均实测通过。本轮不是新的完整产品审计，原始功能缺项和真实用户研究仍按既有账本保留。

| 组成 | 实际运行提交 | 主分支记录 |
|---|---|---|
| Web / API | `bfa080765a5e876b98c011c58cd8b64e04c22165` | [PR56](https://github.com/cooooooosdas/Filemate/pull/56)，合并 `0c90d49e030936148378a3256591b69b032bea03` |
| 独立 Judge | `78396339b83ed6bd2eba2d3c9f96a06a857507d5` | [PR58](https://github.com/cooooooosdas/Filemate/pull/58)，合并 `7f8993f206bb16ccee14fdc6c4c4a58547a35286` |

版本保持1.3.0-alpha.4，业务schema26、治理schema2不变。通过 /release.json 完整提交号识别Web/API批次；Judge使用独立发布链接，其镜像、gVisor、安全限制和题库没有改变。

## 发布内容与工程验证

- [四项修复](KNOWN_BUG_FIXES_2026-10-14.md)：Microsoft自然语音协议、上传文件名及失败清理、AI Schema校验、只读数据库就绪门禁。
- Web/API [候选CI](https://github.com/cooooooosdas/Filemate/actions/runs/38511781681)和[主分支CI](https://github.com/cooooooosdas/Filemate/actions/runs/38512137309)成功：Linux后端1115通过、18跳过、5排除，前端55项、类型、构建和预算通过；Windows后端1099通过、20跳过。
- 本次重启后发现Judge初始缓存时间戳0被当作已完成自检，导致开机不足600秒时跳过探针。现改为首次立即真实自检，之后再缓存；失败仍关闭评测。新增开机1/599/601秒和失败重试回归，本机23通过、1项Linux分支跳过；[完整Linux CI](https://github.com/cooooooosdas/Filemate/actions/runs/38584123416)后端1119通过、18跳过、5排除，前端55项及构建通过。
- 核对123个前端源文件，使用测试通过的构建；保留386个旧哈希资源，支持已打开页面继续加载。

| 包 | SHA256 |
|---|---|
| web.tar.gz | `105ff70f3217ad6fe39db4107df8fcba5d04e4d1307f27ee77c00eac96322b5e` |
| backend.tar.gz | `b226f828a5782c972091495f443824e18006f41baab80d7f5512585906281de9` |
| Judge启动修复包 | `ca1325e7026e226ba9bc7d1dbebae0986bf1b0520b64155f209964cba7ef589b` |

## 备份与恢复

Web/API备份：

`/var/backups/filemate/alpha4-bfa080765a5e876b98c011c58cd8b64e04c22165-20261014T144346Z`

停写后以SQLite backup API和附件快照保存222个数据库、509个文件，独立恢复演练、完整性和权限验证通过。历史空间存在业务schema15/24/25/26，治理schema2；这些历史分区不表示当前迁移版本降低。旧发布和备份保留；公众恢复写入后不得用旧快照覆盖新增用户资料。

Judge旧配置与链接备份：

`/var/backups/filemate/judge-bootfix-20261014T145529Z`

首次Judge激活验收在服务启动后过早读取socket，触发自动回退，已确认旧链接和服务恢复。部署助手补上有界socket等待后再次切换成功，以正式filemate用户访问受限socket并完成真实隔离自检。没有放宽安全策略或回写用户数据快照。

## 公网实测

22:50公网检查通过，22:57在更新后的Judge上完成合成账户业务流程：

- /release.json精确匹配bfa08076；health与ready均200，数据库、账号、治理账本均ready，探针不签发Cookie。
- 首页、全部入口静态资源及缓存合同通过；实际浏览器首页正常显示，服务已连接。
- 账号查询、知识图谱、岗位状态、判题状态、导师记录、资料列表、分析概览、隐私边界均200且success；判题ready和network_isolation_ready为true。
- 超长上传文件名400；未授权语音403。晓晓、云夏均200，约1.41/1.52秒，46656/47376字节，MP3完整解码通过；仅外发原创合成句。
- 临时合成账户使用9位字母数字混合密码注册、退出、重新登录通过；会话Cookie有HttpOnly/Secure/SameSite。
- 中文合成课程上传解析成功。真实C++判题AC、WA、CE与预期一致，分别约5.42/5.33/0.66秒。
- 完成后先预览，再注销临时合成账户及其空间；重新查询确认未登录。不涉及既有演示账户或真实用户资料。

本轮没有读取真实用户模型密钥或用其调用LLM。结构化输出有工程回归，不能写成所有供应商和真实学习效果已经验证。

## 连接故障经过

12:41及18:48，本机多种客户端、两条网络和[独立云端诊断](https://github.com/cooooooosdas/Filemate/actions/runs/38512673824)均遇到SSH握手或HTTPS超时。当时没有部署、维护标记或生产备份；早先标注“待上线”的ZIP反映当时状态。

用户随后完成阿里云登录。控制台确认实例运行、IP正确，最初CPU约95%–97%。监控随后回落，SSH恢复时系统uptime约4分钟，HTTPS也恢复。本轮自动化没有执行实例重启；证据不足以将连接故障断定为某进程、OOM或云网络。恢复后可用内存约1GiB、根盘余量约15GiB，当前启动周期未发现OOM记录。

连接恢复后才执行stage、activate及Judge修正。未修改安全组、创建云凭据、上传私钥或关闭TLS/主机密钥校验。

## 交付与保留限制

最新包为 `FileMate-20261014-已上线完整发布包.zip`，包含源码、编译前端、原始部署包、Judge补丁和脱敏回执；不含生产.env、数据库、Cookie、密码或私钥。生产备份留在服务器受限目录。

证据位于忽略目录 `_working/deploy-20261014/`：stage/activate日志、CI、public-smoke、workflow-smoke、Judge回执及首页截图。失败记录保留。

完整FEATURE07–13缺项、细粒度开关、解析隔离/展开预算、邮箱归属验证、评分/检索校准和真实学生研究仍按[需求账本](FEATURE_07_13_REQUIREMENTS_LEDGER.md)与[最终审计](FINAL_PRODUCT_AUDIT_REPORT_2026-10-10.md)保留。桌面安装器未纳入本次网站发布。
