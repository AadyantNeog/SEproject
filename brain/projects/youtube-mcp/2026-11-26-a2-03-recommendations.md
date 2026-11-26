---
id: 2026-11-26-a2-03-recommendations
type: ai-session
title: A2-03 preference profiles and fixture recommendations
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - docs/requirements/SRS.md
  - docs/implementation/MASTER_PLAN.md
  - docs/implementation/CONTRACTS.md
  - https://github.com/AadyantNeog/SEproject/issues/14
  - https://github.com/AadyantNeog/SEproject/pull/15
requirements:
  - FR-3.1
  - FR-3.2
  - FR-3.3
  - GOV-02
---

## Goal and outcome

Implement the A2-03 fixture slice over the merged snapshot and candidate contracts. Added deduplicated preference evidence, a shared TF-IDF fit, source-weighted scores and reasons, bounded query terms, and strict optional filters. Reports preserve per-source coverage even when some sources are denied. Tracked in [issue #14](https://github.com/AadyantNeog/SEproject/issues/14) and [draft PR #15](https://github.com/AadyantNeog/SEproject/pull/15).

## What worked and verification

- Independent calculations verified all three family weights and the shared-space IDF. The duration fixture keeps the 600-second and 244-second matches under a 900-second budget while preserving the requested regional audio and topic constraints. A video shared across likes and playlists is fitted once and contributes to both source families.
- Passed 63 offline tests, including seven recommendation cases. Ruff lint and formatting passed for `src` and `tests`, strict mypy passed on 31 source files, and the locked wheel built. All 34 planning checks passed.
- The [recommendations handoff](../../../docs/developer/recommendations.md) describes the inputs, evidence, and tests. Observed evidence is limited to synthetic snapshots and candidate pools. J2-04 retrieval, J2-02 candidate discovery, P2-02 reservations and MCP routing remain open. Human owner review is pending.

Related notes: [[03-authorised-preference-signals]], [[02-metadata-based-similarity]], [[2026-11-26-a2-02-ranking]].
