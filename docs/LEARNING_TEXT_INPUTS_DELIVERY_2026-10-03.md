# DEV-01 学习资料入口交付

2026-10-03。从已固定的 `UI-2026.10.03-r1` 本地视觉基线继续开发，软件仍为 `1.3.0-alpha.1`。本卡补齐 Markdown 与代码学习资料入口，复用现役解析、资料、引用、会话和知识图谱，不新增 schema、端点或模型 Provider。

## 实际行为

- 学习工作区可添加 `.md/.markdown/.c/.cpp/.h/.hpp/.py/.java/.js/.ts`，后缀不区分大小写；课件与 TXT 格式保留。
- 新增格式以 UTF-8 纯文本读取。Markdown 的标记与代码作为文字阅读，不渲染 HTML、不执行或编译代码；导入、阅读与创建会话不调用模型。
- 内容哈希复用现有资料；保存的原文、检索片段、会话与图谱仍指向同一 Source。图谱须核对确认，重开后保留；无作答继续显示待评测。
- 25 MiB 文件限制、解析前 500000 字符限制沿用现役合同。空白或编码错误返回 422 并清理此次副本，其他扩展名返回 400，超限返回 413。重复上传清理新副本并保留原资料。
- `/process` 分类归档上传格式保持原合同；编程评测仍由专用隔离评测入口负责。
- 知识库刷新保护同步收尾：存在未保存编辑或正在保存时就地提示并阻止顶部刷新，避免丢失修改。

## 变更范围

解析注册：`filemate/perception/parsers/__init__.py`、`txt.py`；学习上传校验：`server.py`；入口：`LearningWorkspace.vue`；刷新保护：`Knowledge.vue`；合同：`filemate/docs/API_SPEC.md`、README；回归：`test_server_persistence.py`、`test_graph_api.py`、`workspace.mjs`。LOGO、配色、首屏预算、文件确认/撤销和模型授权保留。

## 验收证据

证据目录：`_working/learning-text-inputs-20261003/`。首次默认门禁的后端 758 项与前端 18 项通过，但前端构建和浏览器截图遇到 D 盘空间不足；失败日志保留。随后恢复记录因执行中断未形成完整父级报告，不能作为通过依据。迁移本次自建依赖缓存后，以新候选重新验收。

760后端、18前端及类型/构建/原体积门禁通过；最终同包46项TLS父级/91路径、12视觉、17归档、25学习工作区、18知识库通过。后端18项跳过、5 deselected、3 warnings保留；实际模型输出为本地合成HTTP夹具，有限128次读取不代表完整服务器容量。最终源码与静态资源指纹固定于`version-freeze-complete.json`，前端副本为`frontend-complete`，生产证据为`production-complete`；不累加不同快照的通过数。

额外体积复读最初用了错误脚本名，两份错误日志保留；按package.json中的`node scripts/check-bundle.mjs --dist dist`重跑退出0。默认门禁和TLS运行器各自使用正确命令并通过。

## 边界与后续

图片/OCR 导入不在本卡，普通教材的提取质量、关系覆盖与真实学习收益仍待验证。模型产物仅用于明确的本地合成 HTTP 合同夹具；真实学生与导师数据仍为 0。现役格式支持不表示所有旧版 Office 环境都具备解析依赖。

下一卡 UI-02 整合知识图谱的「选资料 → 提取 → 核对确认 → 阅读证据 → 学习路径」界面。先处理该模块，随后串行处理编程、面试、求职；其余运维、平台、产品化和正式发布要求保留在全项目账本。

## 复跑

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
uv run pytest filemate/tests/test_server_persistence.py -q -k "learning_text or learning_source or classification_upload"
uv run pytest filemate/tests/test_graph_api.py -q -k text_learning_import
uv run python scripts/acceptance/gateway_preflight.py `
  --caddy _working/operations-preflight-20261003/tools/caddy.exe `
  --web-root <本卡最终编译的隔离前端路径> `
  --out <尚不存在的_working子目录> `
  --visual-checks --review-checks --workspace-checks --layout-checks
```
