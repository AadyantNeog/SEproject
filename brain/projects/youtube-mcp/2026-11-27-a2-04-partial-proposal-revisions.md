---
id: 2026-11-27-a2-04-partial-proposal-revisions
type: ai-session
title: A2-04 partial proposal revision planning
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - docs/adr/0003-native-human-approval.md
  - docs/developer/playlist-planning.md
  - tests/unit/test_playlist_planner.py
  - https://github.com/AadyantNeog/SEproject/issues/12
requirements:
  - FR-5.1
  - FR-5.2
  - FR-5.3
  - FR-5.4
---

## Goal and outcome

Prepare the A2-04 planner to revise the explicitly changed fields of a saved proposal. The same validation and packing rules apply to the amended request. The planner preserves the other fields, keeps the original candidate reference, and returns the superseded and replacement records for the later transaction.

## What worked and what remains

The saved seed-exclusion count distinguishes default exclusion from an explicitly requested seed that previously failed a constraint. The unit tests exercise both cases when the individual video cap changes. The replacement keeps its account and ID, advances its version and has a fresh digest and expiry. The test cases for empty changes, exact duration, invalid field types, a confirmation flag, infeasible limits and a different candidate set return typed errors.

The committed repository exposes individual proposal saves. The atomic revision and validation at write claim are pending shared integration with Paul. The A2-04 tool can use that path once the persistence and approval work is available.

## Verification

On Windows, 22 planner tests and all 257 offline tests passed. Scoped Ruff lint and formatting and mypy on 53 source files also passed. This is planner evidence. The end-to-end revision transaction and human owner review remain pending.

Related notes: [[2026-11-26-a2-04-playlist-planning]], [[2026-11-27-a2-04-playlist-preview-stdio]], [[04-duration-and-language-constraints]] and [[06-preview-and-human-approval]].
