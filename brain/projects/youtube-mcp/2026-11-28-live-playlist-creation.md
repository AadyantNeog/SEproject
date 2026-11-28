---
id: 2026-11-28-live-playlist-creation
type: ai-session
title: Live approved playlist creation
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/adr/0013-live-approved-playlist-creation.md
  - src/yt_intel/mcp/live_creation.py
  - tests/system/test_live_server.py
requirements:
  - FR-5
  - NFR-03
  - NFR-04
  - NFR-05
---

## Goal and outcome

The goal was to build the last live feature gap: one supervised live
playlist write for Stage 4. Live mode now runs the full video-to-playlist
workflow:
- **Quota.** `begin_workflow` reserves the whole budget first.
- **Stages.** The seed fetch, discovery and proposal all spend that
  reservation.
- **Creation.** `prepare_creation` and `create_playlist` use the shared
  guarded creation service, with the native dialog and the real write
  adapter.
- **Preconditions.** Writes need D-02 resolved and the write scope. Without
  the scope, the workflow refuses with zero calls.
- **Not exposed.** Live recovery.

See [[06-preview-and-human-approval]] and [[09-quota-buckets-and-budgeting]].

## What worked

- **Reused services.** `WorkflowService` and `PlaylistCreationService` were
  already provider-agnostic apart from one fixture-only check. That check
  now takes the same injected D-02 check as the other services.
- **Offline tests.** The existing fixture playlist simulator stands in for
  Google's write endpoints, so the approve, reject, replay and scope cases
  run offline.

## What failed

The first run of the suite had one failure: an older test asserting that
`create_playlist` was absent from live mode. It now asserts that the
recovery tools stay absent instead.

## Verification

- **Tests.** 371 offline tests passed, including three new write tests.
- **Lint and types.** CI-scoped Ruff and mypy passed.
- **Live.** No live write was sent. The supervised live run is Aadyant's to
  perform.
