# 生产 SQLite 学习查询兼容修复

2026-10-25 公网合成验收发现：课程创建、提取、审核及关系画布成功，`learning/nodes` 返回脱敏503。测试账号已通过正常预览确认删除。此前本地与Linux CI均使用较新的SQLite，未覆盖生产解释器链接的SQLite3.26.0；生产不是数据库损坏。

根因是学习投影的三个 `AS MATERIALIZED` 查询提示，生产SQLite3.26不能解析（该提示需3.35以上）。只移除提示，保留DISTINCT／UNION集合边界、Artifact索引限定、历史题目身份和同课隔离；无schema、API字段或前端资产变更。

## 已验证

- 使用实际生产Python3.11.13／SQLite3.26.0，在独立合成临时库运行新增行为回归，修复前明确RED：`near "MATERIALIZED": syntax error`。
- 同一生产运行时，隔离的修复副本通过11项：新增空／有作答学习查询、学习证据边界和既有查询工作量回归（10000条无关＋10000条相关作答、1001条映射）。生产数据未用于测试，也未安装开发依赖到生产venv。
- 本地相关34项通过，包括未引用来源删除、路径并发和查询工作量。部署前继续要求最终全量门禁及固定提交CI，公网闭环另记发布回执。

运行时回归：`uv run pytest filemate/tests/course_graph/test_runtime_compatibility.py filemate/tests/course_graph/test_learning_evidence.py -q`。在较新SQLite上通过不代表已验证旧运行时；生产部署应使用目标解释器额外执行隔离查询回归。

保留第一次DNS失败、第二次真实503、修复前RED和最终GREEN原始记录。依旧不将HTTP或合成回归当成浏览器验收、语义质量或真人学习效果。
