# FileMate 最终版网站优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 用户此前选择当前会话逐项实施、结束后一次独立审阅，沿用此执行方式。

**Goal:** 按用户提供的 11 项网站评估要求完成前端、公开路由与部署配置优化，并用实际浏览器证据交付最终候选版本。

**Architecture:** 沿用 Vue 3、现有主题令牌、路由、资料导入和状态组件。以实际业务状态决定首页入口，公开页静态预渲染与 SPA 共存。已知页面与 API 的服务端路由各自保持原合同，未知 HTML 地址返回 404。

**Tech Stack:** Vue 3、TypeScript、Vite、Node 测试、Python、Playwright、现役 Nginx/Caddy 配置。

**Spec:** `docs/superpowers/specs/2026-11-05-final-web-optimization.md`。原文件为 `D:/FileMate/FileMate-网站评估与优化提示词-2026-11-04.md`，SHA256 `52af178ad706f90a3a448c9cfc7ee235e1fbb7642f460555a93e7a1e85c2ecbb`。

## 当前状态与边界

- 工作区为现有隔离工作树 `C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project`，基准 HEAD 为 `89de3ec81d3c10a9a1f726a8bbaf9862d33b875a`。
- 前一轮 D 级任务 1—8 已提交，任务 9 仍有未提交验收工具和兼容修复。实施前保留其状态与证据，避免与本计划混淆。
- 此计划覆盖文档全部 11 项。D/E 业务阶段验收、真人学习效果、实体设备与既有万题容量 P2 仍各有独立状态。
- 首先交付本地可验证候选与部署包。生产改动通过发布前备份、配置校验、健康检查和失败回滚实施，保留每一步回执。

## Global Constraints

- 沿用现有钴蓝动作色、蓝灰画布、四套主题、无衬线字体及卡片样式。
- 保留既有功能、隐私事实、LOGO 形象与吉祥物，使用现有 SVG 图标。
- 不采用新的图片 CDN、营销站路由或整站 SSR 框架。
- 首页冷加载总传输 ≤400KB，图片 ≤120KB，吉祥物 WebP ≤25KB。
- 首页桌面与移动 CLS <0.05，公开首页冷加载 LCP ≤1.0s 为验收目标。
- 桌面紧凑导航行高 36—38px，触屏操作区至少 44×44px。
- 工作区宽度上限 1440px，阅读正文上限 720px，宽屏左右留白差 <8px。
- 移动英雄区 390×844 时 ≤420px，375×667 时 ≤360px，首屏可见完整首张功能卡。
- axe critical/serious 为 0，正文对比度 ≥4.5:1，大字和控件边界 ≥3:1。
- 23 份用户修改测试的原哈希必须保留，密钥、数据库和用户资料均不进入提交或交付包。
- 预渲染失败允许告警并保留 SPA 构建，最终交付仍须提供公开页实际预渲染证据。

## 需明确的实现取舍

1. 原文同时要求首页总焦点 ≤22、保留约20个导航入口及头部控件。验收分别记录页面总数和主内容数，将 ≤22 作为首页主内容区目标，导航保留键盘可发现性。
2. 已登录用户保留首页工作台骨架，统一入口收敛和性能修复适用于所有状态。首次到访引导仅在未登录且资料确认为空时显示，读取失败时提供重试。
3. 示例采用原创《数据结构·队列》短资料，点击明确创建到当前学习空间，复用真实导入与阅读流程，标记为示例。重复点击恢复已有导入结果，失败可重试，默认不调用模型。
4. 静态预渲染使用构建后浏览器捕获公开页面，并保存可编辑模板与生成脚本。主题和账号数据在浏览器接管时更新，生成过程使用隔离空空间。
5. Brotli 以实际网关模块能力为准。构建生成 `.br`，支持的网关启用协商，保留 gzip；未支持时明确记录，避免加载不存在的模块指令。

## Review Focus

1. 慢网、离线、隐私边界读取失败与资料非空状态下，首页保持稳定且不会误建示例资料。
2. 登录、注销、刷新和多标签切换后，首次引导与主 CTA 随真实账号和资料状态更新。
3. 已知 SPA 与重名 API 地址、静态文件缺失、带查询串未知地址的状态码和 Content-Type 正确。
4. 四套主题、320px、375×667、小高度桌面、超长一言和减少动态效果偏好保持可操作。
5. 预渲染或 Brotli 工具不可用时可构建，页面正文、错误与权限边界保持真实，线上回滚可恢复原包。

