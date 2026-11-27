---
id: 2026-11-27-a2-02-discovery-quota
type: ai-session
title: A2-02 SQLite quota preflight for standalone discovery
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - https://github.com/AadyantNeog/SEproject/issues/10
  - https://github.com/AadyantNeog/SEproject/issues/26
  - tests/system/test_discovery_stdio.py
requirements:
  - FR-1.1
  - FR-2.1
  - FR-7
---

## Goal and outcome

Codex connected standalone video and channel discovery to the project-scoped SQLite quota ledger. The handlers validate identifiers before reserving. The active quota profile prices the discovery endpoint ceilings for all buckets before the first call. The existing fixture provider debits the reservation, and the handler releases unused capacity on completion, failure or cancellation.

## What worked and what remains

The prior in-memory allowance bounded one synthetic call at a time and did not enforce the SQLite daily budget. The stdio checks now inspect the real search debits, refusal when the complete reservation will not fit, and release with no candidate cache entry after cancellation. Candidate references still work in playlist planning. Live-derived ranking remains gated by D-02. The seed, discovery and preview still need to share one composed-workflow reservation for issue #26.

## Verification

All 293 offline tests, CI-scoped Ruff lint and formatting, mypy on 62 source files, and all 34 planning checks passed locally. Aadyant's owner review is pending.

Related notes: [[2026-11-27-a2-02-discovery-stdio]], [[2026-11-27-a2-02-discovery-candidates]] and [[09-quota-buckets-and-budgeting]].
