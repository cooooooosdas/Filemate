# FileMate 大背景与全站配色重做

用户反馈上一版大背景变化不足，明确要求重新从六个参考站选模板、配色与提示词，替代绿白底色。本卡仅处理全站视觉，保留上轮资料审核与学习工作区的全部业务流程。

## 参考与选型

[来源与可复制实施提示词](BACKGROUND_REDESIGN_PROMPT_2026-10-03.md)记录六站访问结果、参考范围和不能核实的部分。直接观察了Aceternity Background Beams预览；其路径式大背景与Aurora光场、React Bits Side Rays、Uiverse等高线构图组合为原创Vue/CSS/SVG实现。没有复制付费模板源码或引入React/OGL/WebGL。

`_working/background-redesign-20261003/samples/`保留三份原创、可离线打开的整页样例，每份都有375/768/1440截图及无横向溢出检查：

| 样例 | 配色与背景 | 选型 |
|---|---|---|
| `a-cobalt.html` | 钴蓝主视觉、冰蓝画布、暖金导入动作，曲线光束与大透镜 | 已选；与FileMate蓝色品牌连接，动作和正文层级明确 |
| `b-amber.html` | 琥珀色大纹理、暖纸面板、棕色导航 | 保留供比较，当前不实装 |
| `c-prism.html` | 银蓝棱镜、浅青画布、低反差空间背景 | 保留供比较，当前不实装 |

样例中的链接、数据和流程标注为示意。实际产品继续使用真实记录与已有路由。

## 用户可见变化与文件

- `Home.vue`、`KnowledgeBackdrop.vue`：首页标题改为「让知识成形」，旧纸页小插画替换为占满标题区域的大背景。24条原创曲线横跨画面，右侧大透镜与学习折页，标题44–70px、正文18–20px、暖金主动作。背景滚出视口或页面隐藏时暂停，减少动画时静态，离开时清理。
- `style.css`、`App.vue`、`workspace.css`：根画布、侧栏、页头、选中导航、当前任务导航、公共页头和面板统一冰蓝/钴蓝。长篇阅读表面为近白蓝，成功/警告/失败保留语义颜色；任务内导航合成连续导航条。
- `LearningWorkspace.vue`、`FileReview.vue`、`Import.vue`、`Auth.vue`：阅读/目录/归档预览/导入/登录统一新背景，移除导入页覆盖全局的旧绿色令牌。现有创建折叠、引用、草稿、确认、撤销、练习和输入保护不变；登录注册仍是原有界面预览，未新增身份功能。
- `visual_upgrade.mjs`：实际编译页面检查背景覆盖、字体、颜色对比、多个任务页和登录、减少动画、路由重建和业务导航。原10项扩为12项，不将重命名断言当作额外通过。
- `AGENTS.md`、设计系统、PRODUCT与README：同步用户新要求，避免后续又恢复自然绿限定。

## 验收记录

最终证据在`_working/background-redesign-20261003/`：

- `verify.log`：默认`scripts/verify.ps1 -IsolateFrontend`退出0，Ruff、740项后端（18跳过、5未选、3警告）、18项前端、类型检查、构建与原首屏预算通过。
- `frontend-final/`：冻结已验证源码与编译产物；manifest SHA256为`763f2964d1fd32483eaf33f7b27cc4908a6df36662d2d28f89d391ef936ad764`。`source-snapshot.json`核对当前72份前端源文件/构建入口与冻结副本一致。
- `production-final/summary.json`：实际本机Caddy HTTPS网关45项、91个API路径和128次有限读取通过，验收涉及源码指纹保持不变。`visual_upgrade`12项、`file_review`17项、`workspace`23项、`gateway_production`28项及现役本地视觉生产专项通过；全部使用同一冻结编译包。
- `production-final/visual_upgrade/`：375/768/1024/1440首页大背景与字体截图、导入/知识库/今日学习/成长/工作区和登录截图。8组主要文字、画布/面板和主动作颜色对比最小4.55:1；这是所测令牌组合，未把它等同于所有控件状态的完整无障碍认证。
- `bundle-final.json`：首屏累计JavaScript 363405字节、估算gzip 133484字节、CSS 100972字节，维持原450/140/150KiB预算，不放宽门槛。
- `cleanup.json`：自有验收端口和浏览器进程清理检查；用户原有参考标签保留。

可复跑命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -IsolateFrontend
uv run python scripts/acceptance/gateway_preflight.py --caddy _working/operations-preflight-20261003/tools/caddy.exe --web-root _working/background-redesign-20261003/frontend-final --out _working/background-redesign-20261003/production-rerun --visual-checks --review-checks --workspace-checks
```

复跑输出目录必须尚不存在。实际模型不参与本轮浏览器闭环，使用显式隔离夹具；不沿用上轮绿白方案截图，也不累加不同候选的通过数。

## 边界

本卡不改变API、schema、模型Provider或服务器部署。外部参考只影响视觉；实际学习工作区/文件流程用隔离匿名资料和显式本地合成HTTP模型夹具回归，不证明真实模型质量或学习收益。真实学生与导师数据仍未采集。motion.sites当前无法加载；showrealdesign缺少确切域名；Aceternity提示词复制超时，已交付可复制的改写提示词，未声称取得原站提示词。
