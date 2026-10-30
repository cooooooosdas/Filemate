# SDD ledger — plan: docs/superpowers/plans/2026-10-30-wrong-review-incremental-b.md

Spec read: incremental A audit, candidate CODEX_MASTER_PROMPT B1—B4; A approved 2026-10-30. Existing isolated codex/wrongbook-2-audit worktree reused. Initial HEAD d97a33c; 24 pre-existing modified tests preserved.
Pre-flight Task2→Task3: ReviewFilter.sort=recommended and server as_of feed preview; both require filtered eligible-due intersection and fixed priority tie order. No conflict.
Pre-flight Task1→Task4: source_hashes keeps byte selection stable; historical E manifests intentionally become stale after B edits, new evidence only. No conflict.
Pre-flight Task3→Task4: session-check is read-only; actual grading, idempotency and state transition remain existing attempts endpoint. No conflict.
Ruling: implement the concrete B plan after user explicitly approved A and requested B — current-session implementation already authorized — cost if wrong: local commits reversible, no deployment.
Ruling: recommendation order is fixed descending score/ascending due/id, independent of legacy direction — a recommendation has one stable rule, four existing sorts retain direction — cost if wrong: C control wording may need adjustment.
Task 1: in_progress; BASE=d97a33c.
Task 1: complete (commits d97a33c..8a9ac07, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_acceptance_compat.py -q --basetemp _working/review2-incremental-b-20261030/pytest-task1 → 1 passed in 0.11s)

Task 1 evidence: actual Python3.11.15 source_hashes succeeds (643 at that point); py310 Ruff passes. No Python3.10 executable installed.
Task 2: in_progress; BASE=8a9ac07. RED23 new tests; further RED11 JSON branch cases and RED3 corrupt metadata cases.
Ruling: new baseline default list/search already passes 500ms; do not change default wide-row sorting without causal evidence — preserve original behavior — cost if wrong: default optimization deferred.
Ruling: prioritize native JSON validation and snapshot-local grouped timestamp conversion after cProfile located Python callbacks; JSON-only still failed 4-concurrency, grouping passed359.23ms — exact parse_time/day logic retained, no global tenant cache — cost if wrong: many unique timestamps may retain capacity limits; final HTTP evidence required.
Ruling: label error_count as saved historical wrong answers, not necessarily objective for legacy imports — field provenance differs — cost if wrong: requires more detailed provenance UI in future.
Task 2: complete (commits 8a9ac07..27aa14d, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_insights.py filemate/tests/wrongbook/test_workspace_reads.py -q --basetemp _working/review2-incremental-b-20261030/pytest-task2 → 73 passed, 1 warning in 38.92s)

Task 3: BASE=27aa14d; RED22 service/route cases + RED3 client tests; GREEN31 backend +3 client; vue-tsc -b --noEmit exits0.
Ruling: add source_id to references and replayable filters to preview/check — otherwise course/source context can be lost at readiness — cost if wrong: new C client must replay these additive fields.
Ruling: extract the query implementation into _snapshot_page, shared by public page and checks — avoid reopening a second transaction while comparing current artifact digests — cost if wrong: broader query regression required, running full wrongbook suite.
Task 3: complete (commits 27aa14d..a604b7c, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook -q --basetemp _working/review2-incremental-b-20261030/pytest-task3-regression → 238 passed, 1 warning in 40.07s)

Task 4: BASE=a604b7c; registered-account ASGI/SQLite lifecycle passes1, including actual logout/login, replay-once, two objective correct rounds and a new wrong answer, today queue, foreign identity rejection. Service clock controlled, original synthetic question seeded directly (not upload/parser/real student evidence).
Ruling: first correction is not a delayed eligible review under the existing engine — retain rule, add a distinct delayed correct round in acceptance — cost if wrong: eligibility tests would understate an independent review.
Ruling: final full verify includes the full wrongbook directory, so avoid a redundant standalone full-directory run after adding the lifecycle test — developer requires risk-proportionate tests — cost if wrong: verify log must confirm all tests collected.

Final: independent fresh-context review completed; no established new Critical / Important / Minor findings. No reviewer edits; no second review; existing 24 modified tests untouched. No Critical / Important fix pass was required.
Final: Ruling: accept the reviewer's code-only review with executor's fresh full gate rather than duplicate heavy tests — identical tested code, 1790 backend / 281 frontend and exit0 — cost if wrong: runtime evidence is not independently rerun.
Final: Ruling: Python3.10 and production SQLite3.26 remain unverified at runtime — code inspection / forced-no-JSON1 parity are insufficient substitutes — cost if wrong: compatibility must be verified before release.
Final: Ruling: C visible UI/browser interactions, production deployment and real learning effects stay outside B — approved B is backend contracts plus API/SQLite validation — cost if wrong: these remain separate work and are not completion claims.
Final: Ruling: late delivery documentation receives executor integrity/self-check only — fresh review covered code and tests, no repeated review — cost if wrong: documentation has no independent review.
Final: Ruling: preserve P2-INC-B-01 at 1624.01ms for 9992 distinct due times, do not broaden B with migration/index architecture — ordinary HTTP fixtures pass but the original500ms capacity gate is not universally met — cost if wrong: high-cardinality four-concurrency remains slow; B is conditional.
Final: Ruling: keep the branch/worktree locally under the pre-agreed Task4 scope instead of reopening integration choices — user approved B implementation and the task explicitly says no push/deploy — cost if wrong: integration requires a later release task.
Final: Deferred minors: none established by this review. Capacity P2 is a known retained limitation, not a hidden minor.
Task 4: complete (commits a604b7c..0b7b832, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook/test_incremental_b_flow.py -q --basetemp _working/review2-incremental-b-20261030/pytest-task4-done → 1 passed, 1 warning in 5.35s)
