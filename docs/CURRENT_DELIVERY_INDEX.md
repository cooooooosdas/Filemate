# FileMate 当前交付资源索引

2026-10-04最新入口：[首页诗词接口与银蓝欢迎区交付](HOME_POETRY_DELIVERY_2026-10-04.md)，含源码/编译包匹配、792后端/33前端CI及8项真实公网验收。当前前端为`857782b`、后台为`9c133e1`，以站点`/release.json`分别核对。下一任务由用户指定为真实注册/登录及各功能/API实测，账号目前仍为预览。

最新整合入口：[已上线alpha.3的发布、测试与备份记录](INTEGRATED_RELEASE_ALPHA3.md)。主分支、最终CI、22页/9接口和真实模型合成资料闭环已验证；下列alpha.1/alpha.2交付是历史证据，上线版本、提交以alpha.3记录及站点`/release.json`核对。

2026-10-03后续开发：[DEV-01学习资料入口](LEARNING_TEXT_INPUTS_DELIVERY_2026-10-03.md)已完成，支持UTF-8 Markdown及代码文本本地导入、引用/会话复用和确认图谱；760后端、18前端及类型/构建/原体积门禁通过；最终同包46项TLS父级/91路径、12视觉、17归档、25学习工作区、18知识库通过。原视觉基线`UI-2026.10.03-r1`及交付包保留，新开发基线`DEV-01-2026.10.03`独立固定；下一卡UI-02整合图谱的提取、核对、证据与学习路径。软件仍为`1.3.0-alpha.1`，未部署，真实研究尚未采集。

- 最新：[布局、动效与图标交付](UI_LAYOUT_CLOSEOUT_2026-10-03.md)、[开发流程v2](DEVELOPMENT_WORKFLOW_V2.md)、[知识库](../filemate/web/src/views/Knowledge.vue)、[任务内导航](../filemate/web/src/components/TaskNavigation.vue)、[入场/指针反馈](../filemate/web/src/components/MotionSurface.vue)、[18项专项](../scripts/acceptance/knowledge_layout.mjs)。本地视觉基线`UI-2026.10.03-r1`固定最终副本与文件哈希；46项TLS父级/91路径、12视觉/17归档/23工作区/18知识库通过，线上未更新。

核对日期：2026-10-03。此索引指向现役源码、合同、测试和阶段报告；五模块/服务器历史实测见[总验收](INTEGRATED_AUDIT_2026-10-02.md)，B2/B3工程完成状态见[收口交付](B2_B3_ENGINEERING_CLOSEOUT_2026-10-02.md)，当前前端质量见[阶段交付](FRONTEND_PRODUCTION_QUALITY_DELIVERY_2026-10-03.md)。完整后续要求见[执行账本](FULL_PROJECT_EXECUTION_PLAN.md)。历史报告保留当时结果，不等同于当前线上版本。

## 权威合同与运行

