---
id: 2026-11-26-a2-04-playlist-planning
type: ai-session
title: A2-04 strict playlist planner and versioned proposals
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - docs/requirements/SRS.md
  - docs/implementation/MASTER_PLAN.md
  - docs/implementation/CONTRACTS.md
  - docs/adr/0003-native-human-approval.md
  - https://github.com/AadyantNeog/SEproject/issues/12
  - https://github.com/AadyantNeog/SEproject/pull/13
requirements:
  - FR-5.1
  - FR-5.2
  - FR-5.3
  - FR-5.4
  - GOV-02
---

## Goal and outcome

Implement the A2-04 fixture planner using the merged contracts and A2-02 TF-IDF helpers. Added structured request clarification, account and expiry guards, strict topic and audio evidence, exact-second greedy selection, and immutable versioned proposals. Documented the creation digest in ADR-0003. The work is tracked in [issue #12](https://github.com/AadyantNeog/SEproject/issues/12) and [draft PR #13](https://github.com/AadyantNeog/SEproject/pull/13).

## What worked and what changed during verification

The SRS duration example produced 6,420 seconds selected and 780 unused while excluding a 1,201-second candidate. The first weak-topic fixture still scored above the threshold, so its synthetic unrelated evidence was strengthened to exercise rejection below 0.10. The planning validator expects the eight baseline ADRs. The creation digest is recorded as a refinement in the existing approval ADR.

## Verification and remaining integration

- Passed 56 offline tests, including 14 planner cases with generated packing inputs. Ruff lint and formatting, strict mypy on 29 source files, the locked wheel build and 34 planning checks passed.
- The [planner handoff](../../../docs/developer/playlist-planning.md) describes language comparison and versioned digest inputs. The language normalizer was a synthetic adapter in these checks.
- J2-01 validation, J2-03 account lookup, P2-01 proposal persistence and atomic invalidation, P2-02 quota, MCP routing and the native approval proof remain open. Human owner review is pending.

Related notes: [[04-duration-and-language-constraints]], [[06-preview-and-human-approval]], [[2026-11-26-a2-02-ranking]].
