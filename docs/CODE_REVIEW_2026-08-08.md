# FileMate 历史代码审查备忘（2026-08-08）

> 审查日期：2026-08-08
> 审查基准：GitHub `origin/main` `003f828`
> 状态：历史快照。此文只描述 `003f828` 当时的问题，不能作为当前实现状态；
> 其中大部分工程、文档、可信执行和学习闭环问题已在后续版本处理。

## 一、结论摘要

当前仓库更像“带 README 和架构图的项目原型”，而非可直接演示或参赛的系统。主要问题不是功能少，而是文档、架构、测试与真实代码互相脱节，且主流程存在必现崩溃。

## 二、问题清单（按优先级）

### P0：决定项目能不能用、能不能对外展示

| 编号 | 问题 | 影响 | 整改方向 |
|---|---|---|---|
| P0-1 | `BackendAPI` 保存 session 时传入 `session.to_dict()` 全量字段，包含 `session_id`，必然抛 `TypeError` | 界面处理文件后无法保存结果 | 保存前只传白名单字段，或让 `update_session` 忽略多余字段；补端到端测试 |
| P0-2 | 运行时从不加载 `.env`，`LLMConfig.from_env()` 只读 `os.environ` | 按 README 操作拿不到 API Key | 引入 `python-dotenv` 或统一在入口加载 `.env` |
| P0-3 | README/架构文档宣称 FastAPI、LangChain、LlamaIndex、Neo4j、Vue 3 等技术栈，实际仓库只有 Gradio、SQLite、requests、StepFun | 文档与实现严重脱节，无法作为真实项目展示 | 把“已实现”和“规划中”分开，改正 README clone 地址和目录说明 |

### P1：决定工程可信度

| 编号 | 问题 | 影响 | 整改方向 |
|---|---|---|---|
| P1-4 | `pytest -m "not e2e"` 有 1 个失败，测试断言仍是旧置信度公式 | CI 无法保持绿色 | 更新过期断言，将非 e2e 测试接入 CI |
| P1-5 | `datasets/raw/` 和 `datasets/long_text/` 为空，W4 报告中的 20/57 份样本无法复现 | e2e 全部跳过，指标不可信 | 提交真实样本（注意脱敏/版权）或提供可生成样本；e2e 单独 CI job 运行 |
| P1-6 | 存在多套重复且不一致的 Pipeline：`main.py` 手写阶段链、`BackendAPI._build_stages`、`PipelineFactory`、`AgentCoordinator` | 改一处漏三处，UI 与 CLI 行为不一致 | 选定统一入口，删除或真正接入死代码模块 |
| P1-7 | UI 半成品：分类/命名“加载”按钮无事件绑定，确认按钮覆盖显示框内容 | 用户无法正常查看和确认结果 | 补全按钮逻辑，确认后回显真实 session 数据，加冒烟测试 |

### P2：安全与稳定性

| 编号 | 问题 | 影响 | 整改方向 |
|---|---|---|---|
| P2-8 | `Archiver` 直接用 LLM 返回的 `course`、`category`、`new_name` 拼接路径 | 存在 `..`、绝对路径、盘符逃逸风险 | 做字符白名单过滤，`resolve()` 后校验仍在 `base_dir` 内 |
| P2-9 | `SessionStatus` 含 `paused`、`waiting_confirmation`，但 SQLite `CHECK` 未包含；BackendAPI 处理时未做状态迁移 | 状态保存不一致，状态机形同虚设 | 对齐 DB 约束与枚举，统一 `pending → processing → done` 流转 |
| P2-10 | `SQLiteStorage` 连接从不关闭，运行时代码无人调用 `close()` | 长期运行泄漏文件句柄和 WAL 文件 | 使用上下文管理器或请求级生命周期 |

### P3：后续优化

| 编号 | 问题 | 整改方向 |
|---|---|---|
| P3-11 | 只支持 StepFun provider，却宣称 DeepSeek/Claude/GPT-4o 多供应商 | 删除宣称，或实现 provider 注册表后再扩展 |
| P3-12 | `PipelineFactory` 超时控制仍是 `pass`，`BatchProcessor` 引用不存在的 `PipelineWorker.process_one` | 实现或删除，避免留下“看起来有但实际没有”的能力 |
| P3-13 | 报告指标不可复现、文档记录的是规划而非现状 | 文档只描述真实存在的能力，指标附样本和复现命令 |

## 三、整改顺序建议

1. 第一优先级：让一条真实链路端到端可用。
   - 修复 `BackendAPI` 保存崩溃。
   - 运行时加载 `.env`。
   - 补全 UI 按钮逻辑。
2. 第二优先级：让测试全绿。
   - 更新过期测试断言。
   - 明确 e2e 样本来源和运行方式。
   - 接入 CI，保证 `pytest -m "not e2e"` 必须通过。
3. 第三优先级：统一并精简架构。
   - 让 CLI 和 UI 共用同一套处理编排。
   - 删除或真正实现 `PipelineFactory`、`AgentCoordinator` 等未接线模块。
4. 第四优先级：安全与文档。
   - 归档路径校验。
   - SQLite 连接管理、状态机与 DB 对齐。
   - 最后再更新 README/架构文档，只描述真实存在的东西。

## 四、验收标准

- 按 README 操作能直接运行项目。
- `pytest -m "not e2e"` 全绿。
- 上传一个文件后，数据库和界面都有正确结果。
- README 中的技术栈、目录结构、clone 地址与仓库一致。