## Task 1 图片与资源尺寸

**Files:** `filemate/web/src/assets/`、`components/Logo.vue`、`views/Home.vue`、`views/Auth.vue`、其余图片调用方；新增 `filemate/web/tests/brand-assets.test.mjs`、资源导出脚本。

**Interfaces:** 导出透明 LOGO SVG、220×294 吉祥物 WebP 及 PNG 兜底。组件显式声明真实宽高和按用途设置 lazy/async。

- [x] 写资源尺寸、字节预算、SVG 无内嵌整张 PNG 和图片宽高合同的失败测试，执行 `node --test filemate/web/tests/brand-assets.test.mjs`。
- [x] 从现有品牌资产导出，逐图记录原字节、输出字节、尺寸和引用位置。表达图按实际角色尺寸导出，低频图片懒加载。
- [x] 重跑测试及 `npm --prefix filemate/web run build`，1440与390截图检查透明边缘、文字、形象。
- [x] 显式提交本任务文件，记录首页真实传输测量，区分开发服务器与压缩生产产物。

## Task 2 稳定外壳与数据加载

**Files:** `App.vue`、`views/Home.vue`、`views/Import.vue`、`views/AITools.vue`、`components/DataState.vue`、相关布局 CSS；新增 `filemate/web/tests/layout-stability.test.mjs` 和浏览器性能脚本。

**Interfaces:** 既有 loading/error/empty 属性保持兼容。导航提示使用固定覆盖层，页面加载占位匹配最终结构，页脚与账户区域预留空间。

- [x] 为导航非占流、稳定外壳和加载占位写 RED，采集首页及三个相关页的冷加载 LayoutShift 来源。
- [x] 在实际移动元素处修复，保留页面可见正文和重试入口，避免用 transform 或延迟整页渲染掩盖位移。
- [x] 同一浏览器环境以1440×900及390×844各重复至少3轮，记录5秒CLS样本、LCP、FCP、失败请求和控制台。
- [x] 首页 CLS 每轮 <0.05 后提交。P75 与单设备实验值分别标注，真实用户 P75 留待采集。

## Task 3 公开路由与真实404

**Files:** `router/index.ts`、新增 `views/NotFound.vue`、`public/robots.txt`、`public/sitemap.xml`；`deploy/nginx.filemate.conf`、`deploy/Caddyfile`；路由与网关合同测试。

**Interfaces:** catch-all 保留原地址，标题“页面不存在 · FileMate”，回首页及今日行动两个可点击出口。已知 SPA 路由白名单与现有 API 识别共同生成部署合同。

- [x] 写未知 `/abc`、`/foo/bar`、查询串、缺失静态资源、公开页面直访及重名 API 的失败测试。
- [x] 加入 catch-all 和静态爬虫文件。网关对未知页面返回404，HTML内容仍允许前端显示同一404视图。
- [x] 用隔离网关或配置验证工具检查状态码、Content-Type、安全头和路由。运行相关部署测试及前端路由测试。
- [x] 将已知路由更新方式写入部署文档并提交。

## Task 4 首次到访引导与首页入口

**Files:** `views/Home.vue`、现有账号与资料读取服务、首页状态纯函数模块、示例资料、相关测试。

**Interfaces:** `resolveHomeAction(state)` 返回固定内部路由、标题和动作类型。输入区分资料未读取、读取失败、空资料、已有资料和待复习。示例入口复用 `importLearningSource`。

- [x] 为游客空资料、登录、已有资料、待复习、读取失败、重复示例点击和路由目标写 RED。
- [x] 引导带呈现 ≤22字定位句、三步和一个主动作。主 CTA 与辅助卡片分级，资料/错题/面试三个卡片提供按需展开的原功能链接。
- [x] 主内容区可聚焦元素 ≤22，单个 primary 动作。记录含导航的整页计数，保留全部功能可到达。
- [x] 浏览器完成真实示例导入→阅读、登录后引导隐藏、原资料状态恢复和离线重试后提交。

## Task 5 桌面、移动与统一空状态

