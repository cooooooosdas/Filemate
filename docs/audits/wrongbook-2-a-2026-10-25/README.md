# 错题复盘2.0 A级审计证据

对应[审计与待确认设计](../../superpowers/specs/2026-10-25-wrongbook-2-design.md)。本轮没有产品代码、schema或线上配置改动；所有写入来自隔离的原创合成库。

归档文本统一使用UTF-8与LF换行；原始运行日志保留于忽略的`_working/`，归档不改写测试内容或结果。

- `verification.json`：本轮测试范围、结果与未执行项；不是全产品发布验收。
- `observations.json`：5组合成探针的实际观察、schema/FK/索引结构；证明缺口存在，不代表缺口已修复。
- `public-readonly.json`：HTTPS发布标记与就绪读取。保留初次错误路径404和正确`/api/ready`的200；没有生产写入。
- `backend-output.txt`、`characterization-output.txt`、`frontend-output.txt`：实际完成输出。
- `characterization-test.py.txt`：临时审计脚本的可复现源，不是产品实现，也不加入默认测试收集。
- `builder-check.md`：A级设计的独立可实施性检查及处理记录。
- `closeout-validation.json`：2026-10-26文档链接、JSON、测试输出与原有文件哈希的交付核对，不是重新执行的产品测试。

后端原有回归的完整范围：

```powershell
$env:PYTHONUTF8='1'
New-Item -ItemType Directory -Path '_working/wrongbook-a-reproduce' -Force | Out-Null
.venv/Scripts/python.exe -m pytest filemate/tests/test_p1_wrongbook.py filemate/tests/test_study.py filemate/tests/test_goal_planner.py filemate/tests/test_server_persistence.py filemate/tests/course_graph/test_learning_api.py filemate/tests/course_graph/test_learning_evidence.py filemate/tests/course_graph/test_runtime_compatibility.py -q -m 'not e2e' --basetemp=_working/wrongbook-a-reproduce/regression-data
node --test filemate/web/tests/course-learning-state.test.mjs filemate/web/tests/course-practice-component.test.mjs
```

重现现状探针时，先把`characterization-test.py.txt`复制为上述忽略目录中的`test_audit_observations.py`，再由项目根目录运行：

```powershell
.venv/Scripts/python.exe -m pytest _working/wrongbook-a-reproduce/test_audit_observations.py -q --basetemp=_working/wrongbook-a-reproduce/probe-data
```

`--basetemp`应使用本次新建的专用空目录；不要指向用户资料目录。测试会通过tmp_path/FILEMATE_DATA_DIR隔离数据，不读取生产账户。

首轮命令未先建basetemp父目录，145个setup error均在临时路径创建阶段发生；未执行任何业务测试。完整首轮日志在本机`_working/wrongbook-a-regression.log`，后续使用新目录重跑为144 passed/1 skipped；没有修改产品或测试以规避失败。

没有执行全量verify、浏览器视觉、真实模型、实体设备或真人研究，后续阶段必须补上相应验收。保存原24个用户修改测试的哈希核验记录在本机`_working/wrongbook-a-20261025/preserved-tests.json`，这些文件不属于本轮修改。
