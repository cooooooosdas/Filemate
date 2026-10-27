# SDD ledger — plan: docs/superpowers/plans/2026-10-26-wrongbook-workspace.md

User approved the full C plan and inline execution on 2026-10-26. Base dc5d35e; existing isolated codex/wrongbook-2-audit worktree verified. B product baseline e1c97e1. No deployment authorization in this card.

Pre-flight: Task 1 → 2/3/4/5: paged DTO, raw detail, receipt lookup and capability names match.
Pre-flight: Task 2 → 3/4/5: one shared submission controller, nullable result, scope and persistent metadata match.
Pre-flight: Task 3 → 4/5: workspace and legacy fallback preserve read-only records; ability flags must not trigger downgrade.
Pre-flight: Task 4 → 6: local batch is metadata only and not a server task, receipt IDs must be reverified.
Pre-flight: Task 5 → 6: all four entry points use the same typed three-state result, browser verifies mounted components.
Ruling: No new worktree or dependency reinstall — existing isolated worktree and installed runtimes are the tested B environment — cost if wrong: baseline dependency drift, checked by baseline and final verify.
Todo: 1 in progress; 2–6 pending. Fresh whole-branch reviewer only at the end.
Baseline: 67 passed. Task 1: HTTP/query RED 16 missing features; bad-data RED reproduced invalid cause UDF and legacy decoder list fallback; GREEN 97 passed, ruff and vue-tsc pass. No schema or external calls. Logs _working/wrongbook-c-20261026/task1-*.log. Own plan newline normalized to LF after diff-check caught Windows newline conversion; protected user tests untouched.
Task 1: complete (commits dc5d35e..daa4f58, tests: .venv/Scripts/python.exe -m pytest filemate/tests/wrongbook -q → Binary file /c/Users/胡希/.codex/worktrees/release-alpha3/FileMate-Project/.superpowers/sdd/2026-10-26-wrongbook-workspace/task-1-tests.log matches)
Task 2: complete (commits daa4f58..b83f54c, tests: node --test filemate/web/tests/wrongbook-submission.test.mjs filemate/web/tests/wrongbook-browse.test.mjs → ℹ duration_ms 169.8781)

Ruling: move review HTTP implementations to services/review-api.ts with lazy services/api.ts facades — build measured 144014 gzip > 143360 budget; preserve public call signatures and shared auth interceptors — cost if wrong: lazy import or cycle errors, covered by enabled build and real browser.

Ruling: direct route-only services/review-api.ts over named lazy facades; all callers retain the shared authenticated Axios client. New UI split the Vue runtime and added gzip overhead; group its interdependent runtime modules in Vite. Enabled build now 142786 / 143360 gzip bytes, without widening budget or excluding static imports. Cost if wrong: shared-runtime regressions, covered by full gate/browser.
Task 3: complete (commits b83f54c..be777be, tests: node --test filemate/web/tests/wrongbook-workspace.test.mjs → ℹ duration_ms 129.6396)
Task 4: complete (commits be777be..18fcc17, tests: node --test filemate/web/tests/wrongbook-focus.test.mjs filemate/web/tests/wrongbook-submission.test.mjs filemate/web/tests/wrongbook-workspace.test.mjs → ℹ duration_ms 226.0863)

Ruling: add scoped question-access read endpoint before legacy submissions — artifact/index entries do not carry wrong_id, so client cannot otherwise know 2.0 ownership before a rejected POST; no schema or writes added. Cost if wrong: extra bounded GET per question; measured in browser and full regression.
Task 5: complete (commits 18fcc17..0169526, tests: node --test filemate/web/tests/wrongbook-entrypoints.test.mjs filemate/web/tests/course-learning-state.test.mjs filemate/web/tests/course-practice-component.test.mjs → ℹ duration_ms 440.124)

Task 6: actual browser RED found focus receipt disappearing, disabled assistance from Vue optional Boolean defaults, lost verification reference on refresh, stale browse state erasing focus progress, incorrect schedule action names, dialog focus, code height, 200% header overflow and content scroll restoration. Node and real browser fixes underway; no C completion claim yet.
Ruling: use optional SQLite JSON1 for native stem search with guarded malformed JSON and UDF fallback when unavailable — measured 10000-row Python callbacks exceeded 500ms; no schema/runtime upgrade — cost if wrong: compatibility fallback may miss the performance target on SQLite without JSON1, explicitly remains an E/runtime measurement dependency.

