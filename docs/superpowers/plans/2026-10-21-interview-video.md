# Interview 2.0 Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Approved Stage5: explicit camera/microphone selection, bounded reliable local video, immediate per-question replay and whole-session collection, optional observable motion only.
**Architecture:** Testable browser adapters own device resources; a page-local collection binds immutable video takes to coach receipts. Existing visual metrics/API/storage remain unchanged. A default-off flag replaces the coach camera UI while retaining the old interface when disabled.
**Tech Stack:** Vue3, TypeScript, MediaDevices/MediaRecorder, existing MediaPipe Worker and SQLite29.
**Spec:** `docs/superpowers/specs/2026-10-19-interview-2-design.md` Stage5, accepted by user2026-10-21; per-question replay plus session summary explicitly selected.

## Global Constraints

- Preserve four themes, sans-serif, SVG, body17px/minimum15px,44px controls. No new framework/assets/dependencies, deployment, emotion/identity inference or scoring changes.
- Camera preview is video-only; recording audio is separately opt-in, with a microphone selector. A rejected requested microphone does not silently claim sound: offer explicit silent retry. Never open devices on restore or selection alone.
- Local blobs remain page-only; explicit export/download/delete confirmation; refresh/leave clears media. No media upload, table or migration. New UI default off via `VITE_ENABLE_INTERVIEW_VIDEO`, requires coach.
- Engineering limits:640×480 ideal,15fps ideal/24max,1Mbps video/64kbps audio;30min/100MiB per take,200MiB/20takes per page, no eviction. Permission15sec and final-stop5sec timeouts; preserve already received chunks on failures, mark partial. Stop late granted streams and ignore late callbacks.
- Context=session/question/attempt/runtime token+draft epoch. Only matching save receipt attaches a take; unknown response retries keep the frozen visual evidence and original command. Switching questions retains detached clips for export; changing sessions clears them.
- Hidden page stops recording with a visible interruption marker and closes camera; return never auto-opens. Device loss stops capture, preserves partial chunks. Actual hardware/vendor behavior must be distinguished from synthetic browser tests.
- Optional existing vision remains local2Hz/30min; initialization30sec, add finite in-flight response timeout and visibility cleanup. No face/low light means no invented reading. Existing summaries remain device observations, unscored.
- Preserve the24 unrelated modified tests and prior Stage4 work.

## Review Focus

1. Permission resolves after timeout/session change: stop all tracks and never revive preview (Task1).
2. Recorder error/track-ended/final chunk/stop timeout: settle once, preserve earlier chunks, release clones and microphone, keep preview ownership separate (Task1).
3. Lost receipt followed by deleting/re-recording/switching draft: never mutate retry evidence or bind video to the wrong attempt (Task2).
4. Device labels missing/removed device/permission failure: no silent camera substitution or unexpected microphone activation (Tasks1–2).
5. Hidden page or stalled visual worker: stop resource use and retain text/recordings; resuming is explicit (Tasks2–3).

## Task1: Device and recording adapters

**Files:** create `web/src/interview/video-devices.ts`, `video-capture.ts`, `types/interviewVideo.ts`, `web/tests/interview-video.test.mjs`.
**Interfaces:** `CameraPreview.open(deviceId='')/close()/refresh()/dispose()`, state `{phase,stream,devices,error}`; selection uses exact deviceId, no persisted labels/IDs. `VideoCapture.start(binding,preview, microphoneId:string|null, maxBytes?)/stop()/dispose()` publishes `LocalVideoTake` containing blob, original binding, duration, hasAudio, partial and issue. Null microphone means video-only, empty string means explicit default microphone.

- [x] RED tests: absent adapter; camera-only constraints, exact selection, late permission/timeout/rejection, ended preview, cancelled acquisition, final chunk, disconnected tracks/error/stop timeout/byte cap, preview survives clone cleanup, no silent audio fallback.
- [x] Implement injected browser dependencies, monotonic duration, bounded timers/memory and generation cancellation; preferVP8 overVP9 and fall back toMP4/default supported recorder.
- [x] Run `node --test tests/interview-video.test.mjs` and frontend suite; expected PASS, commit selected files.

## Task2: Receipt-bound replay and UI

**Files:** create `video-collection.ts`, `useInterviewVideo.ts`, `InterviewVideoPanel.vue`, `InterviewVideoLibrary.vue`; modify `Interview.vue`, environment/docs and new collection tests.
**Interfaces:** `VideoCollection.context(binding)/add(take)/freeze(text,visualMetrics)/receipt(snapshot,attemptId,sessionId)/remove(id)/clear()`. Frozen values survive local deletion. Composable owns preview/capture/URLs, selection, explicit audio opt-in, pending-save guards, exports via `saveDownload`. Panel emits preview element for existing optional vision; library supports filters/current/history/summary.

- [x] RED tests: matching and mismatched receipts, context/session transitions, quota/no eviction, delete while pending, reanswer/history, URL cleanup and immutable visual retry snapshot.
- [x] Integrate default-off coach UI, selectors within details, prominent preview/record/stop; immediate draft playback and whole-session/history library. No silent replacement; repeated recordings remain distinct. Lock new media while save receipt uncertain. TTS/audio capture cannot overlap; camera-only preview may coexist.
- [x] Update README/API/env/verify flag support. Run Node suite, vue-tsc and build; expected PASS, commit.

## Task3: Vision lifecycle and fault acceptance

**Files:** existing `useInterviewVision.ts`, testable `vision-lifecycle.ts` if needed, lifecycle tests; stage delivery A–E and scratch evidence.
**Interfaces:** watchdog permits one in-flight frame, drops/stops stale work on timeout/context switch; visibility ends current observation and requires explicit user restart. Existing VisualMetrics fields unchanged.

- [x] RED tests: worker never responds, late responses across epochs, hidden-page interruption and resume not automatic. Implement finite watchdog/cleanup; preserve valid observations and truthful missing states.
- [x] Use actual browser canvas-generated video+audio through MediaRecorder/playback/download; separately test synthetic denial/late grant/disconnect/stop failures/save recovery/default-off and390/768/1440 layouts. Attempt real authorized device verification only if available; record limitations honestly.
- [x] Run `scripts/verify.ps1 -IsolateFrontend`, expect exit0. One fresh final whole-branch reviewer; one Important/Critical TDD fix pass and full suite; defer minors, no re-review.
- [x] Verify preserved24 hashes, commit delivery and complete ledger. Keep local branch/worktree and evidence, no deployment; ask next-stage choices after completion.

Self-review: Stage5 scope covered by the three tasks, shared binding and take signatures pinned; no API/schema change. Constants above are engineering choices inside accepted media/privacy scope. No new product approval requested for the already-approved stage or preserved inline method.
