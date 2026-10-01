# V2.3 编程练习与隔离评测

日期：2026-10-01。仅交付五模块计划中的 V2.3，不包含 V2.4/V2.5 草稿。

基线为已合并的图谱 PR #45：`9d6d4cb0487ead9b307f5293613be4e3269bc1d8`。分支 `codex/v2-3-programming`；独立发布快照位于项目 `_working/release-v23`，原工作区和全部既有改动保持原样。源码、PR、网站及 EXE 状态分别验收，不混同。

## 用户变化

- “编程练习”提供按需加载的 Monaco C++17 编辑器；加载失败保留文本输入，离开页面释放编辑器、模型和订阅。
- 8 道原创题：简单 3 道、中等 3 道、困难 2 道；包含普通、边界及最大规模测试输入，不抓取第三方题库。
- 真正编译与逐点执行，显示 AC/WA/TLE/RE/CE、通过点数、得分、耗时、峰值内存、输出及编译诊断。模型建议不能改变判题。
- 保留原代码，支持本地复盘、笔记和明确同意外发后的模型参考建议；模型失败不丢失判题或已有复盘。
- 真实有效提交驱动编程错题、分类通过率、本周记录和最近趋势；无样本显示待评测，同题连续两次 AC 标记已复习。
- 运行可取消，已结束提交可撤销/恢复统计资格；重复操作幂等。取消/基础设施失败不计入统计。

## 公共合同

- API：新增 `/api/programming/status`、`setup`、`problems`、`overview`、`submissions` 及单条运行/取消/撤销/恢复/复盘/笔记接口，保持 `ApiResponse` 和匿名设备分库。
- schema：v22 只追加 `coding_submissions` 和 `coding_events`；代码、结果、复盘、笔记复用 `coding_submission` Artifact，旧迁移不改写。
- 路由：`/programming`。环境开关：`FILEMATE_ENABLE_PROGRAMMING=0`、`VITE_ENABLE_PROGRAMMING=false`。前端关闭后旧地址返回学习工作区，后端关闭后新接口 503。
- 工具链：可用 `FILEMATE_CPP_TOOLCHAIN_DIR` 选择专用 MSVC/SDK 副本目录；不复制模型密钥到子进程，不自动安装系统组件。

