# V2.3 编程练习与真实隔离评测交付

交付日期：2026-10-01。范围为五模块升级中的 V2.3，沿用 Vue 3 / FastAPI / SQLite / Python 主链。

当前状态：V2.3已从最新main提取为独立分支 `codex/v2-3-programming`，提交 `ce45a01`；[PR #46](https://github.com/cooooooosdas/Filemate/pull/46)已合并，main提交为 `dcd18c1`。GitHub前后端CI通过，后端558项、前端12项；[CI证据](https://github.com/cooooooosdas/Filemate/actions/runs/36875170157)，安装包任务跳过。V2.2的PR #45已合并，依赖提交为 `9d6d4cb`。网站及EXE未升级。桌面FileMate源码目录为本工作区的Junction，源码修改同步生效，不代表安装包内容更新。独立发布快照与最新验收说明见 `_working/release-v23/docs/V2_3_PROGRAMMING_DELIVERY.md`；本文件同时保留原工作区历史证据，不能混用其测试数量。

合并后的main文件树与已验收分支一致；[main CI](https://github.com/cooooooosdas/Filemate/actions/runs/36875619579)也已通过。本轮临时验收服务已关闭，8008/8010/5178/5180无监听；结束检查临时 `filemate.cpp.*` AppContainer目录为0。源码与证据工作区保留，未清理或覆盖已有资料。

## 用户现在可以做什么

- 从“学习与练习 → 编程练习”进入 Monaco C++17 编辑器，按难度与知识分类选择题目。
- 使用8道原创题：简单3道、中等3道、困难2道，覆盖数组、字符串、二分、栈、贪心、排序、树、队列、图、优先队列和动态规划。
- 真正编译代码，逐测试点运行输入、比对输出，查看 AC / WA / TLE / RE / CE、通过数、得分、耗时、Job峰值内存、退出码和触发限制。
- 查看原始代码与编译诊断，保存本地复盘和笔记；主动确认外发后请求模型分析错误行、可能原因、复杂度、规范和失败测试点。
- 自动积累编程错题，重复练习后更新连续通过次数；同题连续两次AC标记已复习。语法错误仍作为有效错误提交，取消与基础设施失败不计入练习统计。
- 查看全部有效完成提交的分类通过率、本周练习/判定数、每题平均提交次数、最近30次结果和操作日志；无样本显示待评测。
- 取消正在评测的提交，或撤销/恢复已结束提交的统计资格。原始代码和历史结果均保留。

## 实现与数据

`filemate/programming/` 包含原创题库、工具链准备、Windows隔离执行、Judge适配接口、提交仓库、复盘与证据统计。`Programming.vue` 提供完整页面，`CodeEditor.vue` 延迟加载Monaco与C++语言模块，并在离开页面时释放模型、编辑器和监听器；加载失败保留文本编辑入口。共享类型位于 `types/programming.ts`，HTTP调用统一位于 `services/api.ts`。

新增 SQLite v22 的 `coding_submissions` / `coding_events`。代码、判题、本地提示、模型复盘和笔记保存为现役 `coding_submission` Artifact，不复制现役Quiz错题表。提交索引与Artifact/事件在同一事务中写入；唯一请求键保证重复创建只留下一个提交，不同代码复用旧键返回409。取消优先于迟到结果，撤销/恢复幂等，不重复记录同一状态事件。

损坏数据保持原库字节，暂停运行/改写/恢复，允许取消和撤销。服务重启后，未由当前进程持有的running记录转为中断失败，原代码可创建新提交重试。匿名身份沿用现役独立数据库，跨身份不能查看、取消或改写提交。通用Artifact编辑入口不能修改判题证据。

本次复核修复两处历史异常边界：找不到题目或固定版本不匹配的记录标记为不可用并排除统计，不用当前题目冒充旧版评测；损坏的孤立running记录只更新索引状态与中断事件，不改写原Artifact，不再阻断整个overview。状态与事件写入失败时一起回滚，重复恢复不重复记事件。新增6项回归，先复现失败再修复。

独立发布复核另修复中文MSVC诊断乱码：本机未安装英语编译器语言包，`VSLANG=1033`不能保证日志为UTF-8。编译日志先严格按UTF-8解码，必要时回退Windows ANSI；学生程序输出仍使用原有UTF-8规则。新增7项回归先失败后通过，真实CE诊断的中文可读且无替换字符。

提交列表不再把所有未撤销记录统一写作“有效记录”：取消/环境失败不计入，排队/运行尚未计入，损坏/不可用版本明确暂停；只有有效完成的AC/WA/TLE/RE/CE计入练习统计。异常记录的撤销确认与状态提示不再承诺当前可恢复统计资格。状态文案提取为纯类型化展示函数，并加入3项前端合同测试，不新增或伪造学习数据。

本轮同步修改 `server.py`、`storage.py`、导航/路由/API、前端依赖锁、旧schema断言、README和API_SPEC。独立发布分支仅包含V2.3和V2.2依赖的合并状态说明，使用SQLite v22。原工作区已有的V2.4/V2.5及其他未提交改动均保留，未夹带到PR #46；未进行网站部署或安装包发布。

## 本机隔离方式

本机没有可用Docker/WSL，但有MSVC x64与Windows SDK，因此实现了Windows原生适配层。准备操作只复制已安装组件到专用目录，不修改系统安装目录，不自动安装组件。工具链副本仅供本机使用，位于忽略提交的 `_working` 中。

编译使用不授予网络能力的AppContainer，学生程序使用更严格的LPAC。MSVC在LPAC中的临时文件/子进程行为不兼容，因此编译与运行使用不同、明确的隔离配置；没有退回普通宿主进程的路径。这一设计使用微软公开的 [AppContainer/LPAC 启动机制](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer) 和 [Job Object 资源限制](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)。

| 范围 | 限制 |
|---|---|
| 编译 | CPU与墙钟30秒，Job总内存768MB，最多8个进程 |
| 每个测试点 | CPU与墙钟1秒，Job总内存256MB，最多1个进程 |
| 输入/输出 | 只继承指定stdin/stdout/stderr句柄，stdout与stderr分别有64KB捕获上限，超过即终止 |
| 文件 | 工具链副本只读；每点独立目录和身份；宿主私有文件访问被拒绝 |
| 环境与网络 | 不继承模型密钥或其他宿主变量，只保留必要标准路径；无网络能力；BFE/MpsSvc未运行时拒绝执行 |
| 写入洪泛 | 每20ms观察Job累计写入，超过16MB阈值终止；可能有观察间隔内超出，不是磁盘硬配额 |

进程先挂起创建，绑定全部Job/安全属性后才恢复；任一限制无法设置就拒绝执行。退出、超时、输出洪泛、取消和异常路径会终止整个Job并释放句柄/临时身份。验收后检查残留 `filemate.cpp.*` AppContainer目录为0。

## 验收结果

以下是合成工程回归，使用真实编译器、真实隔离进程和真实UI/API；不是用户研究或模型准确率测量。

| 检查 | 结果 | 证据 |
|---|---|---|
| 独立发布快照全量门禁 | 退出0；Ruff通过；558 passed / 18 skipped / 5 deselected；前端12测试、Vue类型检查与构建通过；不含V2.4/V2.5 | `_working/release-v23/_working/acceptance/verify-release.log` |
| 独立发布编程专项 | 38/38通过，含新增7项编译日志解码回归 | `_working/release-v23/_working/acceptance/programming-final.log` |
| 独立发布真实隔离矩阵 | 49/49通过 | `_working/release-v23/_working/acceptance/native-final/summary.json` |
| 独立发布全新数据库UI | 14/14通过，页面JS错误0，中文CE诊断无替换字符 | `_working/release-v23/_working/acceptance/ui-final/summary.json` |
| 独立发布关闭回滚 | 16/16通过 | `_working/release-v23/_working/acceptance/disabled/results.json` |
| 历史V2.3快照全量门禁 | 退出0；Ruff通过；538 passed / 18 skipped / 5 deselected；前端9测试、Vue类型检查与Vite构建通过 | `_working/v2-3-20261001/verify-final-complete.log` |
| 本次原工作区全量门禁 | 退出0；Ruff通过；575 passed / 18 skipped / 5 deselected；前端12测试、Vue类型检查与构建通过；含V2.4草稿，不能据此宣称该后续模块验收完成 | `_working/v2-3-20261001/verify-revalidation.log` |
| 历史原工作区编程仓库/API专项 | 当时31/31通过；独立发布已增加至38项 | `filemate/tests/test_programming.py`；包含事务、取消竞态、幂等、损坏/不可用版本、孤立运行恢复与事件失败回滚、v21升级、模型格式/失败归因、匿名越权与网络隔离未就绪拒绝 |
| 真实原生C++矩阵 | 49/49通过 | `_working/v2-3-20261001/native-final/summary.json` |
| 完整UI验收 | 14/14通过，页面JS错误0 | `_working/v2-3-20261001/ui-verified/summary.json` |
| 独立关闭回滚 | 16/16通过 | `_working/v2-3-20261001/disabled/results.json` |
| 本次真实编译/隔离复核 | 49/49通过，结束后临时AppContainer目录0 | `_working/v2-3-20261001/revalidated-current/summary.json` |
| 本次全新数据库UI复核 | 14/14通过，页面JS错误0 | `_working/v2-3-20261001/revalidated-ui/summary.json` |
| 修复后再次全新数据库UI复核 | 14/14通过，页面JS错误0 | `_working/v2-3-20261001/revalidated-ui-fixed/summary.json` |
| 修复后真实HTTP异常历史恢复 | 200；4条真实有效完成统计不变，损坏孤立记录转failed，中断事件1条且原字节保留；异常数据为明确注入的合成输入 | `_working/v2-3-20261001/revalidated-ui-fixed/history-recovery.json` |
| 最终状态文案前端专项 | 15项测试、Vue类型检查及生产构建通过；在上述完整门禁后单独复核前端状态文案 | `_working/v2-3-20261001/frontend-final.log` |

原生矩阵包括每道题的AC/WA/TLE/RE/CE共40项。每题正常、空/极值等边界和最大规模数据均实际运行；参考解代码只作为测试输入，不参与Judge正确性决定。另9项探针核对宿主私有文件读写/环境隔离、编译期私有文件包含拒绝、LPAC网络连接、编译配置下的Winsock连接拒绝、子进程、内存、输出洪泛、文件写入洪泛和取消。首次网络断言要求特定错误码，实测LPAC先限制了Winsock初始化；后改为记录初始化/连接结果，并额外核对编译配置下实际初始化后的连接失败。最终49项全通过，早期失败证据也保留。

UI通过真实键盘输入Monaco验证编辑内容被准确提交，核对WA/AC/CE、64位结果、两个独立AC更新错题、笔记刷新持久化、撤销恢复、运行中取消、重复请求键、全部提交/本周统计及375/768/1024/1440布局。两项故障用例明确标为网络读取失败与模型失败注入，验证旧记录和分数保留；未调用外部LLM做质量测量。

关闭验收涵盖12个编程接口503、导航移除/旧URL回退，以及健康、资料源、知识图谱三个原接口继续可用。

全量验证采用独立前端副本，避免Windows原生依赖文件锁影响本机正在运行的Vite。副本没有复制 `.env` 或真实用户数据库。`verify.ps1` 保留默认命令行为，并增加 `-IsolateFrontend`；UTF-8 BOM保证Windows PowerShell正确解释中文脚本。依赖JSON保持原有CRLF风格，`git -c core.whitespace=cr-at-eol diff --check`通过。

## 可重复操作与回滚

实际环境依赖：Windows x64、MSVC x64、Windows SDK、可创建AppContainer及设置专用目录权限、BFE/MpsSvc运行。本机准备/自检已通过；其他机器需在页面点击“准备本地评测环境”。支持标准C++17头文件，MSVC不支持GCC专用 `bits/stdc++.h`。Linux/macOS、Docker适配、更多语言、题目导入和在线题库抓取未加入本次范围。

```powershell
uv run python scripts/acceptance/programming_native.py --out _working/v2-3/native
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
```

UI/关闭模块的独立端口、新数据库和环境配置详见 `scripts/acceptance/README.md`。原验收使用8002/8003与5174/5175，原工作区复核另用8007/5177，独立发布复核使用8008/5178和关闭开关的8010/5180，均为全新临时库；不以这些临时服务代替正常启动或生产部署验收。

模块回滚：设置 `FILEMATE_ENABLE_PROGRAMMING=0`，前端重新构建时设置 `VITE_ENABLE_PROGRAMMING=false`。保留v22表与Artifact，不进行SQLite降级或删除历史。单次提交可在结果区撤销/恢复。v22只追加表，旧学习/资料/图谱/面试数据无需改写。

## 后续依赖

- 外部模型参考建议接入现役LLM适配层，并有行号/失败点完整性校验与失败保留测试；真实外部模型质量和复杂度估计准确性尚未评测。
- Monaco约2.7MB未压缩、约694KB gzip，按需加载；当前构建仍提示部分块超过500KB，构建成功。
- 原生隔离验证覆盖明确的访问/资源探针；更多Windows版本和安装组合仍需适配验收。
- 当前题库只有固定版本1，未提供旧题版本注册表；题目或版本不可用时隔离记录并保留原产物，而不是尝试用新版重判。
- 真实用户试用、更多题目/语言与面试/职业模块联动属于后续阶段，不把本次合成验收当作这些阶段的完成证据。
