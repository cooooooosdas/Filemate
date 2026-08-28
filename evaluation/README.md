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

## 用户研究分析模板

```powershell
uv run python evaluation/analyze_study.py `
  --annotations evaluation/datasets/retrieval_annotations.example.csv `
  --study evaluation/datasets/user_study.example.csv `
  --output _working/user-study-example-report.json
```

脚本计算标注一致率、Cohen's Kappa、学习正确率增益、节省时间、配对效应量 Cohen's dz 和 SUS。仓库中的 CSV 是合成示例，只用于验证流程；采集真实数据时必须使用匿名参与者编号，并取得知情同意。

## 产品内匿名反馈

知识库检索结果支持“相关/不相关”标注，成长页可导出不含原问题、文件名和用户身份的 CSV。统计命令：

```powershell
uv run python evaluation/analyze_feedback.py `
  evaluation/datasets/product_feedback.example.csv `
  --output _working/product-feedback-example-report.json
```

示例 CSV 是合成数据，只验证统计流水线；正式结果按 `docs/REAL_USER_EVALUATION_PROTOCOL.md` 采集。
