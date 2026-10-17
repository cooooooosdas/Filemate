# 面试教练发布准备（2026-10-17）

状态：本地候选；此文件和压缩包不会执行部署。当前公网只读探针的release.json标记 `935061af439928fbf719ad79d454b8f765a41078`、`1.3.0-alpha.4`、业务schema26、治理schema2；实际生产数据库尚未读取，不能把候选包当作线上回执。

## 包内容

`source/`来自manifest中固定Git提交；`deploy/backend.tar.gz`为同一提交的源码；`deploy/web.tar.gz`开启逐题教练，`deploy/web-coach-off.tar.gz`关闭新界面。`manifest.json`和`SHA256SUMS.txt`记录包指纹、版本、开关及验收范围。`evidence/`只包含合成验收、门禁及公网只读结果，不包含数据库、真实资料、密钥、音视频或生产环境配置；源码保留公开配置示例和桌面端回环API地址。

## 配置与暂存

保持现有生产身份密钥、数据目录、资源限制和模型提供商配置。不要用`.env.example`覆盖线上配置，也不要把密钥加入包或命令。新界面需要同时设置：

```text
后端：FILEMATE_ENABLE_INTERVIEW_COACH=1
后端：FILEMATE_ENABLE_INTERVIEW_REVIEW=1
前端：VITE_ENABLE_INTERVIEW_COACH=true（本包web.tar.gz已编译）
前端：VITE_API_URL为空，使用同站API
```

`FILEMATE_INTERVIEW_LOCAL_ONLY=1`会有意禁止外发分析；保留这一隐私选择时，模型反馈不可用属于预期。设置允许外发也不代表用户授权；每场面试仍由用户主动授权，Microsoft语音有单独授权。

先核对现役systemd的Environment与EnvironmentFile来源及`FILEMATE_ENABLE_INTERVIEW_REVIEW`，再在受管理配置里加上述开关。包内的`40-interview-coach.conf.example`仅是示例，不自动安装；记录改前值与文件归属。关闭时把后端开关设0并切换本候选的coach-off前端，不清数据、不回退schema。

现役拓扑的暂存命令在`stage-command.txt`，使用manifest中的固定提交、release id和两份SHA256。将三个文件放到`/opt/filemate/incoming/<release-id>/`后，由服务器Python3.11运行匹配源码的`scripts/deploy_existing.py stage`。它会在独立目录安装生产锁定依赖、静态检查旧迁移未改写，并启动独立临时数据目录的候选探针；不会切换现役链接。先检查该拓扑仍与现役服务器一致，再执行。此次尚未执行Linux暂存、当前提交远端CI、生产数据库升级或生产回滚演练。

## 激活前必须取得的证据

1. Linux候选暂存、依赖锁、账号注册登录、逐题保存/授权/分析和自然语音探针通过；本机Windows跳过的Linux部署测试不能写为通过。
2. 进入维护窗口、停写，备份整个`/var/lib/filemate`及身份、配置、所有业务/治理库，记录所有权与指纹。依现役管理备份流程恢复到全新目录，验证完整性和schema26→27升级/读取，原备份保持不变。恢复候选必须清除授权、把在途分析标为interrupted，不能自动重放模型。
3. 新版本在独立的生产副本上运行，确认升级合同只追加27，旧回答首版回填、报告及个人导出可读。禁止将本地合成库上传覆盖生产。
4. 激活步骤另行授权，并记录旧后端/前端链接、开关配置与备份位置。现有部署工具只切换代码和静态资源，其失败自动回退不等同于跨schema数据回退；在schema27已写入后，不能直接启动任意旧服务写新库。
5. 切换后核对`/api/health`、`/api/ready`、`/release.json`与核心流程。新旧版本号同为alpha.4，health的version不足以识别后端代码；还须核对systemd实际主进程、启动时间、发布目录及包内源码摘要，并实际调用新教练接口。静态release.json不能替代生产库schema核验。此回执完成前，只能标记“准备完成”，不能标“已上线”。

## 回退

优先关闭新教练：保留新后端兼容读写schema27，后端coach=0并切coach-off构建；旧面试流程继续保存不可变版本。REVIEW=0仍保留读取、导出、取消、清空和确认删除等隐私能力。

升级前备份可用于维护窗口内、尚未开放公众写入的整包恢复；恢复时按新版恢复流程规范化授权与在途运行，再核验数据后重开服务。指定旧候选18b6d77c对schema27副本仅验证了离线读取，旧写入被拒绝，因此不能作为可写回退服务。已有公众新数据后，不允许直接覆盖回升级前快照；先保留增量导出与当前完整备份，选择兼容schema27的修复版本。没有down migration。

## 结论范围

这是面试交互子卡的工程候选，后续编程、真实岗位学习路径与原始功能账本没有据此全部完成。模型评价是模型参考；真实学生学习效果、专家评分校准和真实摄像头质量没有验收。每个回答的各次分析已保存并可导出，目前UI仅显示该回答最近一次分析。Monaco等懒加载分块有构建体积提示，首屏仍受项目预算检查；没有进行本轮全站生产容量实验。
