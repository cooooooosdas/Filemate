# Prompt 库

> 各模块用到的 Prompt 模板汇总，持续迭代。
>
> - v1 → v2：W2 感知层反馈后迭代（汤新阳提供样本）
> - v2 → v3：W3 完成分类/抽取/里程碑/命名四大 Prompt
> - v3 → v4：W4 集成反馈 ← **进行中，见下方 W4 记录**
> - v4 → v5：W6 最终版（归档于此）
>
> TODO(张金宝): W6 前整理完毕。

---

## 各 Prompt 当前版本

| Prompt | 文件 | 版本 | 最近更新 |
|---|---|---|---|
| 分类 | `filemate/understanding/prompts/classify.md` | v2 | W3 |
| 实体抽取 | `filemate/understanding/prompts/extract.md` | **v3** | **W4（2026-07-31）** |
| 多里程碑识别 | `filemate/understanding/prompts/milestone.md` | v1 | W3 |
| 命名规范 | `filemate/understanding/prompts/naming.md` | v1 | W3 |

关键词规则库：`filemate/understanding/rules/keywords.json` v0.3（7 类 125 词，W3）

---

## W4 联调反馈与 Prompt 迭代（2026-07-31）

依据：`docs/联调测试报告_W4.md`（20 份样本，五模块串联实测）

### 已完成

**`extract.md` v2 → v3** —— 修复两类导致整份样本字段全丢的失败：

| 问题 | 证据 | 改动 |
|---|---|---|
| `extra_entities` 嵌套子对象撑爆 `max_tokens`，JSON 被截断 | 日志出现 `'{... "contact": {'` 断在中途 | 新增约束：必须扁平、值只能是字符串或数字、最多 6 个键 |
| 非课程类文件不给主办方 → 命名第一段填「未分类」 | 20 份中 11 份第一段为「未分类」 | 新增约束：竞赛/大创/行政通知必须给出 `organizer` |

配套代码改动：`EntityExtractor` 重试 2 → 3 次、`max_tokens` 提至 4000、
新增 `_flatten()` 兜底压平；`Namer.generate()` 新增可选参数 `extra_entities`
用于取主办方补位。

实测收益：命名通过率 **15% → 75%**，零占位率 15% → 45%。

### 待处理（任务 8，W5 初）

| # | 问题 | 证据 | 拟改 |
|---|---|---|---|
| 1 | 「报名表」被误判为竞赛通知 | `团委干事报名表.docx` → 竞赛通知（规则命中，置信度 0.55），真实为待确认 | `keywords.json`：把「报名表」从竞赛通知移出，或加入待确认 |
| 2 | 大创通知与竞赛通知混淆 | 三份创新大赛 PPT 模板内容近似，前两份判对、第三份判为竞赛通知（LLM，0.90） | `classify.md`：加强大创 vs 竞赛的区分说明 |
| 3 | `task_description` 抽取为空 | `2025-2026-1学期体育评定标准.pdf` 抽取为空，命名回退用文件名 | `extract.md`：补充「标准/规定」类文件的抽取策略 |
| 4 | `Classifier` LLM 空响应重试不足 | 日志 `LLM 分类在 2 次尝试后全部失败`，2 份样本置信度 0.00 | 代码：重试 2 → 3 次，与 `EntityExtractor` 对齐 |
| 5 | `deadline` 召回仅 45% | 部分文件本身无截止时间，需区分「抽不出」与「本来没有」 | 需先人工标注 ground truth 才能定目标 |

目标：`task_description` 召回 **84.91% → 95%**

> ⚠️ 起点用实测值 84.91%（53 份样本）。此前文档中的 92% 是 26 份样本时期的
> 旧数据，已过期。
