# SDD ledger — plan: docs/superpowers/plans/2026-10-28-wrongbook-learning-loop.md

2026-10-28 用户明确回复“确认”，授权本计划在当前会话连续逐项实施，最终一次独立审阅；D结束后再验收E，不部署。

Workspace: existing linked worktree C:/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project; branch codex/wrongbook-2-audit; base 4e7607b.
Spec: docs/superpowers/specs/2026-10-25-wrongbook-2-design.md reachable; accepted seven product decisions apply.

Pre-flight shared interfaces:
- Tasks 1→2: server-built Context/input_digest/private source dependencies → claim and cache; consistent, GET never supplies authority.
- Tasks 2→3: claim(view,claimed,epoch)/finish/fail/cancel → exactly one bounded call; 20s deadline and 30s recovery lease consistent.
- Tasks 1/3→4: context and Analyze command → precise credentials/consent route; consistent.
- Tasks 1/4→5: real context and versioned diagnosis events → bounded tasks and undo; consistent, plans reuse existing StudyPlan.
- Tasks 4/5→6: ReviewAnalysis DTO and preview/confirm receipts → frontend controllers; preserve current ref and epoch.
- Tasks 1–6→7: lifecycle, fault, UI and recorded-evidence contracts → final gate/reviewer; consistent.

Todo: Task 1 in progress; Tasks 2–7 pending.
Task 1: Ruling: Context增加非敏感credential_mode=server|browser，GET不携带密钥；后续POST必须保持同模式 — 浏览器BYOK固定DeepSeek，不能与服务器自定义Provider的预览身份混用 — 若调用方遗漏模式将拒绝旧摘要，需重新预览。
Task 1: complete (commits 4e7607b..0cd49d5, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_context.py filemate/tests/course_graph/test_learning_links.py filemate/tests/wrongbook/test_workspace_reads.py -q → Binary file /c/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project/.superpowers/sdd/2026-10-28-wrongbook-learning-loop/task-1-tests.log matches)
Task 2: complete (commits 0cd49d5..a3f2c9f, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_repository.py filemate/tests/wrongbook/test_analysis_privacy.py filemate/tests/test_p1_personal_backup.py filemate/tests/test_backup.py filemate/tests/wrongbook/test_schema.py filemate/tests/test_deploy_migration_contract.py -q → Binary file /c/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project/.superpowers/sdd/2026-10-28-wrongbook-learning-loop/task-2-tests.log matches)
Task 3: complete (commits a3f2c9f..3cead15, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_analysis_service.py filemate/tests/test_bounded_llm_call.py filemate/tests/test_llm_client.py filemate/tests/test_runtime_governance.py -q → Binary file /c/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project/.superpowers/sdd/2026-10-28-wrongbook-learning-loop/task-3-tests.log matches)
Task 3 supplemental: 混合目录运行时显式注册review_store，扩展回归90通过（含上下文完整字节限制）；产品约束未放宽。
Task 4: complete (commits 3cead15..5e437f2, tests: powershell -NoProfile -ExecutionPolicy Bypass -File .superpowers/sdd/2026-10-28-wrongbook-learning-loop/verify-task4.ps1 → ℹ duration_ms 134.2647)
Task 5: Ruling: 增量计划selection增加可选attempt_id/course_id，省略时选择本题最新真实作答且不带课程；由服务端重建上下文 — 预览必须绑定用户所选作答和单门课程，而原计划仅列出任务编辑字段 — 若调用方不传这些ID，计划仍可用但按题目自身来源生成。
Task 5: Ruling: 相邻测试命令将wrongbook目录的文件连续排列，再运行父目录test_goal_planner.py — pytest9.1.1按节点对象身份匹配fixture，交错目录参数会重建Directory节点导致错误缺失fixture；产品合同与断言不变 — 若判断错误，全目录总门禁仍将暴露实际问题。
Task 5: complete (commits 5e437f2..5a97d5e, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_learning_plans.py filemate/tests/wrongbook/test_consumers.py filemate/tests/test_goal_planner.py -q → 19 passed, 1 warning in 2.31s)
Task 6: complete (commits 5a97d5e..ca85910, tests: powershell -NoProfile -ExecutionPolicy Bypass -File .superpowers/sdd/2026-10-28-wrongbook-learning-loop/verify-task6.ps1 → })
Task 7: Ruling: 同步test_career.py和test_digital_human.py的现役schema断言及test_storage迁移列表／末项名到36 — Task2清单遗漏这两处现役消费者，全门禁实测暴露；只更新最新版本期望，旧迁移内容与历史合同不变 — 若旧运行时不兼容，仍须E级实测，不能据此发布。

Final: fixed I1 token-body retention — test_learning_previews_never_persist_copies_of_private_text[plan/adopt/undo] RED→GREEN; targeted backend 33/33; full backend 1718 pass, 22 skips, 5 e2e deselected.
Final: fixed I2 draft/unknown-confirmation loss — mounted Hub revision test plus evidence refresh controller tests RED→GREEN; frontend 276/276.
Final: fixed I3 terminal410 recovery — a server 410 tombstone ends uncertainty test RED→GREEN; frontend 276/276.
Final: fixed I4 cascade preview undercount — test_source_preview_counts_analysis_cascaded_from_multisource_questions RED→GREEN; full backend 1718 pass.
Final: fixed I5 historical quote ownership — test_history_detail_uses_its_own_bounded_source_quotes and historical SFC quote test RED→GREEN; full gates pass.
Final: fixed I6 undo during reload — the hub cannot start undo while evidence is still loading RED→GREEN; real browser adoption and plan undo PASS.
Final: minor (deferred): repeated (attempt_id, quote) within one cause can display the same real quote twice; no grade/statistics impact. Cost if wrong: reader overestimates independent supporting evidence; prioritize deduplication later.
Task7 supplemental: screenshot revealed dark graph link contrast1.55; real DOM RED→GREEN13.12 and four-theme link assertions added; browser11/11, zero pageerror.
Latest authorization 2026-10-29: user requests complete wrongbook round without further confirmations; supersedes D/E stage pause. No production push/deploy implied.
Task 7: complete (commits ca85910..92e06d4, tests: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_wrongbook_learning.ps1 -CheckRecordedEvidence → ℹ duration_ms 12730.5677)
