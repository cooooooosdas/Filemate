# PPT Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, with one fresh final reviewer.

**Goal:** 将PPT今日安排和教练布局落实到前端，并消除导航重复与面试query重挂载。
**Architecture:** Vue3现役路由/数据不变；目录定义父子关系，应用壳显示唯一分层导航。面试独立稳定实例key和离开保护。
**Tech Stack:** Vue3、TypeScript、Tabler SVG、Node test、Vite。
**Spec:** docs/superpowers/specs/2026-10-16-ppt-workspace-design.md

## Global Constraints

- 保留LOGO、蓝色、真实数据与授权、旧URL、功能开关；无新依赖、API或schema。
- 正文17px、辅助15px、操作至少44px、减少动画有效。

## Review Focus

- 浏览器前进/后退切换面试与未提交回答时不会静默丢失。
- 当前子页与父页高亮语义不同，不伪装成当前页。
- 关闭特性时不留孤立子项；全部工具可查找。
- 375px左右不横向滚动，侧栏键盘与Escape保留。
- 空数据、模型失败不渲染虚构任务/反馈。

### Task 1: Navigation and interview lifecycle

Files: navigation/catalog.ts; navigation/route-state.ts; App.vue; Interview.vue; tests/navigation.test.mjs; tests/route-state.test.mjs.
- [x] 增加父子工具唯一归属、所有别名/开关的失败测试；增加面试query实例稳定和丢失风险判定测试，确认RED。
- [x] 实现childrenTools及稳定key；父级仅当前位置祖先，子级为当前页；取消顶部条和重复知识库链接。
- [x] 实现面试内部query同步、外部query恢复、离开/刷新保护，保留录制清理。
- [x] 运行前端测试并记录GREEN。

### Task 2: PPT-informed workspace

Files: style.css; App.vue; Today.vue; Interview.vue; Home.vue; styles/interview-practice.css; styles/programming-coach.css; design-system/filemate/MASTER.md.
- [x] 从第6/10页采用清亮工作台、任务列表、主次分栏和教练面板，保留业务逻辑。
- [x] 加入轻量原创SVG任务几何图，改进标题/操作/响应式，保持真实数值。
- [x] 类型构建、体积门禁；桌面/窄屏一次批量检查，集中修正。

### Task 3: Review and delivery

- [x] 独立review源代码与截图；只按实质问题修复并复验。
- [x] 同步README/设计系统/交付记录，保留原账本，报告未部署。

## 验收收口

后端1163通过、22跳过、5排除；前端59通过、类型/构建/预算通过。默认脚本npm ci因C盘空间不足中断，D盘同源同锁依赖安装及全部前端尾段恢复exit0，保留原失败记录。独立最终审阅唯一P2手机教练顺序已解决、复审clear。生产未变，详见交付记录。