完整字段、限制与统计规则以 [API_SPEC](../filemate/docs/API_SPEC.md#411-v23-c-编程练习与隔离评测) 为准。

## 数据可靠性与隐私

索引、Artifact 和事件在同一事务中保存；相同请求键不重复创建，不同内容复用旧键返回 409。取消优先于迟到结果。通用 Artifact 编辑拒绝改写判题证据。

损坏 JSON、题目不存在或固定版本不匹配的记录标记 `data_error`，不进入画像，不用当前题目冒充旧版评测。原产物字节保留，暂停执行/修改/恢复，仍可取消和撤销。损坏的孤立运行记录恢复时只原子更新状态与中断事件，不阻断正常历史；事件失败回滚，重复读取不重复记事件。

列表逐条说明统计资格：排队/运行“尚未计入”、取消/失败“不计入”、损坏/不可用版本“记录不可用”；不把所有未撤销记录笼统称为有效记录。

模型调用需用户主动确认发送题面、完整代码和截断的编译/逐点日志；不发送音视频或环境变量。行号与失败点必须符合真实结果，异常建议拒绝保存。复杂度与规范建议只是参考，不是正确性或能力结论。

中文 MSVC 有时忽略英文语言偏好并输出系统 ANSI 编码；编译器日志优先 UTF-8、失败才回退 Windows 系统代码页，保存和 API 仍为 Unicode/UTF-8。学生程序输出继续按 UTF-8 读取，不套用编译器回退。7 项新增回归先失败再修复，真实 UI 的 CE 诊断确认不再出现替代字符。

## 隔离边界

本版本仅支持 Windows x64、MSVC 和 Windows SDK。编译使用不授予网络能力的 AppContainer，学生程序使用 LPAC；没有普通宿主进程回退路径。进程挂起创建，建立安全属性和 Job 限制后才恢复。

| 范围 | 限制 |
|---|---|
| 编译 | CPU/墙钟 30 秒，Job 总内存 768 MB，最多 8 进程 |
| 每测试点 | CPU/墙钟 1 秒，Job 总内存 256 MB，最多 1 进程 |
| 输入/输出 | 仅指定 stdin/stdout/stderr 句柄，stdout/stderr 各 64 KB 上限 |
| 文件 | 工具链副本只读；每点独立目录与临时身份；宿主私有文件不可访问 |
| 网络/环境 | 无网络能力；BFE/MpsSvc 未就绪则拒绝执行；不继承宿主密钥变量 |
| 写入洪泛 | 每 20 ms 观察累计写入，超过 16 MB 阈值终止；不是磁盘硬配额，可能间隔内超出 |

MSVC 不支持 GCC 专用头文件。Linux/macOS、Docker 适配、更多语言和题目导入未交付；在线 Linux 网站可以展示不可用状态，但不能宣称已具备在线 C++ 执行。

## 验收

验收使用合成输入、真实编译器、真实隔离进程和真实 UI/API，不是学生试用或模型准确率测量。

以下结果均来自独立发布快照，不混入原工作区的 V2.4/V2.5 草稿：

| 验收 | 结果 | 本机证据 |
|---|---|---|
| 完整门禁 | Ruff、558 passed / 18 skipped / 5 deselected、前端 12 测试、Vue 类型检查与生产构建通过 | `_working/acceptance/verify-release.log` |
| 编程仓库/API/解码专项 | 38 项通过，含 7 项解码新增回归 | `_working/acceptance/programming-final.log`；完整门禁含相同测试 |
| 真实编译与隔离矩阵 | 修复后 49/49；8 题×5 判定，加 9 项隔离/资源/取消探针 | `_working/acceptance/native-final/summary.json` |
| 全新数据库浏览器 | 14/14，页面 JavaScript 错误 0；真实键盘编辑、编译、笔记、错题、撤销/恢复和四种宽度 | `_working/acceptance/ui-final/summary.json` |
| 独立关闭回滚 | 16/16，12 个新接口关闭、旧 URL 回退、3 个原接口仍可用 | `_working/acceptance/disabled/results.json` |
| 手工 CLI 复核 | 真实页面、练习证据与控制台；错误/警告 0；人工检查 375px 截图 | `.playwright-cli/` 与上述 UI 证据 |

首轮门禁的旧 schema 断言失败、冷启动 UI 超时及其连锁失败、7 项解码失败测试全部保留。浏览器脚本改为明确等待页面/编辑器/环境就绪和筛选状态，不忽略断言，也不据此宣称首屏性能已优化。最终在另一全新数据库通过全部 UI 场景；CE 的中文日志已实际核对。

18 项跳过来自可选 OCR、缺少样例文件及 Windows 符号链接权限；5 项 e2e 未选择。3 项依赖弃用警告未消除，Monaco 等部分生产块超过 500 KB 的构建警告仍存在。

可重复命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
uv run python scripts/acceptance/programming_native.py --out _working/acceptance/native
```

独立端口、新数据库、浏览器和关闭模块配置见 [验收手册](../scripts/acceptance/README.md#v23-编程评测)。测试输出只写 `_working`，不提交数据库、截图或私人资料。CI 继续检查全部非 e2e 测试，并将编程源码与测试加入 Ruff 范围。

## 回滚与待评测

关闭上述前后端开关即可隐藏新入口并禁用编程接口，不影响原资料、练习、图谱和面试。不降级 SQLite、不删除提交历史；单条撤销仅改变统计资格。

真实外部模型质量、真实学生试用、更多 Windows 安装组合仍待评测。Monaco 按需加载但构建块仍较大。题库只注册固定版本 1，旧版不可用时保留记录并排除统计。后续 V2.4 需独立交付与测试，不包含在本报告中。
