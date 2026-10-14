# FileMate 已知缺陷修复 · 2026-10-14

## 范围与状态

按用户“修复目前已知的项目bug”指令，在现役发布工作区修复已确认缺陷，不扩展新业务功能。旧七项P1以各关闭记录为准，本轮不重复声明。

当前为本地修复候选，尚未部署。业务schema26、治理schema2及已发布迁移均不变；源码与依赖应作为同一批交付。

## 修复内容

| 问题 | 原行为 | 修复行为 |
|---|---|---|
| AUD-12 上传文件名 | 300字符文件名直接落盘，操作系统拒绝后500，并可能留下空目录 | 读取正文前校验255 UTF-8字节上限、跨平台保留名/非法字符，400明确提示；落盘失败503，删除仅本次部分副本 |
| AUD-09 通用结构化输出 | Schema只写入Prompt，JSON可解析即接受；解析错误携带前200字符原文 | Schema配置先验证，返回内容离线执行结构校验；保留旧数组接口，拒绝非有限数及非法根；异常不带模型原文 |
| AUD-14 部署就绪 | 仅检查`/api/health`和版本，数据库不可用仍可能放行 | 独立只读`/api/ready`检查核心数据库/版本；部署需同时通过两个探针；不创建游客和学习数据 |
| Microsoft 自然语音403 | edge-tts 7.2.8与上游握手不兼容 | 所有运行清单/本地锁/生产锁统一7.3.1，沿用既有授权、限流、超时、失败提示 |

语音依据：[7.3.0发布说明](https://github.com/rany2/edge-tts/releases/tag/7.3.0)新增上游令牌协议适配，[7.3.1](https://github.com/rany2/edge-tts/releases/tag/7.3.1)继续修复受系统语言影响的日期解析。上游变更不等于本机或生产已经验证成功。

## 验证记录

- 上传/就绪探针12例通过，包含有效中文资料、超长及保留名、部分写入失败清理、账号解析故障旁路、缺失/损坏/旧Schema数据库和损坏治理账本；资料均为合成数据。
- 结构化输出与用量专项51例通过：结构24例、既有可观测性27例。Schema配置无效且未外发时清空本次用量；实际供应商调用成功后解析失败仍保留真实消耗。
- 直接执行部署脚本中的真实`health()`函数：就绪放行、数据库故障拒绝、就绪版本陈旧拒绝三例通过。Windows不能替代Linux权限/快照/服务切换实测。
- 默认晓晓和云夏均通过真实`POST /api/digital-human/speech`返回200，耗时3.66/3.77秒，音频39024/41616字节，响应no-store；ffprobe及ffmpeg完整解码通过，均为24kHz单声道MP3，时长6.504/6.936秒。只外发原创合成句，不使用学生资料或模型密钥。
- 首次`verify.ps1 -IsolateFrontend`的静态检查通过，后端1096通过、2失败、20跳过、5排除；两处失败均为旧测试要求健康检查签发Cookie，与新只读探针合同冲突。已将伪造身份验证转至业务接口，两个探针均断言不发Cookie；租户隔离及上传/就绪补测18例通过。
- 前端在隔离副本完成`npm ci`、55项测试、Vue类型检查、生产构建与`check:bundle`，均通过。
- `uv pip check`确认103个已安装包兼容；新增/修改Python代码Ruff与`git diff --check`通过。最终完整后端使用临时pytest-xdist按文件分配四进程重跑，项目依赖与锁不增加测试插件：**1099通过、20跳过、0失败**，耗时354.32秒。
- 跳过项包括Linux专属部署/判题分支、缺少的历史DOCX/PDF/PPTX测试样本、可选OCR模型和符号链接权限；需要真实模型密钥的e2e标记未纳入本次回归。不能将其描述为所有外部服务、全部平台与真实用户实验均已通过。

最终后端复现命令（仅临时叠加测试工具）：

```powershell
$env:PYTHONUTF8 = '1'
uv run --no-sync --with pytest-xdist pytest filemate/tests -q -m 'not e2e' -n 4 --dist loadfile
```

本轮修复验证通过；这不是一次新的全产品审计或生产部署。已保存本地修复，未推送或切换线上版本。

临时证据位于`_working/bugfix-20261014/`，包括首次`verify.log`、最终`backend-final.log`、`frontend.log`、`speech-result.json`、两段合成MP3与`deployment-gate.json`，不提交运行数据库和音频。新测试不代表真实学生学习效果。

## 依赖锁重建

```powershell
uv sync --extra dev
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file _working/bugfix-release-constraints-20261014.txt
uv pip compile requirements-desktop.txt --constraint _working/bugfix-release-constraints-20261014.txt --python-version 3.11 --python-platform x86_64-manylinux2014 --generate-hashes --output-file deploy/requirements-production.lock
```

## 仍需如实保留的边界

- 就绪探针检查核心共享数据服务，不遍历全部匿名/注册空间；不代替备份恢复、全库完整性或外部供应商验证。
- 通用Schema校验修复结构合同，不保证AI事实正确；未提供Schema的旧调用仍依赖模块验证，真实评分效度待真实研究。
- 原审计中的解析隔离/压缩展开预算、细粒度功能开关、邮箱归属验证、检索与评分校准等未由本轮四项修复自动关闭。
- 不将依赖升级、合成测试或未部署候选描述为线上故障已消失；生产需按现役备份、候选验收、切换和回退流程发布。
