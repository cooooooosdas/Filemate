---
name: FileMate
description: 开放、自然、可信的大学生学习工作台
colors:
  forest-action: "#2F7D55"
  forest-action-hover: "#256847"
  paper-canvas: "#F5F8F4"
  white-surface: "#FFFFFF"
  sage-sidebar: "#EEF5EF"
  sage-elevated: "#EDF4EE"
  ink-primary: "#183229"
  ink-secondary: "#4D655B"
  ink-muted: "#6D8077"
  line-soft: "#D7E3D9"
  line-strong: "#BFD0C3"
typography:
  display:
    fontFamily: "MiSans, HarmonyOS Sans SC, Alibaba PuHuiTi 3, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "clamp(27px, 3vw, 40px)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  body:
    fontFamily: "MiSans, HarmonyOS Sans SC, Alibaba PuHuiTi 3, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: "MiSans, HarmonyOS Sans SC, Alibaba PuHuiTi 3, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  control: "10px"
  panel: "14px"
  dialog: "16px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.forest-action}"
    textColor: "{colors.white-surface}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
  button-primary-hover:
    backgroundColor: "{colors.forest-action-hover}"
    textColor: "{colors.white-surface}"
    rounded: "{rounded.control}"
  panel:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.panel}"
    padding: "22px"
---

# Design System: FileMate

## Overview

**Creative North Star: “日光学习台”**

FileMate 像一张在自然日光下持续更新的学习工作台。轻微偏绿的纸面画布降低长时间阅读的刺激，白色表面保持内容清楚，自然森林绿只用于品牌、选中和关键行动。界面表达克制而开放，信息密度服务于操作，不模仿营销落地页。

**Key Characteristics:**

- 浅色、低饱和、自然绿，不提供暗色主界面。
- 真实数据与状态优先，装饰保持稀少。
- 单一图标家族、清楚分栏和非对称工作台布局。
- 空、错、等待、完成均有文字说明和下一步操作。

## Colors

自然森林绿是唯一品牌强调色；鼠尾草绿负责大面积安静区域，深绿墨色负责阅读对比。

**The One Green Voice Rule.** 品牌强调只使用 Forest Action，警告和错误色只表达状态，不参与装饰。

**The Open Canvas Rule.** 页面画布使用 Paper Canvas，主内容表面使用 White Surface，避免整屏纯白和高饱和绿色铺底。

## Typography

**Display Font:** 中文系统无衬线栈
**Body Font:** 中文系统无衬线栈
**Label/Mono Font:** `ui-monospace, SFMono-Regular, Consolas, monospace` 仅用于数字、版本和度量

标题通过字重与紧凑字距建立秩序；正文保持 1.75 行高和自然中文标点节奏，不远程加载未确认授权的字体。

### Hierarchy

- **Display**（700，`clamp(27px, 3vw, 40px)`，1.2）：工作台首要任务。
- **Headline**（650，18–20px，1.3）：页面和面板标题。
- **Body**（400，14px，1.75）：说明与学习内容，建议不超过 75 个西文字符的等效行宽。
- **Label**（600，11–12px）：状态、元数据和控件标签；不使用全大写英文装饰。

## Layout

桌面应用壳由 252px 浅绿侧栏、72px 白色页头和滚动内容区组成。首页使用 7:5 非对称网格，主要任务与资料在左侧，学习闭环与画像在右侧。900px 以下侧栏变为抽屉；700px 以下操作和数据条改为单列或 2 列，点击区域至少 44px。

间距以 4 / 8 / 16 / 24 / 32px 为主。相关内容紧凑，面板之间保持 20–24px，标题上方空间大于下方空间。

## Elevation & Depth

系统以色面和 1px 分隔线建立层级，默认面板没有阴影。弹窗可使用极轻环境阴影，但不能同时依赖粗边框与重阴影。

**The Flat-by-Default Rule.** 操作平台的内容层级来自版式、色面和边界，禁止发光描边与悬浮玻璃装饰。

## Shapes

控件使用 10px 圆角，面板使用 14px，弹窗使用 16px。小状态标签允许 7–8px；圆形只用于状态点或明确的单图标控件。Logo 的文档与确认符号是唯一品牌专用几何形态。

## Components

### Buttons

- **Primary:** 自然森林绿实底、白字、10px 圆角；同一操作区只保留一个主按钮。
- **Secondary:** 白色或透明背景、强边界色和深绿文字。
- **Hover / Focus:** 悬停加深绿色；键盘焦点使用 2px Forest Action 外轮廓，偏移 2px。

### Cards / Containers

- **Corner Style:** 14px 面板圆角。
- **Background:** 白色主表面或浅鼠尾草分组表面。
- **Shadow Strategy:** 默认无阴影。
- **Border:** 1px Line Soft。
- **Internal Padding:** 20–24px。

### Inputs / Fields

白色或 Sage Elevated 背景，1px Line Strong 边框，10px 圆角。焦点将边框切换为 Forest Action，并保留可见轮廓；错误状态同时使用图标、文字与语义色。

### Navigation

侧栏使用 Sage Sidebar；默认项为 Secondary Ink，悬停使用 Sage Elevated，当前项使用浅绿底、Forest Action 文字与边框。移动端关闭时从可访问性树移除，打开后由遮罩承接焦点语境。

## Do's and Don'ts

### Do:

- **Do** 用真实资料、任务和学习证据建立页面视觉焦点。
- **Do** 统一使用 `@element-plus/icons-vue`，同时显示文字状态。
- **Do** 为 loading、empty、error、retry 和 disabled 提供完整体验。

### Don't:

- **Don't** 使用暗色主界面、紫粉 AI 渐变、霓虹青色或多色品牌强调。
- **Don't** 使用 Emoji 作为功能图标，或混用不同图标家族。
- **Don't** 使用虚构准确率、趋势、学习画像和无意义 3D/机器人/大脑插画。
- **Don't** 用连续等宽营销卡片、过度毛玻璃、发光边缘和弹跳动画替代信息层级。
