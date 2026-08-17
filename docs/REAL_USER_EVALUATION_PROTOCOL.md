# FileMate 真实用户评测执行协议

## 目标

用真实但匿名的数据回答三个问题：检索引用是否相关、学习闭环是否节省时间、学生是否愿意持续使用。演示数据和示例 CSV 不计入正式结果。

## 最小样本

- 30 名大学生，覆盖至少 3 个专业。
- 100 份已获授权的课程资料。
- 至少 300 次检索引用相关性标注。
- 每名学生完成一次 20 分钟任务和前后测。

## 单次流程

1. 告知参与者数据默认保存在本机，可随时退出；禁止上传身份证、联系方式、成绩单等敏感资料。
2. 参与者导入一份自己的课程资料，完成一次检索、一次练习和一次今日学习任务。
3. 对检索引用点击“相关”或“不相关”。系统只保存目标哈希、排名、检索分数、问题长度和评分。
4. 记录任务是否完成、耗时、前后测得分及 SUS 问卷；使用随机参与者编号，不记录姓名和学号。
5. 在“成长数据”导出匿名 CSV，用 `evaluation/analyze_feedback.py` 生成统计报告。

## 命令

```powershell
python evaluation/analyze_feedback.py filemate-anonymous-feedback.csv --sample-kind real --output _working/real-feedback-report.json
python evaluation/analyze_study.py evaluation/datasets/user_study.csv --output _working/real-user-study-report.json
```

## 通过门槛

- 检索引用正向率不低于 75%，同时报告 95% Wilson 区间。
- 前后测平均提升不低于 15%。
- 平均节省时间不低于 20%。
- SUS 不低于 70。
- 所有正式结论必须标注样本量、日期和“真实/合成”属性，不得用示例数据冒充实测结果。
