# 生产前端质量交付（2026-10-03）

这是全项目后续推进的第一阶段，接续已交付的B2/B3工程尾项。当前版本标识、HTTP接口、SQLite v24和五模块数据合同保持现役定义；完整剩余要求见[执行账本](FULL_PROJECT_EXECUTION_PLAN.md)。本阶段完成不等于整个项目或正式v1.3.0已完成。

## 用户可见结果

Element Plus组件和样式改为按实际页面使用加载，Monaco、图表和视觉Worker继续按需加载。页面资源请求失败时，主框架保留，显示明确的重新打开入口；重新打开前告知当前未保存输入会清除，不自动刷新。开发环境提前预编译组件样式入口，避免首次进入新页面时依赖刷新导致路由中断。

新增生产包门禁按首页、入口及全部递归静态依赖累计体积，不因拆成更多小文件绕过预算。`scripts/verify.ps1`、GitHub Actions及Web容器构建均执行相同门禁。

| 首页必需资源 | 原构建 | 当前构建 | 门禁上限 |
|---|---:|---:|---:|
| JavaScript原始字节 | 1,120,774 | 351,679 | 460,800 |
| JavaScript估算gzip字节 | 368,613 | 129,686 | 143,360 |
| CSS原始字节 | 393,630 | 96,437 | 153,600 |

JavaScript约减少68.6%，CSS约减少75.5%。gzip值是本机逐文件估算，未测公网实际传输。真实Edge冷上下文通过本机回环访问，首页本轮666ms；单次样本不作为网站性能改善或SLA证明。

## 文件与公共合同

- `filemate/web/src/main.ts`、`vite.config.ts`、`package.json/package-lock.json`：按需组件、脚本样式注入及开发依赖预编译。
- `filemate/web/src/router/load-errors.ts`、`router/index.ts`、`components/PageLoadError.vue`、`App.vue`：页面资源失败状态与用户主动恢复。
- `filemate/web/scripts/check-bundle.mjs`、`tests/bundle.test.mjs`：递归依赖预算及防止拆包绕过、缺失依赖、重型模块提前加载的测试。
- `scripts/verify.ps1`、`.github/workflows/ci.yml`、`deploy/Dockerfile.web`：本地、CI和容器构建接入门禁。
- `scripts/acceptance/frontend_production.mjs`、`integrated_browser.py`：生产包实际组件、弹窗、消息、加载状态、资源失败与响应式验收。

没有新增HTTP端点、数据库迁移或运行期环境变量。测试可通过`FILEMATE_TEST_TEMP`将本机夹具放入专用临时目录；Windows路径先规范化再校验和清理。

## 当前快照的验收

- 默认全门禁的隔离模式通过：Ruff，后端718 passed / 18 skipped / 5 deselected，前端18项，Vue类型检查、生产构建与包预算；原日志在`_working/project-continuation-20261003/verify.log`。
- 全模块19组浏览器回归中，18组初次通过。22页/9接口冒烟发现Vite首次访问新组件样式的预编译刷新；修复后22页/9接口全部通过。
- 修复后的前端18项、类型检查、构建与预算再次通过；实际生产包8项专项再次通过，包括注入资源请求中断后的主动重新打开、弹窗/消息/加载指令、375/768/1440布局和重型资源延迟加载。
- 两个验收脚本断言问题（弹窗容器与内容宽度、历史页标题/接口）已根据真实页面修正，失败日志保留；前端临时路径使用正斜杠造成的清理边界断言已规范化。未降低任何产品断言或预算。

证据目录为`_working/project-continuation-20261003/`。`browser-full/`保留全19组初次结果，`browser-optimizer/`保留修复后的冒烟和生产专项，`bundle-before.json`与`bundle-after.json`保留资源明细。复测覆盖受影响的开发配置和编译产物，后端代码本阶段未改变；没有将两个快照改写为一次全绿运行。

复跑命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
uv run python scripts/acceptance/integrated_browser.py --web-root <新门禁副本> --out _working/<新证据目录> --cases browser_smoke frontend_production
```

## 已知限制、回滚与下一阶段

Monaco编辑器独立chunk约2.7MB，仍有构建体积提示；它未进入首页，不代表编程页加载已优化到目标。当前浏览器检查基于本机Edge，不替代公网容量、移动设备或长期稳定性测试。未更新线上服务，远端CI和桌面安装包也未因此通过。

需回滚时，只撤回本阶段的组件按需配置、页面加载恢复组件和预算接线；恢复原全量Element Plus注册与CSS。保留其他既有模块改动、数据库和历史证据。恢复全量组件将超出本阶段预算，必须作为明确回滚例外记录，不能悄悄放宽阈值。

下一阶段是独立的服务与数据运维任务卡：匿名分库、托管附件和身份密钥的完整备份、校验、临时恢复与故障演练；监控和容量按后续子项继续推进。真实学生与导师采集、版本冻结及线上同步保持待完成。
