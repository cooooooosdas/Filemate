# 首页诗词一言交付（2026-10-04）

按用户标注保留左侧「今天，让知识成形。」；右侧银蓝区域接入[一言诗词接口](https://developer.hitokoto.cn/sentence/)，替换未上线的原创10句方案。诗句24–34px、作者及出处16px，窄屏移到导入按钮下面。

## 内容与请求

官方HTTPS GET只取`c=i`诗词类8–22字JSON，2.5秒超时；每次打开/刷新首页最多一次请求，同次SPA切页复用Promise。请求不携带Cookie、Referer、资料或学习内容；正文仅按标点分行，作者/作品按`from_who/from`显示，缺失不补写。来源外链为官方UUID详情，不使用远程JS输出；CSP在Web、演示网关及桌面源配置中只增加`https://v1.hitokoto.cn`连接许可。接口记录不等同于逐句独立文献校勘。

最多缓存24条实际接口响应，读取时校验类别、UUID、正文及长度并重新构造链接；同ID或异ID同文重复时选其他缓存句。断网、429、超时、异常或禁用存储时，使用缓存或两条已核对原文的备用句：[杜甫《望岳》](https://www.gushiwen.cn/mingju_960.aspx)、[陆游《冬夜读书示子聿》](https://m.ccdi.gov.cn/content/7d/c6/23245.html)。备用句不限定在线句库规模。

## 验证与发布

- 默认`scripts/verify.ps1 -IsolateFrontend`：784后端通过、19跳过、5排除；33前端通过，Ruff、Vue类型、构建、体积预算通过。记录`_working/home-encouragement/verify-hitokoto.log`。
- [代码提交的CI](https://github.com/cooooooosdas/Filemate/actions/runs/37141646319)：Linux792后端通过、18跳过、5排除；33前端通过；Python包及合成分析管线通过。安装包任务按既定条件跳过，不计为安装包验收。
- 隔离浏览器32项布局（8类实际响应夹具/边界/错误 × 375/768/1024/1440）、2项行为组、4宽度首页WCAG规则检查通过；覆盖请求去重、返回保持、刷新、重复响应、429/断网、非法数据、禁用存储和减少动画。证据`_working/home-encouragement/hitokoto/summary.json`，明确为合成UI回归。
- 75份前端源码与全门禁副本一致，100份编译文件与浏览器预览包逐个SHA256一致。首页全部静态依赖JS371006字节、估算gzip137636字节、CSS103718字节，在既有预算内。
- 公网8项真实浏览器检查通过，无请求模拟：取得两次真实一言响应，原文/作者/作品/链接匹配DOM；四宽度无溢出、首页无障碍规则通过；切页保持、刷新换句、公开提交与健康接口正确；无JS/CSP错误。证据`_working/home-encouragement/live/summary.json`，截图同目录。

软件仍为`1.3.0-alpha.3`，UI编号`UI-2026.10.04-hitokoto`；前端运行提交`857782b773ba005f51d1e640cc26a0d298b37825`、后台`9c133e1701d0518579faf4e174da2c9d17db4199`，公开`/release.json`分别记录两者。

静态`current`原子切到`releases/ui-20261004-857782b7`。包SHA256为`690d107475df0fd92788de7a70b4d64d06512dda2dab4cc88cf6b8eeffb1b153`，101份包内文件校验，另保留26份旧哈希资源。实际NPM配置只增加上述CSP连接；`nginx -t`通过，API active/running、重启次数0，无后端路由或数据库迁移。

服务器操作与回执保留在`/opt/filemate/incoming/ui-20261004-857782b7`，本机清单/回执在`_working/home-encouragement/package.json`及`activation.json`。旧配置为服务器该目录的`http.conf.before`；回滚前检查当前仍为此UI，恢复配置、检查并重载Nginx，再将静态链接原子指回`releases/alpha3-9c133e17`。不要覆盖数据库；历史备份与原主工作区文件保留。

用户新优先级：下一独立卡为PRODUCT-01真实注册/登录/会话与找回，再逐项测试各功能/API。当前登录仍是预览，本报告不将后续任务计为完成。
