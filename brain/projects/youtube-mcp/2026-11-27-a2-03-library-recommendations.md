---
id: 2026-11-27-a2-03-library-recommendations
type: ai-session
title: A2-03 recommendations from saved fixture library snapshots
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - https://github.com/AadyantNeog/SEproject/issues/14
  - https://github.com/AadyantNeog/SEproject/pull/41
  - tests/system/test_recommendation_stdio.py
requirements:
  - FR-3.1
  - FR-3.2
  - FR-3.3
  - FR-7
---

## Goal and outcome

After J2-04 merged, Codex connected the account-bound snapshot from `get_library` to `recommend_videos`. The server resolves it through the same account session and SQLite repository, derives a bounded query, reserves search and hydration against the active project quota, and reuses the discovery service to collect candidates. The bundled comparison example remains available when no snapshot ID is supplied.

## What worked and what remains

The bundled path previously refused every saved library ID. The stdio test now collects likes, passes the returned ID, and receives an English recommendation with 1,200 of the requested 1,300 seconds used. The test checks that two search units were spent, the unused allowance was released, and expired, foreign and disconnected snapshot requests did not start new searches. Live recommendations remain gated by D-02. The composed playlist reservation is separate work tracked in [issue #26](https://github.com/AadyantNeog/SEproject/issues/26).

## Verification

All 292 offline tests passed, including the recommendation, library and discovery checks. The CI Ruff scope, mypy, all 34 planning checks and the wheel build passed locally. Aadyant's owner review is pending.

Related notes: [[2026-11-26-a2-03-recommendation-stdio]], [[2026-11-27-j2-04-library-collection]], [[03-authorised-preference-signals]] and [[09-quota-buckets-and-budgeting]].