Final review: fresh Astra reviewer completed 2026-10-27 against e1c97e1..90e8d46; previous usage-limit attempt produced no review. 0 Critical, 8 Important, 0 new Minor; all eight grades accepted by actual duplicate-write, false-success, lost-draft or unavailable-interface impact. One TDD fix pass follows, no re-review.
Final: Ruling: production SQLite3.26 migration/restore and JSON1-free performance remain E dependencies — local functional and timing checks cannot prove production runtime behavior — cost if wrong: production-only migration/performance failure; not approved for deployment here.
Final: Ruling: D AI analysis, precise graph links and incremental goals stay outside C — preserving the approved stage boundary — cost if wrong: those desired integrations remain unavailable until D.
Final: Ruling: no real-student learning or live-model claim — synthetic engineering checks only — cost if wrong: effectiveness and live service reliability remain unproven.
Final: Ruling: retain B derived-source deletion-preview undercount as the existing Minor — actual deletion works; C does not change this B boundary — cost if wrong: a user sees an understated review-event deletion count.
Final: Ruling: do not add cross-device batch sync or forced-close answer recovery — contract keeps unsent text only in memory and gives leave guards — cost if wrong: forced closure still loses unsent text.
Final: minor (deferred): B indirect derived-source delete preview can undercount review_events; actual cascade remains correct. No new C Minor reported.
Final: Ruling: course code-reading uses the existing supported short_answer type with a code field, displayed as code and saved pending — a synthetic fixture incorrectly used unsupported question_type=code and correctly received 422; do not expand the course grading contract or execute code — cost if wrong: code responses remain ungraded until evidence-based review; unified OJ stays a separate card.
Task 6: Ruling: task-done uses a closeout command that checks the just-completed mandatory full verify receipt, pinned source hashes and 21-check browser receipt, then reruns the complete frontend suite — avoid repeating the long backend run without a new source change — cost if wrong: stale evidence could be accepted; exact exit receipts and unchanged source hashes gate completion.
Final: fixed I1 shared pending overwrite — simultaneous entries preserve other pending keys and assisted flags RED→GREEN; actual Today two-entry refresh passes.
Final: fixed I2 unbound receipt recovery — saved-attempt provenance backend test and cross-question/version frontend recovery RED→GREEN.
Final: fixed I3 unretryable refresh/dont_know — actual component input lock and original-action retry RED→GREEN; browser answer and dont_know retain the original body/key.
Final: fixed I4 narrow focus hidden — actual 375px FocusReview RED with original CSS→GREEN; real submission and saved pending receipt pass.
Final: fixed I5 artifact draft loss — component switch/refresh RED→GREEN; real cancel keeps draft, both refresh guards prevent silent loss.
Final: fixed I6 artifact stale response after restore — mounted event listener RED→GREEN; signed synthetic restore with delayed response passes in workspace and artifact.
Final: fixed I7 stale revision after answer — revision/draft/late-response and failed-refresh write gate RED→GREEN; browser immediate diagnosis save succeeds.
Final: fixed I8 reusable graph leave permission — actual CourseLearning component one prompt RED→two prompts GREEN; browser A→B→C cancellation retains B draft.
Final suite: scripts/verify.ps1 -IsolateFrontend exit 0; 1648 backend passed,22 skipped,5 deselected,3 dependency deprecation warnings;257 frontend passed,0 failed;ruff,typecheck,build,budget pass. Enabled142888/143360gzip bytes; disabled142929/143360. Browser21/21,pageerror0,20 viewport-theme cases plus375px focus;10k list p95=45.6943ms,search p95=71.5513ms,UI feedback467.8361ms. Prior1532.636ms loaded failure retained. Schema35/local SQLite3.53.1;24 protected test hashes unchanged. 592 source hashes pinned for closeout. Production3.26/real models/students not tested.
Task 6: complete (commits 0169526..6ccf642, tests: powershell -NoProfile -ExecutionPolicy Bypass -File _working/wrongbook-c-20261026/finish-check.ps1 → C closeout: full verification exit 0, 21 browser checks, unchanged sources, frontend suite passed.)
