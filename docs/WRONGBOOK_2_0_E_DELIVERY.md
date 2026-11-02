# 错题复盘 2.0 E 级交付与 A—E 总装验收

2026-10-29。结论：CONDITIONAL PASS（本地工程条件通过）。A—E 的本轮工程实现、十个场景、独立审阅修复和交付归档已执行。当前审阅范围内未处理 P0=0、P1=0；E-P2-01 并发容量问题仍开放。未推送或部署。

本地单用户功能可以使用和演示；全量主站发布仍须生产 Linux 运行时的迁移／回滚恢复和容量验证。本报告不把合成回归等同真人学习效果，也不把 Windows SQLite 实测等同生产环境实测。

## 1. 实际改动文件

B、C、D 的历史范围分别见[B级](WRONGBOOK_2_0_B_DELIVERY.md)、[C级](WRONGBOOK_2_0_C_DELIVERY.md)、[D级](WRONGBOOK_2_0_D_DELIVERY.md)；历史证据保留原版本语境。

本次E产品增量：

- filemate/wrongbook/analysis_models.py：拒绝候选内重复原答引用。
- filemate/wrongbook/repository.py：单连接、最多2048项的时间解析缓存，保留严格时区与NULL语义。
- filemate/web/src/App.vue、navigation/route-state.ts：仅V2筛选复用工作区，显式刷新和旧版仍按原规则更新。
- filemate/web/src/components/wrongbook/ReviewWorkspace.vue、wrongbook/workspace-state.ts：零结果清空旧题、草稿与提交状态，并使迟到详情／来源／历史响应失效。
- 对应测试：test_analysis_service.py、test_repository.py、route-state.test.mjs、wrongbook-workspace.test.mjs。
- scripts/acceptance/wrongbook_release_runtime.py、wrongbook_release_fixture.py、wrongbook_release_journey.py、wrongbook_release_performance.py、wrongbook_release_empty.mjs、wrongbook_release_evidence.py、wrongbook_release_package.py。
- 本报告、README、API说明、当前交付索引、执行计划及E审计归档。

验证清单固定 642 份实际源码摘要；用户原有24份测试字节未变，未将其改动纳入提交。

## 2. 数据结构

沿用 Source／Artifact／Context、独立 quiz_attempts、wrong_questions 聚合与 review_events 审计。每次提交保存自己的题目版本、原答、判定方式和规则版本；幂等键和回执支持未知响应恢复。诊断、排期、分析、采纳、计划和撤销各自保留事件。

D的schema36保存分析请求、输入来源依赖及无正文请求墓碑。只有通过结构和逐字引用校验的输出才生成可用Artifact；删除任何输入来源时清除相应正文。学习计划最多7项，预览、编辑、确认后新增，保留已有计划和完成记录。

## 3. 数据迁移与回滚

本次E没有增加schema37或改写旧迁移。用官方Windows SQLite3.26.0引擎实际运行现有35、36迁移：v34旧作答保留、待核对作答 is_correct／score 为NULL、故障事务回滚、foreign_key_check为空、integrity_check=ok、.backup／.restore及当前Repository重读均通过。

