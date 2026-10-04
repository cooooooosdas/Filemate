# 网站自带模型密钥与404修复

用户反馈公网粘贴密钥后404。实际浏览器复现GET和PUT `/settings/llm`均404；该接口仅用于本机系统凭据库，而现役公网Nginx按设计屏蔽它。旧页面错误地把本机入口用于网站，并声称网站可以直接保存到访问者Windows凭据库。

按用户要求补齐网站的本机保存链路。网页先使用候选密钥做一次实际DeepSeek连接测试，通过后才按当前学习空间加密保存到浏览器IndexedDB。失败保留原有效配置，不跳转、不假报保存成功。增加主动测试连接、明确保存位置和移除操作；密码输入在设置关闭后清空。桌面和本机Web继续使用操作系统凭据库。

浏览器使用标准WebCrypto AES-256-GCM、随机IV、作用域附加认证数据和不可导出CryptoKey。只保存密文及CryptoKey；不写浏览器Web Storage、服务器数据库、日志、环境变量或Git。账户及游客学习空间分别隔离，注销后其他账号不能复用当前账号保存的密钥。仅显式AI请求经本站HTTPS在请求头中转发，后端请求上下文接入现役LLMClient；有效期仅此请求，不污染并发用户、共享部署配置或已有客户端。自带密钥强制官方地址且禁用重定向，错误不回显上游正文；无效DeepSeek密钥返回本站502，避免误触发本站401登录过期处理。公网及匿名代理仍不能修改系统共享凭据。

浏览器存储依赖同源脚本与本机可信，不能承诺抵抗XSS、恶意扩展或本机入侵；不可导出CryptoKey也不能阻止同源恶意脚本请求解密。现役CSP、Vue转义、同源限定与系统凭据库规则保留。此机制按用户明确要求提供网站本机持久化，不替代操作系统密钥库；清除站点数据或在其他浏览器登录需重新填写。用户之前的失败保存没有成功持久化，版本上线后应刷新页面再填写；无需向开发者发送密钥。

源码：[模型设置面板](../filemate/web/src/components/LLMSettingsPanel.vue)、[本机加密存储](../filemate/web/src/services/llm-vault.ts)、[统一API入口](../filemate/web/src/services/api.ts)、[请求凭据隔离](../filemate/llm_client/request_credentials.py)、[公共合同](../filemate/docs/API_SPEC.md)。按[DeepSeek官方接口文档](https://api-docs.deepseek.com/)核对HTTPS地址及现役模型别名；`deepseek-v4-flash`当前仍被官方接受。模型、schema及业务产物合同不变，仍为alpha.4 / schema v25。

2026-10-04已推送主分支并上线，前后端运行提交 `0dd4cc449930bb20c50582abb49adce44bef086f`，UI标识 `UI-2026.10.04-browser-model-key`；密码9字符规则已包含于此版本。最终Windows全量841通过、20跳过、5 deselected；模型合同专项19通过；前端40通过，类型、构建和体积门禁通过。Linux CI 851通过、18跳过、5 deselected，[候选分支CI](https://github.com/cooooooosdas/Filemate/actions/runs/37195691519)及[主分支CI](https://github.com/cooooooosdas/Filemate/actions/runs/37196082746)成功。

浏览器存储专项9组通过：候选验证后加密保存、失败替换保留原密钥、不可导出CryptoKey及密文无Web Storage明文、完整重启后恢复、生成请求携带当前空间凭据、注销/异账号隔离及原账号恢复、仅移除当前空间记录，以及四种宽度的布局和无障碍检查。使用实际HTTPS、SQLite与浏览器存储，正向模型响应使用明确标注的合成传输夹具；它只验证凭据流转，不能作为真实DeepSeek接入证据。

公网浏览器5组另行通过：新设置接口200且不请求旧入口、真实无效DeepSeek密钥返回可解释502而非404并保持登录、部署连接主动测试收到真实供应商响应、375/768/1024/1440布局与WCAG AA检查，以及关闭面板清空候选输入。第一次无障碍扫描撞到自动消失提示的过渡帧；原失败记录保留，在提示自然消失、面板稳定后复扫四种宽度通过，不据此宣称瞬态动画逐帧可访问性已验收。

公网真实业务23项通过，包括注册及独立学习空间、请求独立密钥连接、原创合成资料导入、四种学习产物、带引用且可重新读取的问答、只生成待确认草稿的图谱、五项旧AI接口、上传归类分析、面试题生成/实际模型评分/内容分析、C++编译器AC/WA/CE/TLE及AI代码复盘。真实DeepSeek凭据仅在服务器进程内读取既有部署配置并作为请求头测试输入，不导出到客户端或证据，不读取真实用户密钥；共享模型配置保持不变。AI复盘是参考意见，编译器成绩未被覆盖。原始业务响应和持久化读取均来自公网真实接口，没有替换供应商响应。

业务后清理脚本首次把相同正文导入所得的同一Source重复删除：首次成功，随后五次正确404被脚本误判为失败；原始34项记录保留，不能称34项全绿。脚本改为按Source ID去重；独立合成账号的4项定向复测确认导入复用同一Source、只删除一次且随后读取404、会话注销均通过。仅清理本次合成资料和面试并撤销自己的代码提交，合成账号登记、已撤销代码记录及一个未确认执行的归类会话保留；不以这些数据计算真实学生效果。

上线前142个数据库、158个文件完成备份及新目录恢复演练，备份为 `/var/backups/filemate/alpha4-0dd4cc44-20261004T104017Z`。已有资料、账号及schema v25保留，上一版183个哈希静态资源保留供已有页面请求。现役Linux判题服务继续使用已验收的 `alpha4-270ee4f1`；最终服务探针确认API和判题服务运行、重启计数0、判题自检就绪、无残留评测容器或任务挂载、维护标志关闭。代码回滚须兼容当前账号及schema，不以旧备份覆盖上线后的新写入。

后端包SHA256：`5c14cd9cac0f60160bfba5da93144444847ef739567a18d25d3a32d9bd7cc4e3`；网页包SHA256：`75b61aa3ee0c66b6d018857b425043412ea26b298ea2ade5bf0730f5c189ce53`。

本工作树证据位于 `_working/llm-byok/`：`before.json`、`backend-final.log`、`frontend-final.log`、`llm-contract.log`、`browser/summary.json`与截图、`live-browser/summary.json`与截图、`live-model-api-initial.json`、`cleanup-dedup.json`、`live-model-api-summary.json`、`staged.json`、`activate.log`、`backup-result.json`和`runtime-final.json`。各项模型入口一个原创合成用例，证明工程接入与持久化闭环，不代表任意资料质量、长期容量或学生学习收益；未验证用户此前粘贴的具体密钥。真实学习研究尚未采集，邮箱归属验证、独立安装与持续容量仍沿原开发账本推进。
