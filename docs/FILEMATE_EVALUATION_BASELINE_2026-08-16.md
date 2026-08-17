# FileMate 离线评测基线摘要

> 生成日期：2026-08-16
> 基线 commit：`049d7d6`
> 性质：合成工程基线，不代表真实教学效果或真实用户研究结论。

## 指标

| 项目 | 用例数 | 指标 | 结果 |
|---|---:|---|---:|
| 本地词法检索 | 12 | Recall@1 | 1.0 |
| 本地词法检索 | 12 | Recall@3 | 1.0 |
| 本地词法检索 | 12 | MRR | 1.0 |
| 面试本地降级评分 | 5 | 区间通过率 | 1.0 |

## 复现命令

```powershell
$env:PYTHONPATH='.'
.venv\Scripts\python.exe evaluation/run_evaluation.py --output _working/evaluation-report-2026-08-16.json
```

## 边界说明

- 12 个检索用例和 5 个面试用例均为合成数据。
- 正式竞赛结论必须遵守 `docs/REAL_USER_EVALUATION_PROTOCOL.md` 的 30 人门槛。
- 真实用户数据未采集前，一律标记为“待评测”。
