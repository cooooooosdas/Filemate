# 目标运行时与回退验证方法

本轮验证提交a7422eca3b16e4141812f2aa6ab8b87488805a93；Linux现役解释器Python3.11.13绑定SQLite3.26.0。生产数据库仅以mode=ro探测schema、JSON1与变量上限，不导出业务行；未切换服务。下列数据全部原创合成，不能代替真实数据迁移演练或生产负载测试。

1. 从指定Git提交归档filemate下Python源码和scripts/acceptance/orchestrator_runtime.py，排除测试、密钥、数据库、上传资料和前端依赖；记录归档SHA256。
2. 在目标主机新建0700临时目录，将归档放入该目录并再次核对SHA256。用tar的data过滤器提取；运行环境指向这个目录的新合成数据路径，使用development/local身份。
3. 在候选源码目录，以现役解释器运行`python -m scripts.acceptance.orchestrator_runtime --self-test --out _working/target-self-test`。检查schema36、真实预览／确认／幂等／撤销、领域表摘要不变、integrity_check=ok及foreign_key_check无错误。不是只执行SQLite命令行或查看版本号。
4. 用现役旧版本alpha4-41a360bd2f32源码，在另一新目录创建schema34数据库：一份Source、一题questions Artifact、真实错答／错题、含已完成任务的reverse_goal_plan、真实study_plan及第0日完成记录。创建升级前SQLite备份。
5. 记录sources、artifacts、study_plans、quiz_attempts、wrong_questions的原列名；按第一列排序，逐表序列化原列值并取SHA256。候选init_schema将该合成库升级为36，重新对相同旧列计算摘要；必须全部相同。用真实SnapshotReader和project_tasks确认旧目标／计划完成状态及错题仍可读，并验证完整性与外键。
6. 将升级前34备份复制到另一个新目录，使用旧版本源码和现役解释器读取；确认schema34、目标存在、完整性ok。这是“匹配代码＋升级前备份”回退，未把36原地降级或让旧代码盲读升级库。

本轮归档SHA256为aec219d8e1814899f5dfedf3ad5390f81f0b0c705ad9ed573eca453d8857f26a。机器结果见target-runtime.json；完整原始结果与执行脚本保留在项目_working/orchestrator-b-20261031及_working/orchestrator-b-plan-20261031目录，不包含生产业务资料。再次执行须新建输出目录，不能覆盖本轮证据。
