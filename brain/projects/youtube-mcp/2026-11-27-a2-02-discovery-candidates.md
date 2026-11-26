---
id: 2026-11-27-a2-02-discovery-candidates
type: ai-session
title: A2-02 discovery candidate handoff to playlist planning
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - docs/developer/metadata-ranking.md
  - docs/developer/playlist-planning.md
  - tests/system/test_discovery_stdio.py
  - https://github.com/AadyantNeog/SEproject/issues/10
  - https://github.com/AadyantNeog/SEproject/issues/12
  - https://github.com/AadyantNeog/SEproject/pull/31
requirements:
  - FR-1.1
  - FR-1.3
  - FR-5.2
  - FR-5.3
---

## Goal and outcome

Pass the usable, bounded video discovery pool to the fixture playlist planner by opaque reference. The existing account-scoped SQLite cache stores the candidate set with the default 24-hour expiry. The ranked response keeps its result array and adds a candidate reference. The planner resolves that explicit reference under its fixture account, uses the exact evidence and rejects unavailable records. Without a reference it still uses the bundled set.

## What worked and what failed

The plannable pool remains independent of the display limit. The first typed handler attempt forwarded the reference as generic keyword metadata and failed mypy. A video-specific result envelope now carries the additional field. The integration tests exercised a capped discovery with more usable candidates than the requested display limit and checked the shared cache after a server restart.

## Verification

On Windows with Python 3.13.1, all 248 offline tests, scoped Ruff lint and formatting, and mypy on 53 source files passed. The stdio handoff used a fresh fixture database and verified that an unknown, foreign or expired reference is refused. The Codex Desktop `0.171.0-alpha.13.2` app-server probe passed the generated reference to `propose_playlist` and returned **B-Tree Database Indexing Deep Dive** with 1,200 seconds selected and 600 seconds unused. The probe used synthetic data and ran without a model turn.

P2-02 shared workflow reservations, atomic proposal revision, live acceptance and human owner review remain pending.

Related notes: [[2026-11-27-a2-02-discovery-stdio]], [[2026-11-27-a2-04-playlist-preview-stdio]], [[02-metadata-based-similarity]] and [[04-duration-and-language-constraints]].