- [README](../README.md)：现役入口、技术栈、环境变量与schema v24。
- [项目规则](../AGENTS.md)、[分阶段任务合同](AGENT_DEVELOPMENT_EXECUTION_PLAN.md)、[设计系统](../design-system/filemate/MASTER.md)。任务合同中的旧v9基线属于2026-08-27历史，当前版本以migration为准。
- [公共API合同](../filemate/docs/API_SPEC.md)、[FastAPI入口](../server.py)、[迁移与存储](../filemate/execution/storage.py)、[前端API调用](../filemate/web/src/services/api.ts)。
- [开发启动](../scripts/dev.ps1)、[全项目门禁](../scripts/verify.ps1)、[持续集成](../.github/workflows/ci.yml)、[网站/桌面部署边界](DEPLOYMENT.md)。
- [生产资源预算](../filemate/web/scripts/check-bundle.mjs)、[生产浏览器专项](../scripts/acceptance/frontend_production.mjs)：真实组件与指令、资源中断主动恢复、首页全部静态依赖累计预算。
- [大背景重新选型与全站配色](BACKGROUND_REDESIGN_DELIVERY_2026-10-03.md)、[可复制改写提示词与来源](BACKGROUND_REDESIGN_PROMPT_2026-10-03.md)：用户否定旧绿白底色后，重新制作钴蓝/琥珀/银蓝三份整页样例，实装钴蓝光束、冰蓝画布和阅读表面；实际编译包截图与测试见交付报告。
- [视觉选型与首轮实装](FRONTEND_VISUAL_UPGRADE_DELIVERY_2026-10-03.md)、[首页](../filemate/web/src/views/Home.vue)、[原创背景](../filemate/web/src/components/KnowledgeBackdrop.vue)、[视觉专项](../scripts/acceptance/visual_upgrade.mjs)：首轮绿白方案为历史快照；9项主要导航与方向切换继续保留，当前配色以上方新背景交付为准。
- [分类与命名一体审核](../filemate/web/src/views/FileReview.vue)、[实际上传/归档/撤销专项](../scripts/acceptance/file_review.mjs)、[交付报告](INTEGRATED_FILE_REVIEW_DELIVERY_2026-10-03.md)：同屏分类/名称/日程预览和下载；17项实际操作、42项网关、91路径与10项视觉通过，旧URL兼容，API/schema不变。
- [学习工作区](../filemate/web/src/views/LearningWorkspace.vue)、[产物阅读](../filemate/web/src/components/LearningArtifact.vue)、[23项专项](../scripts/acceptance/workspace.mjs)、[交付报告](LEARNING_WORKSPACE_VISUAL_DELIVERY_2026-10-03.md)：大字号两栏、目录切换、四任务/按需创建、真实保存与引用/作答/下载/恢复、输入保护；最终同包45项父级TLS、28页面、4本地视觉、10首页与17归档通过。模型输出来自明确的[本地合成HTTP夹具](../scripts/acceptance/workspace_model_fixture.py)，不代表真实模型或学习效果。
- [实际HTTPS预检](../scripts/acceptance/gateway_preflight.py)、[28项网关页面](../scripts/acceptance/gateway_production.mjs)、[交付报告](GATEWAY_PREFLIGHT_DELIVERY_2026-10-03.md)：40项、91路径、22页和实际本地视觉推理；8访客128次有限读取；本机结果不表示线上同步或正式容量。
- [托管备份/恢复](../filemate/operations/backup.py)、[22项专项](../filemate/tests/test_backup.py)、[19项实际匿名恢复演练](../scripts/acceptance/backup_restore.py)、[手册](BACKUP_RESTORE_RUNBOOK.md)、[运维交付](OPERATIONS_BACKUP_DELIVERY_2026-10-03.md)：主库、匿名分库、附件和身份密钥，预览确认/停写/新目录恢复，不自动覆盖或上线。
- [Python包合同](../pyproject.toml)：包含运行期分类规则、提示词与面试报告字体；最终wheel解包检查及SHA256见本轮 `python-package-smoke.json`，不是桌面安装包。

## 五大模块与学习计划

### V2.1 数字人学习导师

[页面](../filemate/web/src/views/DigitalHuman.vue)、[语音和播放状态](../filemate/web/src/digital-human/)、[后端回归](../filemate/tests/test_digital_human.py)、[浏览器闭环](../scripts/acceptance/digital_human.mjs)、[关闭检查](../scripts/acceptance/digital_human_disabled.mjs)、[V2.1.1交付](V2_1_1_DIGITAL_HUMAN_DELIVERY.md)。采用浏览器真实TTS和近似口型；音质、音素同步及外部供应商未完成质量实验。

### V2.2 知识图谱与证据画像

[页面](../filemate/web/src/views/KnowledgeGraph.vue)、[提取/画像/路径](../filemate/study/knowledge_graph.py)、[领域测试](../filemate/tests/test_knowledge_graph.py)、[API测试](../filemate/tests/test_graph_api.py)、[存储测试](../filemate/tests/test_graph_storage.py)、[教材闭环](../scripts/acceptance/knowledge_graph.mjs)、[关闭检查](../scripts/acceptance/knowledge_graph_disabled.mjs)、[阶段交付](V2_2_KNOWLEDGE_GRAPH_DELIVERY.md)。真实作答作为反馈依据；有限本地句式不代表一般教材提取质量。

### V2.3 编程练习与评测

