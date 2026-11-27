---
id: 2026-11-28-j2-08-read-path-evidence
type: ai-session
title: J2-08 read-path integration, FR-4 oracle and denied-source fix
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/evidence/read-and-privacy/README.md
  - tests/system/test_sparse_and_denied_sources.py
requirements:
  - FR-4
  - FR-6
  - NFR-05
  - NFR-06
  - NFR-08
---

## Goal and outcome

J2-08 moved to Aadyant under [[20-solo-completion-ownership-transfer]].
The session added stdio system tests for the read path:
- exact FR-4 totals, hand-calculated from the library catalogue
- UTC boundary cases
- denied and unrequested sources
- typed read failures with their attempt counts
- retention expiry and disconnect deletion

It also added NFR-08 cached-read benchmark targets.

## What worked

The fault injector runs in a server-side launcher, so faults are scripted
per endpoint over real stdio without changing shipped code. The SQLite
`quota_attempts` table then shows every accounted call.

## What failed

Probing showed a defect. `compare_periods` reported denied or unrequested
sources as zero events, with a note saying none fell inside the periods.
It now compares only retrieved sources, and the analysis warns about
not-requested sources too. The new system test fails on the old code and
passes on the fix.

## Verification

- **System tests.** Four new stdio tests pass.
- **Unit tests.** The analytics unit tests pass, including the new
  regression test.
- **Earlier tests.** The existing analysis and library tests pass.
- **Benchmark.** The performance test includes the two cached-read targets
  and asserts zero provider attempts during sampling.
- **Live.** No live read was run.
