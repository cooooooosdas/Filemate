---
name: FileMate
description: 清爽、清晰、以真实学习记录为中心的大学生学习工作台
colors:
  cobalt-action: "#2352D3"
  cobalt-hover: "#1C42AD"
  ice-canvas: "#EDF3FC"
  white-surface: "#FFFFFF"
  sidebar: "#F8FBFF"
  elevated: "#F4F7FD"
  ink-primary: "#15264A"
  ink-secondary: "#405573"
  ink-muted: "#4D5F7B"
  line-soft: "#DCE5F3"
  line-strong: "#B2C4DF"
typography:
  display:
    fontFamily: "MiSans, HarmonyOS Sans SC, Alibaba PuHuiTi 3, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "clamp(32px, 3vw, 42px)"
    fontWeight: 700
  body:
    fontSize: "17px"
    lineHeight: 1.75
  label:
    fontSize: "15px"
rounded:
  control: "10px"
  panel: "14px"
  dialog: "16px"
---

# FileMate 当前设计

2026-10-16，按用户确认，以答辩PPT第6页今日安排和第10页教练构想为主要参考。保留现有蓝色LOGO和业务数据，采用浅冰蓝工作台、白色阅读面板、钴蓝操作和主次分栏。此文替代早期自然绿/小字号规范；详见 `design-system/filemate/MASTER.md`。

## 版式

- 顶部仅显示当前位置、添加资料、账号、查找与设置；七个主功能统一放在左侧导航，当前分组展开子功能。
- 首页以学习任务和一言为起点；今日学习以欢迎区、执行清单为主列，真实计数和时间预算为辅助列。
- 面试教练将人物/本地媒体预览放在辅助列，训练问题和回答放在主要阅读列；记录与复盘接在其后。
- 窄屏收起侧栏，今日安排先概览与时间预算，再执行清单；不隐藏关键操作和状态。

## 表达与素材

- 标题32–42px，模块24px，正文/操作17px，说明16px，辅助15px；使用系统中文无衬线字体，不新增远程字体。
- 功能图标沿用现有Tabler按需SVG出口。StudyMotif是原创矢量任务纸张与书页插图，无外部图片依赖；人物素材保持原产品资源。
- 不采用紫粉渐变、Emoji功能图标、循环装饰和无依据的进度/评分。浅蓝色块承担分组，留白和分隔线承担层级。
- 页面和面板仅有限过渡，遵守减少动画设置；表单与阅读保留对比度、可见焦点和44px操作区域。

## 交互

- 保留原URL、别名和功能开关；当前子页与所属父级用不同高亮和aria-current语义。
- 首页今日任务进入具体计划，选择已保存面试恢复对应会话，内部ID同步不重建练习。
- 未提交文字、准备修改、本地录音录像在离开前确认；保存失败可重试。授权、删除预览和真实证据边界不得因简化界面被移除。
- 合成演示数据明确标记；无数据显示待评估，不复制PPT概念图中的统计。

## 证据

交付与验证范围：`docs/PPT_WORKSPACE_REDESIGN_2026-10-16.md`。原始PPT未改动；页面为可交互Vue组件，未把构想截图贴成背景。
