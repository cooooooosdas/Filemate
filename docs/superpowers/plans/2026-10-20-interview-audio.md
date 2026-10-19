# Interview 2.0 Audio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approved Stage4: independent local audio recording, immediate per-answer replay/export, optional browser transcription, objective evidence and existing natural speech; whole-session replay list remains available.
**Architecture:** Browser-only media adapters own bounded resources and immutable draft/attempt bindings; existing JSON evidence columns persist validated summaries/transcription provenance with answers. No new media upload endpoint, model, database table or schema migration.
**Tech Stack:** Vue3, TypeScript, MediaRecorder/WebAudio/WebSpeech adapters, FastAPI/Pydantic/SQLite29.
**Spec:** `docs/superpowers/specs/2026-10-19-interview-2-design.md`, Stage4; user accepted Stage3 and chose per-question replay + summary on2026-10-20.

## Global Constraints

- Reuse the current blue themes/LOGO, sans-serif and SVG icons. No deployment, new scoring rubric, emotion inference or camera expansion.
- Local audio capture and optional browser transcription have separate user actions/permissions; browser ASR may send audio to its vendor. Natural speech keeps Xiaoxiao/Yunxia/Yunxi/Xiaoyi and explicit Microsoft-text consent. Capture/replay stops TTS; TTS cannot start during capture.
- Audio blobs are temporary page memory, not uploaded or persisted by FileMate, cleared on refresh/route/session deletion; exported downloads remain user managed. Audio is limited to10min/20MiB per take,60MiB per page; no silent eviction or replacement. At most30 retained takes. Re-record/remove asks first; no bundled archive overwrite.
- Client-captured objective statistics and ASR confidence are unverified device observations, not accuracy/emotion/ability scores. New evidence does not alter content score; existing legacy records retain original method labels.
- Transcript missing/unsupported/denied/interrupted/low-confidence, empty audio and failed analysis have separate states; preserve existing typed text and final transcript, discard interim hypotheses. Never fabricate confidence/word timestamps or call ASR callback gaps real pauses.
- Draft binding includes session/question/current attempt/runtime token. A changed context stops capture, preserves a detached take for export, blocks wrong-attempt submission; successful receipt alone attaches a take to that attempt. Response uncertainty reuses the original request.
- Feature default off via VITE_ENABLE_INTERVIEW_AUDIO; server validates new optional metrics and retains read/export/delete when UI flag off. No schema change; existing backups cover JSON evidence. Preserve the24 unrelated modified tests.

## Review Focus

1. Microphone permission resolves after navigation/dispose: stop returned tracks; cannot publish into the new session (Task1).
2. stop/error/track-ended/final-chunk/byte-cap races: settle once, bounded memory, release tracks and timers, never lose prior saved takes (Task1).
3. ASR final/interim/repeated callbacks/restarts: preserve typed prefix, no duplicate final words, unknown confidence staysnull, late callback cannot mutate another question (Task1).
4. Background task/token/attempt change or lost submit receipt: media cannot be rebound to another task/version and offline retries remain idempotent (Task3).
5. Audio failure/denied mic/ASR unavailable/offline/TTS error: text training and existing reports stay usable; no fallback fake score or robotic voice (Tasks2–4).

## Task1: Browser audio/transcription adapters

**Files:** create `filemate/web/src/types/interviewAudio.ts`, `interview/audio-capture.ts`, `interview/transcription.ts`, `interview/audio-evidence.ts`, new Node tests.
**Interfaces:** `AudioCapture.start(binding)`, `stop()`, `dispose()` publish a bounded `LocalAudioTake` withBlob, duration and local RMS/low-energy/clipping summaries. `Transcription.start(language,onText)` returns final-only text plus bounded segments and provider estimates; stop/revoke preserves finals. Browser dependencies injected for deterministic resource tests.

- [ ] RED tests for denied/late permission, stop-final-chunk, ended/error/caps, decoded known waveform vs silence/no samples, final/interim/dedup/prefix/confidence handling.
- [ ] Run new Node tests, expected absent-module/behavior failure.
- [ ] Implement adapters with10min/20MiB take limits, monotonic timing, cleanup and cancellation; bounded 8kHz decoded audio analysis, expose missing/failed states instead of zeros.
- [ ] Run frontend suite, expected PASS; commit selected files.

## Task2: Durable evidence and truthful reports

**Files:** coach models/validation, `understanding/interview.py`, runtime request validation, reports/types and API docs/tests.
**Interfaces:** existing `fluency_metrics` accepts new discriminated `source=browser_media_v1`: optional `audio` summary and `transcription` result with explicit status/provider/language/segments/confidence; at least one evidence object. Legacy source remains compatible. Reports expose separate `audio` and `transcription` fields per turn, page summary uses actual sampled turns only.

- [ ] RED tests for bounded finite metrics, missing evidence, no score alteration, persisted versions, report/export, existing backup/delete and runtime invalid request422.
- [ ] Run new backend tests, expected unknown-source/missing-report failure.
- [ ] Implement strict normalization and local-only evidence propagation; preserve metadata in subsequent AI analysis without treating it as competence. Markdown/PDF include method and missing states.
- [ ] Run targeted coach/runtime/review/backup/privacy tests, expected PASS; commit.

## Task3: Per-answer replay and session collection

**Files:** new `InterviewAudioPanel.vue`, `useInterviewAudio.ts`, integrate coach panel/Interview.vue and existing report UI; new controller tests.
**Interfaces:** composable owns capture/draft/attempt media and URL cleanup, exports via `saveDownload`. A frozen submission payload binds evidence to the pending request; only a matching receipt binds a take to an immutable attempt. Panel shows record, stop, local audio controls, independent transcription consent/action and objective evidence; answered/history/summary read existing retained takes, absent audio explicitly saysrefresh-cleared.

- [ ] RED controller tests for context changes, reanswer, lost response, repeated receipt, quota, removal/export, speech exclusion and cleanup.
- [ ] Implement guarded recording and immediate playback afterstop/save; per-session list/export controls, unsaved-take navigation warning and explicit remove/replace confirmation. Keep legacy behavior when flagoff.
- [ ] Run Node suite, vue-tsc and production build, expected PASS; commit.

## Task4: Fault acceptance and stage handoff

**Files:** stage report A–E, execution log, scratch scripts/evidence only in `_working/interview-audio-20261020`.

- [ ] Use generated real audio samples through actual browser MediaRecorder/WebAudio/playback/download; separate this from stubbed ASR tests and physical microphone checks. Inject permission/track/network/ASR/TTS failures and verify text survives. Responsive390/768/1440 and featureoff history.
- [ ] Run `scripts/verify.ps1 -IsolateFrontend`; expect exit0; list platform/hardware exclusions honestly.
- [ ] One fresh-context final whole-branch reviewer, one RED→GREEN Important fix pass; no re-review.
- [ ] Verify24 preserved hashes, document all rulings/known dependencies and next-stage questions; keep local branch, no deployment.

Self-review: Stage4 requirements map to all four tasks; no new persistence or provider credentials required. Binary audio stays temporary; summaries are versioned answer evidence. Review inputs have tests. Implementation details above are engineering calls inside the accepted stage, not a new product scope.
