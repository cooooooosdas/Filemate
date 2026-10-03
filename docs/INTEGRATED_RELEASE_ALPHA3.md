# FileMate v1.3.0-alpha.3 整合发布

2026-10-03已部署并完成公网验收：[filemate.asia](https://filemate.asia)。运行代码提交为`9c133e1701d0518579faf4e174da2c9d17db4199`，版本`v1.3.0-alpha.3`；公开[release.json](https://filemate.asia/release.json)与后台健康版本一致。真实学生和导师数据仍为0，不能将合成回归解释为学习效果。

## 本次整合

- 五模块和B2/B3工程尾项、学习证据说明、评测采集/校验/导出工具与完整托管备份。
- 钴蓝光束大背景、冰蓝画布、较大字号、Tabler图标、入场/导航反馈和减少动态效果偏好。
- 分类/命名/日程一体审核、知识证据入口、四类学习任务、资料导入与引用复用；UTF-8 Markdown及代码作为文本导入。
- 集成主分支模型路由、桌面运行环境隔离、面试资源和移动导航/焦点修复；全部版本合同统一alpha.3，schema仍为v24。
- 主色微调为`#2352d3`，同步语义色及Element Plus文本/按钮状态，保证指定浅底文字组合至少4.5对比度。

## 工程证据

合并后的默认门禁：Ruff通过；后端784通过、18跳过、5个真实模型E2E未运行；前端21测试、类型检查、构建及首屏依赖预算通过。新增部署边界回归在Linux CI执行；本机Windows明确跳过，不能记为通过。

最终Linux主分支[CI](https://github.com/cooooooosdas/Filemate/actions/runs/37134208990)通过：792后端、18跳过、5真实模型E2E未运行；其中新增8项服务器部署边界测试通过。前端21测试、类型、构建、首屏预算及Python打包/合成评测分析流水线通过。Windows默认门禁为上面的784项；不能混淆跨平台计数。

隔离前端为`_working/verify-web-d7ae1ddd8a4f420aa351aadad0fb8053`。最终`_working/gateway-alpha3-final/summary.json`通过47项TLS父级检查、91个现役API路径；28项页面、4项实际本地视觉、12项布局/动效、17项归档、25项学习工作区、18项知识库和72项浏览器无障碍检查全部通过。有限8访客128次读取通过；不是生产容量或学习收益测量。编译源与现役77份前端源/公开文件逐一相符，见`_working/package-source-match.json`。

首轮失败和修复证据保留：重复合并的7个相同测试去重；旧主色验收常量更新；5页文字与装饰字对比度、成长说明列表结构修复；SSH umask导致的服务账户权限及预检路由错误在隔离候选中修复。线上学习探针首次使用了错误的弹窗名称，修正选择器后完整重跑，未改变线上业务代码。

## 实际上线结果

- 后台`/opt/filemate/current`指向`/opt/filemate/releases/alpha3-9c133e17`，Python环境独立；静态`current`为`releases/alpha3-9c133e17`的容器内相对链接。systemd active，`nginx -t`通过，维护标记已解除。
- 发布包后台SHA256：`a4bd7b4525add1ef121bfe4d0829cc99f93b6403c65544013ac5cd9d7e754e3d`；静态SHA256：`9ff25ab2ad5c348b8746f1e3f03afc2d2962de7f58b2de233d16c0f4d75518c6`。本机清单`_working/alpha3-9c133e17/package.json`；未包含密钥或用户库。
- 完整备份`/var/backups/filemate/alpha3-9c133e17-20261003T154531Z`，76个SQLite库、87个文件，schema为历史v15与现役v24；备份/新目录恢复、逐文件指纹、UID/GID/权限及每库integrity_check通过。上线前只读检查不存在托管根目录外的资料引用。有效身份密钥和旧版本完整保留。
- `_working/live-check/routes/summary.json`：公网22个页面、9个基础API全部通过，页面内容、无横向溢出、无控制台/JS错误及导航时延有直接证据。页面DOMContentLoaded中位413ms，首次冷访问首页8623ms；冷加载仍值得继续优化，不能把接口速度当作整页加载速度。
- `_working/live-check/learning-final/summary.json`：6项真实公网闭环通过。原创Markdown入库，现役DeepSeek官方端点生成结构化笔记，保存/手工修订/重读有效；另一匿名设备读取返回404；实际知识页可打开学习链和笔记；最后经页面预览确认，只删除本探针资料及派生产物。无请求转发、模型模拟或真实用户资料。
- `_working/live-check/server-latency.json`：10次每秒一次的有限读取全部200，p50为23.55ms，最近秩p95为271.8ms。只表示这次客户端和负载，不能称为生产SLA。上线后可用内存约777MiB，磁盘约23GiB。

主分支已包含运行提交；随后仅提交本次文档收尾，应用代码与上述发布提交相同，无需为文档更新重启服务。标签`v1.3.0-alpha.3`固定已验收运行提交。

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

## 知识收尾状态

代码与运行态`verified-current`；README/资源索引/流程/部署记录`changed-and-verified`；AGENTS约束`verified-current`；独立记忆系统`not-applicable`。发布工作树和证据保留，未删除分支或旧发布；主工作区102份无关竞赛/会议材料保留，属于本次部署的`out-of-scope`。下一开发卡继续UI-02及原账本，不能将本次Alpha上线改写为全部产品目标完成。
