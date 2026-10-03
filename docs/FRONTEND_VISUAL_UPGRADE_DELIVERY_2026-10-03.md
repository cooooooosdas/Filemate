# FileMate 视觉升级：样例、选型与首轮实装

更新日期：2026-10-03。用户要求扩大字号、增强背景和切换表现、整合同类功能并减少控制台感。本卡先完成三份可运行样例及首页/公共导航，下一卡整合资料审核，再推进学习工作区和五模块。整体项目仍按[执行账本](FULL_PROJECT_EXECUTION_PLAN.md)推进。

## 六站参考与实际采用

| 参考来源 | 选择方向 | 实装方式 |
|---|---|---|
| [Anime.js](https://animejs.com/documentation/web-animation-api/) | 入场错峰、原生合成动画、可暂停的背景 | 精确依赖 `animejs@4.5.0`，只导入 `animejs/waapi`；三层书页入场和环线慢转 |
| [MotionSites](https://motionsites.ai/) | EMBER.dsgn / Digital Epoch 的大字主视觉、Glow Features 的连续内容区 | 借鉴层级与节奏，用原创 Vue/CSS 实现。用户给出的 `motion.sites` 无法连通，以可访问的品牌站公开预览为参考；没有购买或复制提示词 |
| [Showreel UI/UX Motion](https://showreel.design/category/uiux-motion/) | Intently 2.0、Clay Showreel 的清楚过渡与简洁信息 | 参考切换节奏；没有复制视频、品牌素材。`showrealdesign` 按可访问的 Showreel Design 核对，不能确认二者是同一域名 |
| [React Bits Threads](https://reactbits.dev/backgrounds/threads) / [Flowing Menu](https://reactbits.dev/components/flowing-menu) | 有机背景线、明确的选中态 | 原创 CSS 环线和 Vue 方向切换；没有接入 React 或复制组件。[官方仓库](https://github.com/DavidHDev/react-bits)标明 MIT + Commons Clause，并提供 Vue Bits 入口，不能把它描述为纯 MIT |
| [Aceternity Background Beams](https://ui.aceternity.com/components/background-beams) / [Tabs](https://ui.aceternity.com/components/tabs) | 大背景与同屏任务切换 | 用原创书页场景和可见方向按钮表达；没有复制付费模板、安装 React/Tailwind/Motion |
| [Uiverse Buttons](https://uiverse.io/buttons) | 大点击区、按下与焦点反馈 | 原创按钮样式与键盘焦点；没有直接复制代码。[官方 Galaxy 仓库](https://github.com/uiverse-io/galaxy)采用 MIT，单个素材仍应按其来源核对 |

以上只作为设计与组件能力参考，不证明流行度、行业采用或学习收益。背景是资料→理解→练习的原创抽象书页，没有外链图片、远程字体或 WebGL 依赖。

## 三份样例与选择

样例在项目忽略目录 `_working/visual-upgrade-20261003/prototypes/`，三个 HTML 均可单独打开。

- `a-growth.html`：知识生长。大字、浅绿场景、三层书页和连续任务区。选为实装方向，主题与资料学习直接相关。
- `b-pages.html`：书页阅读。偏阅读与留白，适合资料正文，首页的行动指引较弱。
- `c-journey.html`：学习路径。连续绿色路径表达推进，但抽象场景占用较多空间，适合后续计划页。

`prototype_checks.mjs` 对三份样例各测375/768/1440布局、方向切换、样例说明弹窗与键盘退出，九组响应式检查通过，无页面异常。这个比较是开发者选型，不是用户实验。

## 首轮用户可见变化

首页标题44–70px、主说明18–20px；导入按钮和三种方向提供清楚的下一步。四块历史计数归入“最近资料”，手机上学习方向紧接主视觉。真实历史和今日安排继续来自现役 API；空库显示空态，没有添加虚构画像或趋势。

侧栏从20个工具入口收为9个主要任务，相关工具出现在各任务内，完整工具查找和原有深链保留。三个方向在同屏切换相关操作；页面切换采用有限的透明度/位移过渡。公共页头、导航、说明和按钮字号同步扩大。

背景进入视口后运动，滚出或页面不可见时暂停；减弱动画偏好立即切为静态，离开页面撤销动画并移除监听。测试通过实际站内往返检查每次只保留一个场景。代码、原文和复杂表格未用强制全局字号覆盖。

主要文件：`Home.vue`、`App.vue`、`components/KnowledgeBackdrop.vue`、`style.css`、`workspace.css`及 npm 合同。API、schema和环境变量没有改动；尚未把全部业务表单合为一屏。

## 直接验收证据

本卡冻结候选为 `_working/visual-upgrade-20261003/frontend-final/`，实际HTTPS结果为 `production-2/`。候选与验收指纹保留，后续卡不覆盖本次证据。

| 检查 | 结果 |
|---|---|
| 默认全门禁 `verify.ps1 -IsolateFrontend` | 740后端通过、18跳过、5排除；18前端通过，类型/构建/预算通过，见 `verify-final.log` |
| 之后首页统计布局微调 | 类型/构建/预算复测通过；当前编译资产经下列实际HTTPS复测，见 `frontend-final.log`、`build-final.log` |
| 当前首屏累计体积 | JS364313字节、估算gzip134156字节、CSS100164字节；原450/140/150KiB预算通过，见 `bundle-final.log` |
| 实际Caddy + 生产匿名FastAPI | 41项通过，91个HTTP路径与实际上游匹配；指纹前后未变化 |
| 页面/CSP/Monaco | 28项通过，涵盖22个页面与响应式，JS/CSP异常为0 |
| 实际视觉Worker/WASM与录像 | 4项通过；输入为公共图片合成流，不是用户设备 |
| 新版UI | 10项通过：字号、点击区、375/768/1024/1440、方向/相关导航、滚出暂停、减弱动画、实际SPA往返 |

初次使用完整动画引擎时gzip144102字节超原预算742字节，失败日志与候选保留。改用独立 WAAPI 入口后通过，未放宽预算或删去必要界面。`production-1/`是更早布局的独立通过记录，不与`production-2/`相加冒充全量一次测试。

本机TLS夹具不表示线上已更新。真实学生与导师数据仍为0，实际学习收益待评测；正式账号、服务器/Linux、桌面交付与整体版本冻结仍按账本继续。

后续[资料审核一体化](INTEGRATED_FILE_REVIEW_DELIVERY_2026-10-03.md)已将分类和命名合到同屏，完整工具查找从本卡快照的20项合为19项。该卡的候选、测试和失败修复过程另存，本卡的首轮指纹与结果保持原状。
