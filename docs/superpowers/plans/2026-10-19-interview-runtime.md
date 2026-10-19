# Interview 2.0 recoverable runtime implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Stage 3: continuous server timing and recoverable knowledge/commerce streamer practice.
**Architecture:** A transactional runtime owns task transitions; existing coach storage owns immutable answers and explicit AI authorization. Rule-selected simulated tasks and audience comments work offline; current AI feedback stays optional, budgeted and evidence based.
**Tech Stack:** Vue 3, TypeScript, FastAPI, SQLite migration 29, Python.
**Spec:** `docs/superpowers/specs/2026-10-19-interview-2-design.md` (Stage 3).

## Global Constraints

- Continuous timing uses the original server deadline; no pause/reset on reload, offline recovery or backup restore. Early finish is explicit.
- A prepared session starts only by explicit action. Restoration interrupts running sessions; resumption requires an explicit action.
- Maximum 30 simulated audience comments, minimum 15-second cooldown; maximum 12 reserved AI transport calls including repair, plus workspace quotas.
- Commands check revision, request key/digest, task, deadline and current attempt in one transaction. Legacy write routes cannot advance timed sessions.
- No inferred emotions, fabricated scores or new six-dimension rubric. Product claims use only supplied facts.
- Existing immutable answers, backups, export/delete, feature rollback and old fixed sessions remain usable.
- Preserve 24 existing unrelated modified test files; do not deploy this stage without acceptance.

## Review Focus

1. A second tab with a stale task/revision must not save into another task (Task 1 conflict test).
2. A response lost after commit must replay the same receipt, including after expiry (Task 1 replay test).
3. Restoration and legacy routes must not silently restart the clock or bypass the runtime (Task 2 restore/legacy tests).
4. An AI response racing with finish must not overwrite the preserved answer or publish obsolete feedback (Task 2 cancellation test).
5. Offline/reloaded UI must retain drafts, display honest remaining time and recover without duplicate commands (Task 3 controller tests and Task 4 real-browser run).

## Task 1: Persistent task engine

**Files:** new `filemate/interview_runtime.py`, `filemate/execution/interview_runtime_schema.py`, `filemate/tests/test_interview_runtime.py`; modify `storage.py`, `interview_config.py`, coach repository.
**Interfaces:** produces `RuntimeRepository.prepare(DraftContent, request_key) -> CoachSnapshot`, `snapshot(sid) -> CoachSnapshot`, `command(sid, RuntimeCommand) -> CoachMutationResult`; runtime fields embedded in `snapshot.session.runtime`. Private coach answer transaction helper is called only after runtime validation.

- [ ] RED: tests assert fixed-seed task stability, explicit start, original deadline, revision/task/attempt conflicts, replay after expiry, bounded comments, no legacy write bypass, skip and early finish.
- [ ] Run `uv run --no-sync pytest filemate/tests/test_interview_runtime.py -q`; expected missing implementation failure.
- [ ] Implement migration 29; timed config is explicit, separate pools and stable indices. Tasks follow opening → topic → challenge → review. Commands are start/resume/submit/advance/event/skip/finish. Public legacy coach methods reject runtime transitions.
- [ ] Same command expected PASS; run existing coach/config tests as regression; commit selected files.

## Task 2: API, AI bounds and lifecycle

**Files:** `server.py`, `filemate/interview_coach/repository.py`, backup/restore modules, interview review repository/reports; new runtime API/backup tests; README/API/env docs and migration contract tests.
**Interfaces:** consumes Task 1 repository; produces GET `/interviews/{id}/runtime`, POST `/interviews/runtime` (content + request_key), POST `/interviews/{id}/runtime/commands`; all tenant scoped. `FILEMATE_ENABLE_INTERVIEW_RUNTIME` controls new writes, not history/export/delete.

- [ ] RED: assert flags, auth isolation, malformed requests, guarded legacy calls, backup restore with original deadline + interrupted status, deletion cascade/counts, report evidence, AI reservation/cancellation.
- [ ] Run targeted new tests; expected failures at absent endpoints/integration.
- [ ] Implement safe routes; restore normalization; report task/event evidence without volatile countdown fields. Reserve 2 transport calls per analysis (existing evaluator max 2), never more than 12 per session; replay does not reserve again. Finish revokes in-flight analysis authorization.
- [ ] Run targeted runtime/coach/config/backup/report/deploy contract tests; expected PASS; commit selected files.

## Task 3: Recoverable practice UI

**Files:** API/types/configuration helper, `InterviewCreator.vue`, `Interview.vue`, `InterviewCoachPanel.vue`, new runtime panel/clock helper and frontend tests.
**Interfaces:** consumes Task 2 snapshots/commands; command adapter reuses existing coach pending retry and immutable answer UI. Server offset drives local countdown; periodic state refresh ends the session authoritatively.

- [ ] RED: tests assert draft defaults, dispatch routing, clock zero clamp, stale/offline behavior and command mapping.
- [ ] Run frontend tests; expected absent helper failures.
- [ ] Add explicit fixed/timed choice, knowledge/commerce cards, start/resume/end controls, current step, large clock, simulated comment and skippable challenge. Disable expired submission and unsafe history navigation during active timing. Keep user text on failure.
- [ ] Run frontend test suite, type check and build; expected PASS; commit selected files.

## Task 4: Acceptance and delivery

**Files:** stage delivery report and development log; scratch evidence under `_working/` only.
**Interfaces:** consumes whole feature, produces evidence for Stage 3 acceptance.

- [ ] Execute synthetic real-browser 10-minute wall-clock session including reload/offline recovery, events, saved answers, expiry/report; separately exercise early finish, commerce facts and feature-off history.
- [ ] Run `scripts/verify.ps1`; expected exit 0, explicitly report platform/hardware skips.
- [ ] One fresh-context final reviewer on full branch; grade findings, one RED→GREEN fix pass for important findings; no re-review.
- [ ] Check preserved-file hashes, document A–E delivery and limitations, commit selected files and retain local branch for acceptance.
