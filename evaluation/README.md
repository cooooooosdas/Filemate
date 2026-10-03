# FileMate 离线评测

该目录提供可提交、可复现、无需外部模型密钥的基础评测证据。

```powershell
uv run python evaluation/run_evaluation.py --output _working/evaluation-report.json
```

当前包含：

- 资料检索：41 组合成跨课程查询，报告 Recall@1、Recall@3、MRR 与逐例命中页；
- 模拟面试：5 档回答质量，验证隐私模式下本地评分的稳定区间；
- 输出为机器可读 JSON，后续可由 CI 和竞赛展示看板直接消费。

该小型合成集合只用于工程回归，不代表真实用户意图或教学效果结论。正式竞赛报告还需扩充匿名真实样本、双人标注一致性和与基线系统的对照实验。

2026-08-28 可复现合成基线：Recall@1 = 95.12%、Recall@3 = 100%、MRR = 97.56%。这些数字只能作为代码回归证据，不得写成真实用户研究结论。

## 用户研究分析模板

```powershell
uv run python evaluation/analyze_study.py `
  --annotations evaluation/datasets/retrieval_annotations.example.csv `
  --study evaluation/datasets/user_study.example.csv `
  --output _working/user-study-example-report.json
```

脚本计算标注一致率、Cohen's Kappa、学习正确率增益、节省时间、配对效应量 Cohen's dz 和 SUS。仓库中的 CSV 是合成示例，只用于验证流程；采集真实数据时必须使用匿名参与者编号，并取得知情同意。

2026-10-02 总验收已加强数据合同：默认 `--sample-kind synthetic`；真实研究显式指定 `--sample-kind real`。研究表另须包含 `score_max`、`study_date`、`consent_confirmed=1`、`discipline_code`，真实标注表每行须标记 `sample_kind=real`。拒绝重复参与者、同一标注者重复计数、缺失双人标注、未来日期、非法SUS和非有限数字，以及将 `.example` / `.template` / `.synthetic` 文件标记为真实。

从空白 `datasets/user_study.template.csv` 与 `datasets/retrieval_annotations.template.csv` 复制采集表，取得实际授权后填入真实匿名记录；仅改变文件名或标记不构成真实研究。

按实验条件分别汇总，报告相对正确率增幅、百分点变化和时间节省百分比；无满分时不推断正确率，常量标签的 Kappa 和零方差 Cohen's dz 输出 `null`。30人、3个专业、对照条件各15人只代表样本门槛，仍需审查知情同意、采集过程、对照设计和数据真实性，不能因此断言学习有效。最新工程与真实证据边界见 [总验收](../docs/INTEGRATED_AUDIT_2026-10-02.md)。

## 国奖对照实验采集包

以下空白模板只定义字段，不含任何示例结果：

- `datasets/agent_ab.template.csv`：单 Agent 与按需多 Agent；
- `datasets/interview_ab.template.csv`：文字与多模态面试；
- `datasets/companion_ab.template.csv`：普通提醒与学习伙伴反馈。

收集真实匿名数据后，复制并去掉文件名中的 `.template`，再运行：

```powershell
uv run python evaluation/analyze_competition_trials.py `
  --agent evaluation/datasets/agent_ab.csv `
  --interview evaluation/datasets/interview_ab.csv `
  --companion evaluation/datasets/companion_ab.csv `
  --sample-kind real --consent-confirmed `
  --output _working/competition-trials-report.json
```

分析器会在任一条件少于 15 名参与者时输出 `pending_more_samples`。这代表“待评测”，不能当作产品效果结论。

对照分析同样默认合成，真实模式需明确确认匿名化与知情同意；默认运行不再自动将任意CSV写成 `real_anonymous_user_trial`。空白模板不构成实验记录，重复任务也不能增加独立参与者数量。

## B3 匿名采集校验与导出

2026-10-02 工程收口新增统一 CSV 合同、Beta 导出和探索性区间。空白模板仍没有数据；只复用已有 `.example.csv` 检验导出，不生成新参与者、SUS答案或专家评分。

```powershell
uv run python evaluation/prepare_beta.py `
  --study evaluation/datasets/user_study.example.csv `
  --output _working/新的Beta合成导出目录
```

默认 `synthetic`。实际采集后使用 `--sample-kind real`；可加 `--tasks <匿名任务CSV>`，字段与 `agent_ab.template.csv` 一致。工具先校验整套输入及参与者/条件对应，再新建目录导出 UTF-8 BOM `user_study.csv`、可选 `anonymous_tasks.csv` 和 `report.json`；已有目录拒绝覆盖。统计JSON不包含参与者编号，匿名CSV保留用于配对的短编号。输入前后 SHA256 核对，来源指纹保留在报告中；匿名格式和同意声明不能代替团队核实实际身份隔离、招募与授权。

CSV 拒绝空/重复表头、额外身份或自由文本字段、缺失必填值和行宽错误。三类对照实验现在分别要求 `task_id` / `attempt_id`（伙伴为每人一条）、整数计数、合理分母上限；同一参与者不得跨平行对照条件，同一任务/面试不得重复。不同任务可同属一人，但不增加独立参与者样本数。

真实前后测、引用标注与三类对照实验，每行须包含 `sample_kind=real`、实际 `study_date` 和 `consent_confirmed=1`；前后测另需满分与匿名专业代码。相应空白模板已补齐。不可回答的引用页码只接受空值、`NA` 或 `0`，归一为同一无引用标签；可回答必须为正整数页码。专家配对沿用六字段及 `expert_real`，拒绝含额外身份内容、非法行宽或示例文件晋升真实。

报告增加生成时间、实际测量日期范围、日期覆盖数、记录数及来源 SHA256；缺少测量日期的合成示例范围为 `null`。区间按条件分别计算：前后测以参与者配对变化为单位；多任务先按参与者平均再重采样，明确区分任务均值和参与者均值权重。固定种子42、2000次重采样的95% percentile bootstrap 仅供探索；少于2人时为 `null`，零观察方差明确标记，不作显著性或因果结论。单位包括原始分数、百分点、分钟、SUS点和比例，不能互换。

RC 准备与团队待办见[清单](../docs/RC_ACCEPTANCE_CHECKLIST.md)、[版本说明草稿](../docs/RELEASE_NOTES_V1_3_0_DRAFT.md)及[B2/B3交付](../docs/B2_B3_ENGINEERING_CLOSEOUT_2026-10-02.md)。正式模式30人门槛只表示可进入团队研究审查，10人Beta不等于正式实验。

## 产品内匿名反馈

知识库检索结果支持“相关/不相关”标注，成长页可导出不含原问题、文件名和用户身份的 CSV。统计命令：

```powershell
uv run python evaluation/analyze_feedback.py `
  evaluation/datasets/product_feedback.example.csv `
  --output _working/product-feedback-example-report.json
```

示例 CSV 是合成数据，只验证统计流水线；正式结果按 `docs/REAL_USER_EVALUATION_PROTOCOL.md` 采集。