引擎二进制SHA256：1570d755540a59e371df012865325cb7b498c8d0373fdcfea31f6900f458191d。
官方包来源：[SQLite3.26 Windows工具](https://www.sqlite.org/2018/sqlite-tools-win32-x86-3260000.zip)。

旧Windows CLI用工作目录内ASCII文件名执行，避开其Unicode命令行路径问题；未借此改动生产文件路径逻辑。生产Linux Python绑定与进程运行时仍待实机验证。

完整备份采用真实CLI预览、确认、停写创建、校验、恢复到新目录，再重启HTTP服务登录核对；重复创建／恢复拒绝覆盖。快照包含账户、资料、错题、四次独立作答和失败AI记录。关闭功能开关不降低schema；需要旧二进制时恢复停写前完整快照。

## 4. API合同

无新增公开路由或环境变量。沿用 /wrongbook/v2 的分页、独立作答、诊断、排期预览确认、历史、学习上下文、分析、采纳、计划与撤销接口；与今日、题集和课程图谱共享真实ID。

新模型输出中同一候选的相同 attempt_id／quote 不可重复计为依据；拒绝无效输出并保留失败状态。历史记录保持可追溯。请求认证、来源约束、严格参数、显式外发授权和浏览器临时密钥边界沿用D合同。

## 5. 页面与完整用户流程

| 场景 | 结果与证据 |
|---|---|
| 1. 错答进入错题库 | 真实HTTP创建错题与独立attempt |
| 2. 原题、原答、解析与来源 | 分别读取真实记录，保留原文 |
| 3. 诊断后重新作答 | 新attempt独立，诊断持久化 |
| 4. 答对后的规则与日期 | provisional、非掌握、次日复习 |
| 5. 再次错答 | 保留三次历史并重新排期 |
| 6. 今日队列一致 | 确认改期到期后完成，队列移除、详情同步 |
| 7. 图谱精确联系 | 实际课程／节点ID及浏览器往返 |
| 8. AI不可用 | 持久化failed；原答及基础练习可用 |
| 9. 刷新、重登、服务重启 | 四次独立原答及失败分析保持一致 |
| 10. 旧库读取 | 实际SQLite3.26迁移与快照恢复后重读 |

[连续流程与完整恢复](audits/wrongbook-2-e-2026-10-29/journey.json)14项全部通过；[工作台浏览器](audits/wrongbook-2-e-2026-10-29/workspace.json)21组、[学习闭环浏览器](audits/wrongbook-2-e-2026-10-29/learning.json)11组全部通过，均无pageerror。

额外真实浏览器回归验证：取消离开保留草稿，确认空筛选后移除旧题与提交按钮，返回加载干净问题。控制器回归同时验证迟到响应不能恢复旧题。桌面／平板／窄屏、四主题、长代码／文件名、键盘、200%缩放和对比度已覆盖；人工查看1440浅色工作台和375深色学习面板截图。未冒称实体手机测试。

## 6. 规则与AI可靠性

规则与原答证据优先；自报、揭晓后的回答和主观待核对不能制造掌握度。隔日验证需满足既定间隔、不同本地日期与证据要求；计划完成不等于掌握。AI只给可能错因和短行动，不改写原答、判题或掌握度。

本次修复同句重复引用；模型失败、错误引用、坏JSON、缺密钥、取消、网络与数据库异常的回归保持失败可恢复。外部模型调用有授权、次数及超时边界。受控loopback Provider用于工程故障模拟，未声称真实模型教育质量通过。

## 7. 自动化验证

最终源码：后端 1720 通过、22 跳过、5 项e2e未选；前端 278 通过，0失败。Ruff、类型、生产构建及原资源预算通过。独立补跑错题后端169项、路由与空结果状态17项通过；完整日志和源码摘要见[验证清单](audits/wrongbook-2-e-2026-10-29/verification.json)。

两开关首屏JS gzip：开启 142947 字节，关闭 142977 字节，上限仍143360字节。未扩大预算。D原门禁为历史版本；本结论使用E最终门禁。

跳过项如下，不记为通过：

- SKIPPED [1] filemate\tests\test_deploy_existing.py:15: 既有服务器部署工具仅在Linux使用
- SKIPPED [1] filemate\tests\test_bounded_parse.py:113: Linux worker address-space limit
- SKIPPED [1] filemate\tests\test_linux_judge.py:114: 仅验证 Linux 平台分支
- SKIPPED [1] filemate\tests\test_perception.py:191: 没有可用的 .docx 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:203: 没有可用的 .docx 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:216: 没有可用的 .docx 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:236: 没有可用的 .pdf 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:248: 没有可用的 .pdf 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:279: 没有大 PDF 文件
- SKIPPED [1] filemate\tests\test_perception.py:321: 没有可用的 .pptx 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:333: 没有可用的 .pptx 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:480: PaddleOCR 未安装（可选依赖）
- SKIPPED [1] filemate\tests\test_perception.py:491: 需下载 PaddleOCR 模型（~80MB），CI 环境跳过
- SKIPPED [1] filemate\tests\test_perception.py:610: 测试文件不存在
- SKIPPED [1] filemate\tests\test_perception.py:627: 测试文件不存在
- SKIPPED [1] filemate\tests\test_perception.py:640: 测试文件不存在
- SKIPPED [1] filemate\tests\test_perception.py:655: 测试文件不存在
- SKIPPED [1] filemate\tests\test_perception.py:821: 测试文件不存在
- SKIPPED [1] filemate\tests\test_perception.py:831: 没有可用的 PDF 测试文件
- SKIPPED [1] filemate\tests\test_perception.py:842: 没有可用的 PPT 测试文件
- SKIPPED [1] filemate\tests\test_resource_recorder.py:64: 实际 /proc 仅适用于 Linux
- SKIPPED [1] filemate\tests\test_server_persistence.py:1993: 需要符号链接创建权限

## 8. 浏览器、性能与故障证据

各性能行包含列表／搜索两种模式：首请求单次、预热后20样本、四并发20样本。首请求定义为新API进程后该工作区／模式首个请求，不清理OS磁盘缓存；环境为本机合成库。

| 错题条数 | 首请求ms 列表／搜索 | 单请求P95 ms | 四并发P95 ms |
|---|---|---|---|
| 0 | 332.42 / 77.83 | 80.19 / 79.07 | 200.53 / 203.14 |
| 100 | 111.63 / 78.64 | 90.49 / 84.19 | 226.82 / 220.39 |
| 1000 | 157.55 / 93.9 | 94.67 / 105.03 | 274.29 / 260.8 |
| 10000 | 371.13 / 338.73 | 222.86 / 351.96 | 680.88 / 668.18 |

0／100／1000／10000共8种单请求模式均达原500ms P95目标；四并发万条库仍有超标，原始失败结果保留，未算通过。每页和DOM最多30项，搜索覆盖全库。

初轮搜索UI耗时2441ms，定位为query变更导致页面重建；修复后单次trace为409ms。复测曾触发真实登录限流，未关闭限流。验收脚本也曾因按钮文案不符中断，改为实际文案后才取得新回归通过；最终使用全新隔离资料库重跑，未把早期失败覆盖成全绿。

一次独立审阅（加补充首次阅读交付脚本，非修复复审）发现1项Important和1项Minor：空筛选旧题、缺0条性能分布；均一轮修复并验证，未重复派审。[审阅与修复记录](audits/wrongbook-2-e-2026-10-29/review.md)。

## 9. 未实施能力与依赖

本轮批准的错题工程流程已实现。下列证据仍未取得：

- 生产Linux SQLite3.26的Python绑定、进程终止回收、附件一致性及真实服务器回滚恢复。
- 主站真实流量容量、实体手机，以及浏览器／OS之外的摄像头或声音设备验证。
- 真实外部模型的错因质量标注与真实学生长期学习效果；现有数据均为原创合成回归。

## 10. 已知风险与发布建议

E-P2-01：万条错题的四并发P95超过未改变的500ms参考目标。增加单连接时间解析缓存后有所改善，尚未解决并发容量问题。建议先分析生产SQL／线程与资源开销，完成容量优化和实机复测；不据本报告直接全量发布。

当前可用于单人本地使用、演示和受控小范围验证。保留业务36、旧数据和开关回退。P0/P1=0仅指本轮审阅与已执行证据范围，不是全项目绝对无缺陷声明。

## 11. 启动与复验

    powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
    powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
    powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
    .venv/Scripts/python.exe -m scripts.acceptance.wrongbook_release_evidence

归档检查验证源码与证据一致性，保留CONDITIONAL状态；其退出0不代表开放的四并发目标通过。

合成验收使用新建_working目录，密码仅从FILEMATE_AUDIT_PASSWORD环境读取。fixture／runtime／journey／performance脚本的--help给出参数；旧SQLite二进制自行从官方包取得。模型故障仅接入loopback受控服务。默认V2及AI开关保持关闭，启用方式沿用API说明，不擅自改变生产配置。

## 12. 交付与后续顺序

本地提交与A—E报告、执行账本、实际证据和源码摘要统一归档。源码包：_working/wrongbook-e-20261029/delivery/FileMate-Wrongbook-2.0-2026-10-29-source.zip，旁附SHA256。只打包Git跟踪文件当前字节，保留用户既有测试换行；排除运行目录、数据库、密钥和真实用户资料。包内_release/manifest.json记录HEAD与逐文件摘要，解包后可复验；不是已部署回执。

交付包探针发现3份测试日志被通用忽略规则漏装；已显式归档并加入打包前依赖／摘要检查。不完整包在创建前拒绝，修复后的候选包已在新目录实际解压，源码及证据摘要复验通过。最终包旁附校验摘要。

后续顺序：并发容量优化 → 生产Linux迁移／快照恢复 → 小范围真实模型与学生验证。Rulings及成本见[执行账本](audits/wrongbook-2-e-2026-10-29/execution-ledger.md)；本轮审阅Minor均已处理，容量问题单列保留。
