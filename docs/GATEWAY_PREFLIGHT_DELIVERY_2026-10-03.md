# 实际HTTPS网关预检与有限并发验收

2026-10-03。完成当前运维子卡的网关修复和本机预检；随后按用户最新要求优先推进前端视觉升级。运行指标、准入/配额、Linux容器和正式发布仍在完整执行账本中保留。

## 用户影响与实现

`deploy/Caddyfile`修复了宽泛`/interview*`将本地视觉模型/WASM误转到API的问题，补齐设置API转发，将页面/API共用的五个精确路径按HTML导航区分。其他API即使携带HTML Accept也返回真实后端结果。CSP允许本地WASM，HTML/API不缓存，哈希资源长期缓存，视觉资源校验更新，内部路径保持404。

正文读取上限32 MiB；声明超限在认证后、接收正文前返回统一JSON413，后端单文件上限仍为25 MiB。本机curl的HTTP/1.1分块超限同样返回413，未创建资料；分块拒绝不承诺JSON正文，客户端仍应保留输入并处理传输错误。

新增`gateway_preflight.py`和`gateway_production.mjs`，视觉验收增加直接网关模式，默认门禁及CI同步Ruff检查。没有API/schema版本变更或应用运行期新环境变量；验收专用环境与复跑命令见[工具说明](../scripts/acceptance/README.md#实际https生产网关预检)。

## 当前候选包直接证据

证据目录：`_working/operations-preflight-20261003/`，最新实际网关运行是`run8/`，独立前端为`_working/verify-web-2ffae887944646a183a236e87a8628ca`。Caddy v2.11.6来自官方Windows发行包，官方SHA512核验一致，来源/校验见`tools/provenance.json`。只忽略夹具自签证书验证，不安装系统根证书；临时数据、证书和临时文件均在独立证据目录。

| 检查 | 当前结果 |
|---|---|
| 全项目门禁`verify.log` | Ruff；740 passed / 18 skipped / 5 deselected；前端18项、类型检查/构建/首屏总依赖预算通过 |
| 网关`run8/summary.json` | 40项通过，前后8个关键文件指纹一致 |
| 路由转发 | 91个现役路径的GET状态和内容类型与实际上游一致，含合法CSV与405/404；不代替各写接口业务验收 |
| 页面`gateway_production/summary.json` | 28项：22页实际导航、Monaco、零脚本/CSP错误、375/768/1440布局 |
| 本地视觉`interview_vision_production/production-summary.json` | 4/4；真实Worker/WASM推理、录像及持久观察样本；公开图片合成视频/拒绝麦克风 |
| 上传与身份 | 实际HTTPS导入/读取，25 MiB文件及32 MiB声明/分块正文拒绝、不产生资料、第二访客404、未认证401 |
| 有限读取`run8/capacity.json` | 8个独立匿名客户端×16次，128/128成功；p50 13.045ms，p95 443.62ms，最大611.23ms，5秒p95门禁通过 |

并发结果仅来自Windows开发硬件的回环TLS读取，不包含模型生成、编译、上传或长期运行，不能当作正式服务器容量或SLA。前端预算沿用现有门禁，没有放宽。GitHub Actions配置已更新，本轮没有远端CI执行链接；没有提交、推送或部署。

## 故障与范围

初次`run1`连接失败及默认Caddy自动保存配置问题保留：后者确认文件只属本次夹具后移除，之后禁用自动保存和系统信任安装。`run2`暴露将合法CSV误判为JSON的验收错误，改为核对真实上游；`run4/run5`暴露大正文传输过程中连接关闭，加入声明超限提前拒绝并以Expect客户端验证。早期成功`run3/run6/run7`与这些失败均保留，不合并不同候选快照冒充单次结果。

线上本次只读抽样`website-health.json`为8/8，平均499.61ms、中位376.09ms、最大1367.79ms；仍是alpha.2，与本机alpha.1不同，编程ready:false。本轮没有改动线上代码、密钥或数据；真实学生/导师仍为0，无法据此得出学习收益。

回滚应使用已经匹配验证的前端/API/网关版本，并保留现役数据与迁移兼容性。不要把含本地WASM的新前端与旧的宽泛路由模板混用。真实Linux Compose镜像、实际证书/服务器容量、指标告警和版本同步仍待独立验收。
