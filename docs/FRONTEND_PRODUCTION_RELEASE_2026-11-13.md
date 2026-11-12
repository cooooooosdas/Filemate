# 前端固定版生产发布回执 · 2026-11-13

已推送main并发布至 https://filemate.asia/ 。新版网页为aa03d0bbbf30500def29dd6ab4050436640703ea，版本1.3.0-alpha.4。后端沿用c28dc2b1ae7c5cbf047321286eb09f73223dac46，业务schema36、治理schema3。

## 测试与发布

精确提交的[干净Linux CI](https://github.com/cooooooosdas/Filemate/actions/runs/43272573903)通过，后端2191通过、19跳过、5排除，前端444通过、0失败。类型、构建、首包体积、Python包及离线评测检查通过。Windows本机重复全套在Linux结果确认后停止，其未完成结果不计为通过。

本轮差异为Web和文档，按既有纯静态发布流程执行。候选450个运行文件摘要核验通过，保留354个旧资源。首次stage被隐藏构建清单.vite阻止，移走本次未激活目录并排除3个内部构建清单后重试通过。源码和业务文件未因发布调整。

正式静态目录为 `/clouddream/nginx-proxy-manage/data/filemate/releases/alpha4-aa03d0bbbf30`。发布包SHA256为 `0444f08f843b0cd3d0c0c441356767563c363166f8f4762d5b60d13f5d1c4ce5`。

激活检查通过，28个首页入口资源和缓存头正常。公网health、ready、release marker、今日行动capabilities回读通过。Edge实测新版首页、面试、资料库、今日行动入口均可打开。API PID为8293，自动重启次数0。

## 回退与资料

上一网页目录 `releases/alpha4-c28dc2b1ae7c` 保留。回退时原子恢复静态current链接，再检查release.json、api/health和api/ready。发布没有数据库迁移，恢复网页时应保留后续用户数据。

服务器发布与回退回执位于 `/opt/filemate/incoming/alpha4-aa03d0bbbf30-web/`。本机证据位于 `D:/FileMate-Project/_working/release-polish-20261113/`。23份用户已有测试改动保留，未纳入提交。

## 后续范围

本版本作为后续体验的固定基线。既有万题并发容量P2、实体音视频设备及真人学习效果验证继续按2026-11-11发布记录跟踪。本轮验证不包含这些专项。后续以测试和产品试用为主。