[页面](../filemate/web/src/views/Programming.vue)、[Monaco](../filemate/web/src/components/CodeEditor.vue)、[评测与隔离](../filemate/programming/)、[测试](../filemate/tests/test_programming.py)、[原生49项](../scripts/acceptance/programming_native.py)、[浏览器闭环](../scripts/acceptance/programming.mjs)、[关闭检查](../scripts/acceptance/programming_disabled.mjs)、[阶段交付](V2_3_PROGRAMMING_DELIVERY.md)。8道原创题和C++17真实判题；Windows MSVC/LPAC现役，Linux网站缺隔离适配器。

### V2.4 面试增强与复盘

[页面](../filemate/web/src/views/Interview.vue)、[复盘组件](../filemate/web/src/components/InterviewReviewPanel.vue)、[视觉与语音处理](../filemate/web/src/interview/)、[本机模型资源](../filemate/web/public/interview-vision/)、[报告领域](../filemate/interview_review/)、[测试](../filemate/tests/test_interview_review.py)、[浏览器闭环](../scripts/acceptance/interview_review.mjs)、[生产资源检查](../scripts/acceptance/interview_vision_production.mjs)、[关闭检查](../scripts/acceptance/interview_review_disabled.mjs)、[阶段交付](V2_4_INTERVIEW_REVIEW_DELIVERY.md)。工程输入为公开图片合成流；模型评分与导师一致性待真实配对校准。

### V2.5 求职训练中心

[页面](../filemate/web/src/views/Career.vue)、[岗位/训练领域](../filemate/career/)、[成长组件](../filemate/web/src/components/CareerGrowthPanel.vue)、[测试](../filemate/tests/test_career.py)、[浏览器闭环](../scripts/acceptance/career.mjs)、[路由与草稿](../scripts/acceptance/career_state.mjs)、[成长回归](../scripts/acceptance/career_growth.mjs)、[生产包检查](../scripts/acceptance/career_production.mjs)、[关闭检查](../scripts/acceptance/career_disabled.mjs)、[阶段交付](V2_5_CAREER_DELIVERY.md)。3份日期快照来自2家公司，7道自编基础题；不代表实时招聘库、企业真题或录用预测。

### B2 岗位证据到学习计划

[计划领域](../filemate/career/planning.py)、[计划面板](../filemate/web/src/components/CareerPlanPanel.vue)、[现役学习页](../filemate/web/src/views/StudyPlan.vue)、[19项专项](../filemate/tests/test_career_planning.py)、[真实进度/导出闭环](../scripts/acceptance/career_planning.mjs)、[交付报告](B2_CAREER_LEARNING_PLAN_DELIVERY.md)。预览只读，确认后持久化，旧证据失效、重复请求、撤销/恢复与岗位删除均有回归。

### B2 学习统计证据说明

[纯聚合](../filemate/study/evidence_profile.py)、[成长页](../filemate/web/src/views/Growth.vue)、[证据面板](../filemate/web/src/components/LearningEvidencePanel.vue)、[18项领域/存储专项](../filemate/tests/test_evidence_profile.py)、[9项浏览器验收](../scripts/acceptance/evidence_profile.mjs)、[收口交付](B2_B3_ENGINEERING_CLOSEOUT_2026-10-02.md)。按练习/错题/计划/面试逐项说明样本数、日期、公式、异常排除与最近原记录；空、少量、历史证据和本地回退不冒充能力结论。

## 原有六条主流程

- 文件草稿/确认/归档/撤销：[确认执行器](../filemate/execution/confirmation_executor.py)及[回归](../filemate/tests/test_confirmation_executor.py)。
- 资料/产物/对话重启恢复、引用与拒答、练习与复习、每日计划、五轮面试：[持久化集成测试](../filemate/tests/test_server_persistence.py)。模型输入使用明确合同Stub；不代替真实供应商质量实验。
- [流程4独立API验收](../scripts/acceptance/flow4_api.py)、[资料生命周期独立验收](../scripts/acceptance/a3_lifecycle.py)、[22页/9接口冒烟](../scripts/acceptance/browser_smoke.mjs)。

## 真实评测准备包

