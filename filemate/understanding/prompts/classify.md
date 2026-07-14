# 分类 Prompt

## 输入
- 文件文本内容（前 2000 字）
- 文件名 + 后缀

## 输出（严格 JSON）
```json
{
  "category": "课件 | 作业 | 竞赛通知 | 考试通知 | 待确认",
  "confidence": 0.0,
  "course_name": "课程名或 null",
  "reason": "简短判断依据"
}
```

## TODO(张金宝)
填写完整提示词，迭代至 v5 最终版后归档至 `PROMPT_LIB.md`。
