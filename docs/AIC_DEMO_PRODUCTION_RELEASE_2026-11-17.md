# AIC 答辩首页与复盘 P1 生产发布回执

日期：2026-11-17。已部署至 https://filemate.asia/ 。网页提交 `8566356a8088885035ae0244c7886a4cb8b79171`，后端保持 `c28dc2b1ae7c5cbf047321286eb09f73223dac46`，业务 schema 36／治理 schema 3。

## 结果

- 首页恢复深蓝曲线、大字标题、浅金色学习动作和右侧一言，原有学习入口与随机语句来源保留。
- 原审查 P1 的公开入口问题已关闭：正式构建默认加载 `ReviewWorkspace`，公网错题页新版工作区 1 个、旧版 0 个；资源摘要与候选包一致。`write_enabled=true`，AI 分析开关保持原值。
- [精确提交的干净 Linux CI](https://github.com/cooooooosdas/Filemate/actions/runs/44075664039)成功：后端 2191 通过／19 跳过／5 排除，前端 448 通过。类型、构建、体积及评测工具检查通过。此为工程回归，不代表真实学生效果。
- 公网首页、登录、学习工作区、知识图谱、错题复盘、今日行动，分别在 390px／1440px 检查，共 12 组通过；无未捕获异常、控制台错误、HTTP 错误或横向溢出。一言与主操作可见。
- 使用全新无登录状态的临时访客，只浏览其自有空空间。未使用真实账号，未上传资料、调用模型或执行学习记录写入。答辩完整作答链仍以本轮先前隔离合成账户的本地 10 组验收为证，不冒称已在生产写入验证。

## 发布与回退

仅更新静态前端；没有后端重启、数据库迁移、生产配置或服务端功能开关变更。API MainPID 8293，NRestarts 0，health／ready 正常。

候选 456 个运行文件校验通过，保留 644 个旧资源，激活时 28 个入口资源及缓存头检查通过。正式目录：`/clouddream/nginx-proxy-manage/data/filemate/releases/alpha4-8566356a8088`。

发布包 SHA256：`6ce4f7ffd7a4b72f9c050bbffe6cf44b6e80c01f9cbcb7d01fb1b05e42609acd`。

旧版 `releases/alpha4-406f01ef5594` 保留。需要回滚时以临时符号链接和原子替换恢复网页 current，再检查 release.json、health 和 ready；保留后续用户数据。服务器回执：`/opt/filemate/incoming/alpha4-8566356a8088-web/rollback.json`。

## 证据与边界

本机证据：`D:/FileMate-Project/_working/aic-p1-hero-20261117/production/`，含 CI 日志、包清单、摘要、stage／activation／rollback 回执、公网 JSON 与桌面／手机截图。

首次浏览器脚本把所有 POST 一律阻止，误拦 `/api/learning/orchestrator/goal-options`，导致两条测试侧错误。已核对 API_SPEC 与实现，该接口只读取当前空间的一页目标目录；仅放行此只读查询后完整重跑 12 组通过。初始失败证据仍保留为 `initial-harness-production-browser.json`，不列为产品缺陷，也不隐去。

历史 P2 容量、真人学习效果与实体设备限制仍按原记录延期，不因本次界面发布而宣称解决。原有 23 份用户测试改动未纳入提交或发布。