**Files:** `App.vue`、`components/DataState.vue`、`views/Home.vue`、`views/AITools.vue`、`views/Trust.vue`、共享样式、响应式合同测试。

**Interfaces:** 复用 DataState 的现有 slot 和事件，新增可选标题/图标/动作 slot，至少3页采用。阅读/工作区容器沿当前结构分层。

- [x] 写窄屏无溢出、导航可发现性和空状态复用 RED，测量900/768高度与1920宽度基线。
- [x] 桌面导航压缩并显示滚动提示，手机头部统一44px控件。一言保留点击展开，英雄区遵守两档高度。
- [x] 统一空状态上下留白至少48px、CTA底边距至少24px，归档空态使用紧凑横排。
- [x] 1440×900、1366×768、1920×1080、390×844、375×667、320宽及四主题截图、键盘走查通过后提交。

## Task 6 文案、隐私与可访问性

**Files:** `views/Import.vue`、`components/PrivacyBoundaryNotice.vue`、`views/Auth.vue`、设置组件、`App.vue`、共享按钮样式及测试。

**Interfaces:** 隐私组件保留 ready 事件与失败时阻止上传的合同。完整事实收进可访问说明面板，公开环境横幅支持本机关闭，关于页呈现版本信息。

- [x] 写 remember 默认false、隐私ready门禁、说明入口、关闭横幅与失败重试 RED。
- [x] 首屏隐私说明≤30字，完整说明保留90天/15分钟/25MB等事实。删除重复说明，长句分段，侧栏正常连接降级显示。
- [x] disabled 使用原生禁用、去阴影与可识别原因，关键文字≥14px，状态辅以图标/文本。
- [x] 对 `/`、`/today`、`/import`、`/login` 运行 axe，critical/serious为0。抽测10处对比度，完成 Tab、焦点、禁用态与四主题走查后提交。

## Task 7 分享、预渲染与压缩

**Files:** `index.html`、构建脚本与 `package.json`、`vite.config.ts`、现有主题运行模块、公开分享图片、部署配置和构建合同测试。

**Interfaces:** 四个公开页面 `/`、`/login`、`/register`、`/trust` 输出含真实 H1 与首段的 HTML。元数据含至少5项OG、Twitter卡片、canonical及Organization/WebSite JSON-LD，无虚构统计。

- [x] 写公开HTML标题/正文/元数据、主题色、无浏览器时告警回退、预渲染隔离数据的失败测试。
- [x] 从现有品牌素材合成1200×630分享图，生成四页HTML与`.br`资源。按主题更新theme-color，首帧使用匹配主题色。
- [x] 构建时隔离空空间，生成不包含账户/令牌/学习内容。实际检查四页源码、MIME、缓存协商、深链接与SPA接管。
- [x] 测量首屏 ≤400KB、图片≤120KB、LCP≤1s。微信/QQ真实分享卡片列为需实际客户端验证，不能以meta存在替代。提交代码与测量。

## Task 8 全量验证、独立审阅与最终交付

**Files:** `docs/FINAL_WEB_OPTIMIZATION_DELIVERY_2026-11-05.md`、README、交付索引、部署说明；证据放 `_working/final-web-20261105/`。

- [x] 运行 `scripts/verify.ps1 -IsolateFrontend`，记录完整退出码；前端测试、vue-tsc、构建和现有gzip143360字节门禁全部保留。
- [x] 对11条提示词逐条核对实际证据，记录未达标指标、设备与外部依赖；保护原23份用户测试哈希。
- [x] 使用 requesting-code-review，仅一名全新只读审阅者审阅整个本轮实现，处理重要问题并重跑受影响门禁。
- [x] 输出新的最终ZIP、源码与产物SHA256、改动与限制清单、配置部署及回滚步骤。原包保留。
- [x] 按已有生产授权与阶段边界完成可发布部分的上线，保存备份、版本、健康和公开页面验证回执。D开关仍以用户D级验收为启用前提。

## 计划自审

- 11项映射依次为任务1、2、3、4、4、5、5、5、7、6、6。
- 五项Review Focus分别进入任务2/4、4、3、5/6、7/8的验收。
- 首页示例与CTA使用原资料合同，隐私ready事件沿用，catch-all与网关同步，新增生成文件拥有可复现脚本。
- 任何性能、可访问性或线上指标未实测时保留未验证状态，交付状态以证据决定。
