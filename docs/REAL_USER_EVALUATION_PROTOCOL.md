# FileMate 真实用户评测执行协议

## 目标

用真实但匿名的数据回答四组问题：检索引用是否可靠、按需多 Agent 是否优于单 Agent、多模态面试是否提升训练质量、学习伙伴反馈是否促进执行。演示数据和示例 CSV 不计入正式结果。

## 最小样本

- 30 名大学生，覆盖至少 3 个专业。
- 100 份已获授权的课程资料。
- 至少 300 次检索引用相关性标注。
- 每名学生完成一次 20 分钟任务和前后测；对照实验每个条件至少 15 人。

## 四组实验设计

| 研究问题 | A 组 | B 组 | 主要指标 | 必须控制 |
| --- | --- | --- | --- | --- |
| 检索引用是否可靠 | 整篇截断/基础检索 | FileMate 分块检索 | Recall@1/3、MRR、引用正确率、响应时间 | 同一资料、同一问题、相同设备 |
| 多 Agent 是否有效 | 单 Agent 完成全部任务 | 按需调用规划/资料/教练/评价/安全角色 | 任务完成率、幻觉率、耗时、调用数、成本 | 同一模型、提示预算与任务顺序随机 |
| 多模态面试是否有效 | 文字回答 | 摄像头本地录像 + 语音回答 | 完成率、复练提升、导师盲评、系统—导师相关性、停顿与语速 | 不做颜值、情绪或性格判断 |
| 学习伙伴是否促进坚持 | 普通文字提醒 | 由真实学习证据驱动的形象反馈 | 任务完成率、到期复习率、次日返回率 | 不用羞辱文案，不用虚假成长值 |

参与者按匿名编号随机分组。面试由两名教师或企业导师盲评；标注分歧先保留，再由第三人裁决。摄像头录像默认只存在参与者浏览器内存，研究表只记录分数和行为计数，不收集原始视频或逐字稿。

## 单次流程

1. 告知参与者可随时退出：本地/桌面运行时资料保存在本机，公开网站运行时资料保存在服务器的访客隔离空间；摄像头录像仍默认留在浏览器内存。禁止上传身份证、联系方式、成绩单等敏感资料。
2. 参与者导入一份自己的课程资料，完成一次检索、一次练习和一次今日学习任务。
3. 对检索引用点击“相关”或“不相关”。系统只保存目标哈希、排名、检索分数、问题长度和评分。
4. 记录任务是否完成、耗时、前后测得分及 SUS 问卷；使用随机参与者编号，不记录姓名和学号。
5. 在“成长数据”导出匿名 CSV，用 `evaluation/analyze_feedback.py` 生成统计报告。
6. 多 Agent、面试和学习伙伴实验分别复制三个 `.template.csv`，只填匿名编号和数值字段；禁止写姓名、学号、文件名、问题原文或回答原文。

## 命令

```powershell
python evaluation/analyze_feedback.py filemate-anonymous-feedback.csv --sample-kind real --output _working/real-feedback-report.json
python evaluation/analyze_study.py --annotations evaluation/datasets/retrieval_annotations.csv --study evaluation/datasets/user_study.csv --sample-kind real --output _working/real-user-study-report.json
python evaluation/analyze_competition_trials.py --agent evaluation/datasets/agent_ab.csv --interview evaluation/datasets/interview_ab.csv --companion evaluation/datasets/companion_ab.csv --sample-kind real --consent-confirmed --output _working/competition-trials-report.json
```

真实前后测表在示例字段之外增加 `score_max`、`study_date`、`consent_confirmed` 和匿名 `discipline_code`；每名参与者只保留一条配对记录。真实标注及三类对照实验也逐行记录 `sample_kind=real`、实际 `study_date`、`consent_confirmed=1`，空白模板已包含这些字段。每题恰好两名独立标注者；可回答题的页码为正整数，不可回答只填空值、NA或0。标注分歧保留，第三人裁决另行记录，不将第三条记录混入双人一致性计算。

先用 `evaluation/prepare_beta.py --study <实际匿名前后测CSV> --tasks <实际匿名任务CSV> --sample-kind real --output _working/<新采集包目录>` 完整校验再导出。任务编号、计数上限、重复记录及参与者/条件对应须合法；平行实验同一人不能跨组计数。报告日期是实际测量范围，生成时间另列；按条件分别报告参与者配对变化的探索性95%区间，不将多任务记录当独立学生。格式通过与样本门槛通过均不能替代团队过程审查，详见[工具合同](../evaluation/README.md)。

## 通过门槛

- 检索引用正向率不低于 75%，同时报告 95% Wilson 区间。
- 正确率相对前测平均正确率增加不低于15%，同时报告百分点变化和前后测满分；前测平均正确率为0时相对增幅不可计算。
- 平均用时相对前测平均用时节省不低于20%，前测用时必须大于0。
- SUS 不低于 70。
- 所有正式结论必须标注样本量、日期和“真实/合成”属性，不得用示例数据冒充实测结果。
- 多 Agent：任务完成率提高、幻觉率下降；同时完整报告耗时、模型调用数和成本，不能只报优势。
- 多模态面试：系统分与双导师均分的相关性达到 0.70 以上，并报告平均绝对误差；样本不足时显示“待评测”。
- 学习伙伴：到期复习完成率或次日返回率有提升；未达到每组 15 人前不得宣称有效。

## 2026-10-02 采集状态

负责人已确认尚未采集真实学生试用与导师盲评。当前示例、工程作答与自动化浏览器操作均不计入真实样本。先开展10名种子用户Beta，解决真实反馈后再按本协议扩展到30名、3专业、100份授权资料和300次引用标注；统计工具通过不能替代试用完成。
