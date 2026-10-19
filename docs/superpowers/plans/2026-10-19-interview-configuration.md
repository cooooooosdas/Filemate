# Interview 2.0 Stage 2 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution and one independent final review.

**Goal:** Deliver unified creation, durable configuration drafts, immutable session configuration and honest permission/capability status.
**Architecture:** A validated configuration module maps canonical choices to the existing fixed-question runner. Workspace-routed SQLite stores a revisioned draft and session snapshots. A dedicated Vue creator uses typed API calls. Existing answer versions, reports and device controls remain the execution path.
**Tech Stack:** Vue 3 / TypeScript / FastAPI / Pydantic / SQLite / pytest / Node tests / Playwright.
**Spec:** docs/superpowers/specs/2026-10-19-interview-2-design.md

## Global Constraints

- User accepted Stage 2 on 2026-10-19: quick preset 10 minutes / standard / Chinese; devices off, AI separate; future runtime continuous and may end early. Execute continuously within this stage.
- No Stage 3 engine, new scoring, emotion inference, deployment or dependency upgrade.
- Target duration is stored, never shown as active timing. Fixed questions remain real execution. Unsupported strategies / creator tracks are draft-only and blocked server-side.
- English currently maps only to existing English general interview. Challenge maps only to existing pressure mode. Reject unsupported combinations rather than silently changing the chosen track.
- Save source and project facts only on explicit draft save; no stored media permission, external consent, reusable-answer consent or memory selection. Draft restore requires a click and never requests a device.
- Append migration 28; preserve historical sessions and the 24 preexisting modified tests. Existing backup dynamically includes new tables; test old missing-table backups and consent revocation.
- Reuse existing isolated worktree and new codex/interview-v2-configuration branch. Fetch reset by network; no merge or push.

## Review Focus

Check workspace isolation, atomic snapshot creation, schema upgrade, draft lost-update prevention, restore after schema upgrades, malformed JSON recovery, no consent resurrection, legacy unknown scenarios, unsupported cross-products and no false timed-mode promise. Inspect source/goal route precedence, disposal races and narrow-screen controls.

## Task 1: Canonical contracts and persistence

Files: new filemate/interview_config.py, new filemate/tests/test_interview_configuration.py; modify filemate/execution/storage.py.

Interfaces: InterviewConfiguration; InterviewDraft; ConfigurationRepository.read_draft/save_draft; legacy_projection; session_configuration. Session snapshot is immutable and FK cascades. Draft singleton belongs to the routed workspace DB. Save requires expected_revision and request_key; same last command replays, stale edits conflict.

- [ ] RED: Test mapping, unsupported combinations, draft conflict/replay/reopen, migration preservation, corrupted snapshot fallback and cascade.
- [ ] Run `uv run --no-sync pytest filemate/tests/test_interview_configuration.py -q`. Expected: missing module/behavior fails.
- [ ] GREEN: Implement bounded strict models, schema 28, repository and storage projection / optional config snapshot parameter. Old records project with unknown duration and retain original scenario.
- [ ] Run same command. Expected: all pass. Commit explicit task files.

## Task 2: API, backup and feature shutdown

Files: server.py, new filemate/tests/test_interview_configuration_api.py; relevant backup source only if tests require changes.

Interfaces: GET /interview/configuration; PUT /interview/configuration/draft; optional configuration in POST /interviews. Old payloads still work. FILEMATE_ENABLE_INTERVIEW_CONFIG=0 disables new writes, retains reads and old start.

- [ ] RED: real TestClient tests for accepted canonical launch, mismatch rejection before writes, draft revision, tenant isolation, feature shutdown, personal export/restore including old missing-table backup and permission reset.
- [ ] Run both new test files. Expected: API endpoints/contracts fail.
- [ ] GREEN: validate before source/provider work; snapshot written in session transaction; explicit draft API with 409 conflicts; dynamic backup compatibility.
- [ ] Run both files plus existing interview coach/privacy/practice suites. Expected: all pass. Commit task files.

## Task 3: Unified creator and explicit recovery

Files: new web types/interviewConfiguration.ts, interview/configuration.ts, components/InterviewCreator.vue; services/api.ts; views/Interview.vue; new web/tests/interview-configuration.test.mjs.

Interfaces: typed API draft state; four categories plus learning expression; quick vs advanced controls; canonical-to-legacy mapper; draft save/restore events. Parent keeps source/project/history consent controls, passes configuration to start API. No automatic draft overwrite on load. Route-linked training has priority.

- [ ] RED: execute TypeScript utility with Node tests covering track/language/challenge validation and safe restore values. Expected: missing module fails.
- [ ] GREEN: extract creation controls, explicit save and restore, conflict reload with preserved local input, permission summary and truthful pending features. Keep accessible large controls and theme tokens.
- [ ] Run `npm.cmd test` then `npm.cmd run build`. Expected: all tests and type/build pass. Commit task files.

## Task 4: Integration, documentation and review

Files: README.md, filemate/docs/API_SPEC.md, design spec and Stage 2 delivery note; scripts/verify.ps1 only to include new module lint.

- [ ] Run default scripts/verify.ps1 and record full output. Expected: backend/frontend checks pass; any unrelated failures explicitly reported.
- [ ] Use isolated synthetic workspace via browser: save draft, reload and restore, create fixed session, reload session and read config; invalid configuration does not create a session. Desktop 1920, laptop 1366 and mobile 390 screenshots. No real AI/media claim.
- [ ] Confirm 24 preserved test file hashes; synchronize API/env/schema documentation and accepted Stage 3 timing decision.
- [ ] Commit docs. Prepare whole-branch review package and dispatch one independent reviewer per executing-plans skill. Fix important findings RED→GREEN then affected suites; ledger minor findings.
- [ ] Final report A–E: actual changes/evidence, unimplemented Stage 3 capability, boundaries and next stage questions. Keep branch for user review; no deploy.
