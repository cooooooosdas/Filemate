# v1.3.0 RC 验收准备清单

状态：2026-10-02 工程尾项交付，正式发布待团队冻结。此清单没有发布授权；版本仍为 `1.3.0-alpha.1`、schema v24。

## 工程证据

- [ ] 确定唯一代码快照；提交全部拟交付变更，记录提交 SHA、版本与源码指纹。
- [ ] 对该快照运行 `scripts/verify.ps1 -IsolateFrontend`：Ruff、非真实资料后端测试、前端测试、类型检查和构建；列出跳过及未执行项。
- [ ] 对最终编译资源完成六条学习主流程、五模块和 B2 浏览器验收；数字人/摄像头与原生判题保留专用证据和运行限制。
- [ ] 核对 migration 幂等、资料隔离、删除/撤销、确认与禁用开关；不修改已发布迁移。
- [ ] 当前提交的远端 CI、Python 包资源、桌面壳/安装包范围和发布说明一致；不沿用别的提交的成功状态。
- [ ] 网站与本地版本同步后，抽查健康、主页面/静态资源、最新接口与浏览器闭环，记录延迟、错误和服务器负载。

当前已经通过的证据及范围见 [B2/B3交付](B2_B3_ENGINEERING_CLOSEOUT_2026-10-02.md) 和[总验收](INTEGRATED_AUDIT_2026-10-02.md)。未提交工作区、旧线上版本、不同日期浏览器测试分别标注；这些历史通过项不能勾选为“最终冻结快照通过”。

## 真实研究与人工签核

- [ ] 团队完成招募、知情说明、退出机制及实际授权记录；实名对应表不进入仓库或统计包。
- [ ] 至少10名真实学生完成种子 Beta；该门槛不能替代30名正式实验。
- [ ] 正式实验30名、3专业、100份授权资料、300次引用标注，平行对照各条件至少15名；过程和样本门槛均需审查。
- [ ] 组织双导师盲评和分歧保留，专家校准逐维度实际配对；不能使用合成评分或本地回退冒充导师结果。
- [ ] 报告同时列出样本量、实际测量日期、`sample_kind`、区间、未达到的指标与局限，团队确认哪些结论可公开使用。
- [ ] 团队记录每项审核者、实际审核日期与依据，再决定版本标签和发布；工具输出不替代人工审批。

截至2026-10-02，上述真实采集均尚未开始，当前不勾选。

## 复跑只读准备工具

先保存待验证代码指纹，再运行门禁，最后汇集实际证据。所有证据使用新路径，避免覆盖旧的失败记录：

```powershell
uv run python scripts/acceptance/release_readiness.py --capture-baseline _working/rc-next/source-baseline.json
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend *> _working/rc-next/verify.log
uv run python scripts/acceptance/release_readiness.py `
  --baseline _working/rc-next/source-baseline.json `
  --gate-log _working/rc-next/verify.log `
  --browser-summary _working/b2-b3-20261002/browser-b2/summary.json `
  --synthetic-report _working/synthetic-learning-20261002/run5/results.json `
  --output _working/rc-next/release-readiness.json
```

上例先保存新基线和门禁日志，使用本轮浏览器/合成证据作复核；后续版本须替换为对应代码的实际场景证据。工程输入在测试期间不能改变，保留门禁退出码与原日志；需要隔离临时文件时另设项目 `_working` 中的 TEMP/TMP。正式数据取得后可追加 `--study <匿名前后测CSV> --expert <实际导师配对CSV>`；研究输入按真实模式严格校验，合成不能晋升为真实。准备命令退出0表示报告生成成功；报告内 `engineering_status` 才表示工程证据是否通过。`status=pending_team_release_review` 代表等待团队冻结；`--require-ready` 在人工冻结未完成时退出1。脚本只读源数据，不修改版本、标签、服务或发布状态。