[采集协议](REAL_USER_EVALUATION_PROTOCOL.md)、[工具说明](../evaluation/README.md)、[前后测分析](../evaluation/analyze_study.py)、[匿名反馈分析](../evaluation/analyze_feedback.py)、[三类对照实验](../evaluation/analyze_competition_trials.py)、[导师校准](../evaluation/calibrate_interview.py)、[分析数据合同测试](../filemate/tests/test_evaluation_study.py)。

B3工程：[严格CSV合同](../evaluation/csv_contract.py)、[探索性区间](../evaluation/intervals.py)、[匿名Beta导出](../evaluation/prepare_beta.py)、[采集与RC合同测试](../filemate/tests/test_beta_tools.py)、[RC只读准备器](../scripts/acceptance/release_readiness.py)、[RC清单](RC_ACCEPTANCE_CHECKLIST.md)、[版本说明草稿](RELEASE_NOTES_V1_3_0_DRAFT.md)。拒绝额外身份列、非法行宽/范围、重复参与者和混合样本；真实研究仍待采集与团队审查。

空白采集表：[前后测](../evaluation/datasets/user_study.template.csv)、[双人引用标注](../evaluation/datasets/retrieval_annotations.template.csv)、[单/多Agent](../evaluation/datasets/agent_ab.template.csv)、[文字/多模态面试](../evaluation/datasets/interview_ab.template.csv)、[普通提醒/学习伙伴](../evaluation/datasets/companion_ab.template.csv)、[导师评分](../evaluation/datasets/interview_expert_scores.template.csv)。全部只有表头，须取得实际知情同意并采集匿名记录。

合成资源：[41例检索](../evaluation/datasets/retrieval_cases.json)、[5例面试](../evaluation/datasets/interview_cases.json)、[检索问答草稿](../evaluation/QA_PAIRS_README.md)、[工程评测运行器](../evaluation/run_evaluation.py)。`.example.csv`只验证统计流水线，不计入真实实验。

[合成学习资料实测脚本](../scripts/acceptance/synthetic_learning.py)生成原创7份材料并连接现役模型适配层；最终85项通过、20次实际模型调用，证据在 `_working/synthetic-learning-20261002/run5/`。仅为工程闭环，不计入学生、问卷或导师研究。

## 总测试与复核证据

[统一浏览器运行器](../scripts/acceptance/integrated_browser.py)、[只读网站健康抽样](../scripts/acceptance/website_health.py)、[资源与结果汇总器](../scripts/acceptance/collect_audit.py)、[复跑说明](../scripts/acceptance/README.md)。

本轮完整机器证据位于项目忽略目录 `_working/integrated-audit-20261002/`：`summary.json`、`resource-inventory.json`、门禁日志、分组结果、响应式截图、实际下载、只读服务器日志和失败复现。索引包含受Git管理/未忽略的源码及文档SHA256；不读取密钥内容，不包含依赖缓存和私人应用数据库。独立数据库仅有工程输入，保留用于复核。

后续 B2/B3 证据独立保留于 `_working/b2-b3-20261002/`：专项和全门禁日志、`browser-b2/`、合成Beta导出、空导师模板报告、测试前 `source-baseline-final.json` 与 RC 汇总。历史结果不覆盖，也不把不同日期/代码快照的通过数相加冒充同一次全量测试。

2026-10-03工程证据在`_working/project-continuation-20261003/`：当前`verify-with-backup.log`为740后端/18前端通过，生产资源预算、22页/9接口纠错复测、8项生产专项、22项备份专项及19项匿名HTTP恢复演练通过。初次19组中的一项Vite刷新失败保留在`browser-full/`，修复后的受影响项在`browser-optimizer/`；不能改写为一个快照的全绿结果。线上只读抽样、wheel校验、源码指纹和仍待完成要求见`summary-final.json`及两份本日阶段报告。

视觉及审核证据在`_working/visual-upgrade-20261003/`：三份样例、首轮与后续冻结包、实际TLS截图、17项文件操作、当前740后端/18前端门禁和公开源码基线。19组业务/关闭首次18组通过，面试模型开发期自动刷新已修复；最终副本的面试14项、页面冒烟及8项生产专项复测通过，分别保留于`browser-full/`和`browser-followup/`，不把跨快照结果写成同次全绿。
