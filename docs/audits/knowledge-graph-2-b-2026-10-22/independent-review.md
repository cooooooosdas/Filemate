# B级独立审阅与修复记录

2026-10-22，独立只读审阅gpt-6-astra，范围61d5bce..cc0769d。审阅者未改文件、未调用模型、未跑全量。原结论With fixes：无确认Critical、7项Important、1项Minor。执行者将删除后旧提取请求500重新定级Important，一次修复全部8项；没有二次审阅，不将回归通过称为再次人工审阅通过。

## 修复结果

1. symbol identity / local C# preservation：`test_local_symbol_terms_and_same_payload_remain_distinct + test_symbol_collision_across_modes_does_not_reuse_other_concept`观察到RED后实现修复；最终GREEN。
2. cancelled draft aliases：`test_cancelled_group_alias_never_becomes_new_group`观察到RED后实现修复；最终GREEN。
3. failed source starvation：`failed_first_source_does_not_starve_later_pending_sources`观察到RED后实现修复；最终GREEN。
4. revoked candidates / relations selected again：`test_revoked_items_do_not_block_remaining_review + test_revoked_relation_is_not_selected_when_publishing_remaining_node`观察到RED后实现修复；最终GREEN。
5. merged original detail404：`test_merged_original_id_still_opens_concept`观察到RED后实现修复；最终GREEN。
6. member name/alias search and suggestions：`test_merged_member_names_aliases_remain_searchable_and_suggested`观察到RED后实现修复；最终GREEN。
7. merge preview source evidence：`test_merge_preview_displays_selected_source_evidence`观察到RED后实现修复；最终GREEN。
8. deleted source extract500：`test_deleted_source_extract_returns_fixed_error`观察到RED后实现修复；最终GREEN。

符号身份使用现有evidence_id承载course/source/revision/保留符号的原术语身份，legacy_node_id保留旧键含义；歧义置空并提示，D再人工关联旧题。既有B1随机ID通过不可变原候选核对复用，不依据可编辑显示名。schema仍31。真实第三次DeepSeek返回C/C#/C++/A-B/AB，确认5个独立概念；另两个旧键歧义项均有明确标记。

最终门禁退出0：后端1389通过、22跳过、5取消选择、3已有警告；前端149通过；Ruff、类型、构建、首屏体积通过。浏览器实际核对新版融合预览同时展示两份文件名与引用。没有遗留Minor，本阶段没有开放的已确认Important；这不代表未测试平台或整个产品不存在其他问题。

## 审阅未判断的边界及执行裁定

- C大画布、万节点及邻域性能：按已确认范围延期；大课程容量未验证。
- D跨课联系、旧学习键与掌握度：延期；新图谱不自动驱动旧学习事实。
- E Agent与真人实验：延期；无真实学习效果结论。
- 超过20000字符、通用教材和复杂关系总体质量：未知；3份原创短文不可外推。
- 供应商费用及其他供应商：费用未知，只记录1269真实token；其他供应商仅有适配合同测试。
- Linux发布、生产迁移/上线及桌面包装：未做；不能把Windows通过当上线门禁。
- 设备与完整无障碍：审阅者未做浏览器验收；执行者补有5尺寸、4主题、文本HTML安全，但无完整屏幕阅读器/实体设备认证。
- 最终文档和后加截图摘要：不在审阅固定HEAD；执行者自行对照真实日志与文件，未二审。
- 原24个用户修改测试：不评判无关内容；SHA256全部保持。

## 执行时的裁定

- Task 1: Ruling: Existing tests assert the old schema head literally (30). Update only head assertions in test_storage.py and test_interview_assessment_storage.py to 31 after observing failures; these are not among the preserved 24 files. This tests the new migration contract without suppressing real failures — cost if wrong: could conceal an unintended migration head; explicit upgrade/FK tests protect it.
- Task 1: Ruling: Same old-head literals also appear in career, digital-human, interview-review and programming migration regressions. The targeted run failed 4/149 solely on 31!=30, so update these four assertions while retaining history checks — cost if wrong: same migration-head risk, protected by explicit migration31/FK tests. No preserved test touched. A diagnostic selector named a nonexistent career test once (collection exit4); reran real complete files and kept their output.
- Task 1: Ruling: Admin backup governance regression also reports the business schema head; observed RED on [31]!=[30], update only the business head to 31 and keep separate governance version2 unchanged — cost if wrong: backup compatibility could be overstated; its real restore and integrity assertions remain active.
- Task9: Ruling: Run the single independent review after all B implementation and initial verification, before final task9 delivery commit, because task9 itself requires that review — avoids claiming completion before review — cost if wrong: final documentation-only status edits are not reviewed by that agent.
- Final: Ruling: Regrade deleted-source extract KeyError from Minor to Important — ordinary stale UI after source removal must return fixed404 rather than HTTP500 — cost if wrong: one additional targeted regression/fix, no wider feature scope.
- Final: Ruling: Keep schema31 and old graph keys, use deterministic evidence_id as the B occurrence identity over course/source/revision/normalized original term; legacy_node_id becomes only an unambiguous hint, collisions are NULL and explicitly marked — the planned lossy legacy key cannot identify distinct A-B/AB — cost if wrong: D must explicitly review ambiguous old-key associations; conservative ambiguity remains after undo rather than reviving an unsafe hint.
- Final: Ruling: C canvas/10000-node layout and neighborhood performance remain deferred as agreed — B is an evidence/review panel, not a capacity claim — cost if wrong: large-course usability/performance remains unverified.
- Final: Ruling: D cross-course manual links, old learning-key association and mastery remain deferred — no automatic migration or fabricated mastery — cost if wrong: new course concepts do not yet drive old learning evidence.
- Final: Ruling: E Agent and real student study remain deferred — no efficacy claim without a study — cost if wrong: no real learning-effect validation.
- Final: Ruling: Text beyond20000 chars and general/complex relation accuracy remain unknown — three short original documents only test scoped examples — cost if wrong: long-document coverage and model quality cannot be generalized.
- Final: Ruling: Supplier money cost and other provider behavior remain unknown — actual token counts recorded, no inferred billing — cost if wrong: fees or alternative-provider compatibility can differ.
- Final: Ruling: Linux release, production migration/deploy and desktop packaging remain outside this local B delivery — no production side effect authorized by B approval — cost if wrong: this is not a release-ready production gate.
- Final: Ruling: Physical devices and complete accessibility remain unverified by the read-only reviewer; executor verified five browser viewports/four themes — cost if wrong: screen-reader/device-specific gaps may remain.
- Final: Ruling: Final docs/screens added after review HEAD are executor-checked only — reviewer scope is fixed cc0769d — cost if wrong: final documentation could misstate a result; exact commands/evidence are linked.
- Final: Ruling: Original24 modified tests remain outside unrelated correctness review — hashes unchanged — cost if wrong: unrelated legacy test gaps are not resolved by this B work.
