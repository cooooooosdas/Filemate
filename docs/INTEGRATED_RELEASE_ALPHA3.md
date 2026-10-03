# FileMate v1.3.0-alpha.3 整合发布

2026-10-03发布候选。此记录区分本机工程验收、远端CI与实际公网部署；上线结果在完成后补录。真实学生和导师数据仍为0，不能将合成回归解释为学习效果。

## 本次整合

- 五模块和B2/B3工程尾项、学习证据说明、评测采集/校验/导出工具与完整托管备份。
- 钴蓝光束大背景、冰蓝画布、较大字号、Tabler图标、入场/导航反馈和减少动态效果偏好。
- 分类/命名/日程一体审核、知识证据入口、四类学习任务、资料导入与引用复用；UTF-8 Markdown及代码作为文本导入。
- 集成主分支模型路由、桌面运行环境隔离、面试资源和移动导航/焦点修复；全部版本合同统一alpha.3，schema仍为v24。
- 主色微调为`#2352d3`，同步语义色及Element Plus文本/按钮状态，保证指定浅底文字组合至少4.5对比度。

## 工程证据

合并后的默认门禁：Ruff通过；后端784通过、18跳过、5个真实模型E2E未运行；前端21测试、类型检查、构建及首屏依赖预算通过。新增部署边界回归在Linux CI执行；本机Windows明确跳过，不能记为通过。

隔离前端为`_working/verify-web-d7ae1ddd8a4f420aa351aadad0fb8053`。完整TLS与页面/学习交互、视觉、无障碍浏览器验收正在执行，保留失败与最终通过证据。

## 部署与回滚

现役拓扑为Nginx Proxy Manager容器`nginx-app`、systemd `filemate-api`及SQLite数据根`/var/lib/filemate`。发布工具为[scripts/deploy_existing.py](../scripts/deploy_existing.py)，不能直接使用Caddy/Docker bootstrap覆盖既有服务。

1. 对明确提交创建后台与已验收前端tar包，计算SHA256；静态`release.json`记录软件版本、提交和构建时间。
2. 上传至`/opt/filemate/incoming/alpha3-<commit短码>`。工具`stage`先校验包、独占解压，使用独立Python3.11环境和[锁定依赖](../deploy/requirements-production.lock)，保留现役环境；临时数据以实际`filemate`账户运行核心API预检。
3. 工具`activate`确认迁移合同相同，设置维护标记、停止应用写入；使用SQLite backup API备份整个数据根，包括匿名分库、附件、身份密钥及历史运维文件，保留所有权和权限；在新目录验证恢复与每库完整性。
4. 保存旧链接、systemd和Nginx配置；校验`nginx -t`，原子切换后台/静态链接，重启版本检查和实际容器静态映射，再开放公网。
5. 解除维护后检查HTTPS、HTML及JS/CSS、资源缓存和公开提交标记。早期失败自动回退代码与配置；已重新开放公众写入后保持当前数据，禁止用旧快照覆盖。

工具参数：`stage|activate --release-id alpha3-<短码> --commit <完整SHA> --version 1.3.0-alpha.3 --backend-sha256 <SHA256> --web-sha256 <SHA256>`。部署脚本、SSH密钥和生产环境变量分别管理；密钥及用户备份不提交Git。

该拓扑普通接口120次/分钟、AI接口6次/分钟、并发20、网关正文26MiB、后端文件25MiB。Caddy的32MiB策略属于另一拓扑。业务和HTML使用no-store、哈希静态资源长期缓存、视觉模型no-cache；限制不因验收而关闭。

## 保留依赖

Linux服务器尚无经安全验收的C++隔离Provider，编程模块应明确显示运行环境不可用；桌面Windows版本保留现役隔离实现。登录/注册仍为清楚标注的预览，匿名设备隔离不能算正式账号。安装包独立验收、监控/配额与异地自动备份、真实研究和导师盲评继续按开发账本推进。本次上线为Alpha，不是正式v1.3.0验收。
