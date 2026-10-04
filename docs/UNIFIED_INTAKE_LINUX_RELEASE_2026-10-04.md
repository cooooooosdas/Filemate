# 统一资料入口、多分类一言与Linux判题发布

日期：2026-10-04；[当前网站](https://filemate.asia/)；版本 `1.3.0-alpha.4`，schema v25，无新迁移。运行提交 `270ee4f199202d33358621e1f13e1d2da4a3837f`，视觉基线 `UI-2026.10.04-unified-intake-linux-judge`。该业务提交已推送main，远端CI [branch](https://github.com/cooooooosdas/Filemate/actions/runs/37184985421) 与 [main](https://github.com/cooooooosdas/Filemate/actions/runs/37185433971) 均成功；后续文档提交不改变线上业务源码或提交标记。

## 用户可见改变

- 首页左侧标题保持，右侧一言从动画/漫画/文学/诗词/哲思库取原文、作品与作者，详情按实际UUID链接。8–48字符，访问内稳定、刷新或登录换句，断网缓存及经典备用；接口没有独立“热血/励志”分类，不能保证每句都是励志。
- 顶栏固定唯一“添加资料”入口，资料页用两张用途卡分为阅读学习与整理归档；批量上传、重试、下一步与结果同屏。学习工作区移除重复文件选择器，空态仍有清晰引导。整理先模型授权，再集中核对与确认，上传不自动归档。
- Linux网站实际执行C++17编译与测试，GCC/gVisor/单学生进程/无网络/只读根文件系统，资源、输出和取消清理经过真实探针。AI复盘单独授权并持久化，不改变编译器得分；Windows原MSVC/LPAC保留。
- 注册、跨浏览器登录、游客资料认领、退出、密码恢复、旧恢复码失效与会话撤销继续通过真实网站检查。

设计复用现有钴蓝光束与Tabler图标，参考[Aceternity File Upload](https://ui.aceternity.com/components/file-upload)、[React Bits Stepper](https://reactbits.dev/components/stepper)和[Linear](https://linear.app/features)的集中入口、投放反馈与清晰任务引导，自写Vue/CSS；不引入React运行时。一言合同来自[官方API文档](https://developer.hitokoto.cn/sentence/)。源码与合同详见[入口交付](UNIFIED_MATERIAL_INTAKE_2026-10-04.md)、[一言交付](HOME_ENCOURAGEMENT_CATEGORIES_2026-10-04.md)、[判题交付](LINUX_CPP_DELIVERY_2026-10-04.md)及[API规范](../filemate/docs/API_SPEC.md)。

主要改动：`filemate/web/src/App.vue`、`views/Import.vue`、`views/Home.vue`、`views/LearningWorkspace.vue`及旧归档入口；`home/encouragement.ts`、`home/visitEncouragement.ts`、一言组件与API/类型；`filemate/programming/linux_judge.py`、`linux_broker.py`、`linux_docker.py`、`service.py`和GCC诊断复盘；`scripts/judge/`、`server.py`及编程状态页面/类型。验收脚本、API合同、README、设计系统、执行账本与本轮报告同步，版本迁移保持不变。

## 最终验证及证据

| 范围 | 当前实际结果 | 证据（项目忽略目录） |
|---|---|---|
| 默认完整门禁 | Windows807通过，20跳过、5排除、3依赖弃用警告；前端35、类型/构建/体积通过 | `_working/linux-judge/verify-final.log` |
| Linux CI | 817通过，18跳过、5排除，前端35与构建通过；桌面安装包job按配置跳过 | 上方对应运行提交CI |
| 实际TLS网关/本地模型合同夹具 | 47组、96 API路径；页面29、归档17、工作区25、知识布局18、视觉12通过 | `_working/unified-intake/gateway-v2/` |
| 候选统一入口浏览器 | 7组，四宽度/无障碍/延迟/失败重试/上传期间离开保护/授权 | `_working/unified-intake/browser/` |
| Linux服务器真实原生判题 | 12组；隔离、AC/WA/CE/TLE、内存/输出/磁盘、逐点文件隔离、伪造诊断、取消与清理 | `_working/linux-judge/native-result-final.json` |
| 公网实际模型及API | 42项，依赖列表为空；四类资料产物、引用问答/持久化、错题复练、图谱确认/撤销/恢复、来源面试实际llm评分、C++四判定与AI复盘 | `_working/linux-judge/live-api/summary.json` |
| 公网账号浏览器 | 12组，包括16个四宽度/AA组合；真实注册、两设备登录、退出、恢复及清理 | `_working/linux-judge/live-accounts-v2/summary.json` |
| 公网统一资料入口 | 9组，实际Markdown/代码文件选择、批量持久化、下一步与刷新恢复、四宽度/AA、归档授权；自建资料清理确认 | `_working/linux-judge/live-intake-v3/summary.json` |
| 公网实际归档分析 | 3组，授权后模型分析、集中预览与确认归档、撤销/重复撤销；原始合成文件和会话留作已撤销记录 | `_working/linux-judge/live-archive/summary.json` |
| 公网真实一言 | 8组，实际5类请求、原文出处一致、四宽度/AA、返回稳定/刷新换句/CSP/标记 | `_working/linux-judge/live-quotes/summary.json` |
| 公网页面/API冒烟 | 24页/9API、无JS/资源错误或横向溢出 | `_working/linux-judge/live-routes-v2/summary.json` |
| 网站低负载健康读取 | 20/20成功，服务器端公网TLS p50 25.87ms、p95 327.27ms，API重启0；不是并发容量测试 | `_working/linux-judge/runtime-health.json` |

首次将多组公网脚本同时运行，合计请求触发既有120次/分钟/IP网关限流，导致账号、资料清理和页面冒烟出现429/等待超时。原失败报告保留于 `live-accounts/`、`live-intake/`、`live-routes/`；账号与页面顺序重跑使用v2独立目录。入口v2脚本等待“当前最后一项就绪”时，第一项先完成便提前判断双份结果；修正为等待两项均就绪，v3通过，原v2失败保留。不修改业务接口、不放宽生产限流或用夹具替代公网成功。真实学习收益仍没有学生或导师数据，本表只证明当前合成工程流程。

## 部署、备份与运行限制

后端包 SHA256 `767f9ae3efba950bb5ee05f4998a92b73c0a769ba2687e48e87231883ddafc66`；前端包 `fa5574f3ec10d7927499f95dc1b430894b89be1651ebcd877f3df91b405bbdfa`。校验后独立release/venv及临时数据预检，停写后备份和新目录恢复演练通过，再原子切换API/静态链接与Nginx。备份 `/var/backups/filemate/alpha4-270ee4f1-20261004T072248Z`，113数据库、126文件，schema 15/24/25完整。保留119份旧hash资源，避免旧页面切换时404。旧发布与备份保留；公开写入之后回退仅切代码兼容现有schema，不覆盖新用户数据。

判题代理发布 `/opt/filemate-judge/releases/alpha4-270ee4f1` 与业务同提交，核心代码仅规范化CRLF后与12组实际测试候选相同；镜像内容ID与gVisor固定版本见判题交付。Web服务用户无Docker权限，Unix socket仅受限协议；服务并发1，编译30秒/384MB，运行每点1秒/256MB，输出64KB、临时文件系统16MB，题库当前8道C++17。判断资源及复杂程序适配继续拓展，不能把隔离探针视为零风险保证。

本次只用自建合成账号和原创文件。成功验收的自建资料按预览确认删除、面试按确认token删除、编程验收记录撤销不计统计；账号注册记录及撤销代码记录保留，因为尚无账号删除合同。首次429中未完成清理的合成资料单独记录，不当作真实学生记录；不读取或删除其他用户资料，不提交数据库、凭据或真实材料。

仍需真实学生/导师采集与质量校准、邮箱归属验证（现役恢复方式为恢复码）、桌面独立安装/升级及干净机器验收、长期监控/配额和异地备份、题库覆盖与并发容量。后续按[开发流程v2](DEVELOPMENT_WORKFLOW_V2.md)独立卡推进。
