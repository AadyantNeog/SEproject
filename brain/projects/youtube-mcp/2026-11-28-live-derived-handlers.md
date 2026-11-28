---
id: 2026-11-28-live-derived-handlers
type: ai-session
title: Live derived handlers, ADR-0011 step two
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/adr/0011-staged-live-serve-mode.md
  - src/yt_intel/domain/derived.py
  - src/yt_intel/mcp/live_derived.py
  - tests/system/test_live_server.py
  - tests/unit/test_derived_policy_check.py
requirements:
  - FR-1
  - FR-2
  - FR-3
  - FR-4
  - FR-5
  - NFR-05
---

## Goal and outcome

Aadyant asked to proceed with D-02 if YouTube itself does not block it.
YouTube does not block the API calls. D-02 is the team's own SRS gate, and
only a human-recorded instructor or provider direction can resolve it. So
the session did **not** change `d02-status.json`. It built everything up to
that record instead:
- **Shared check.** One injectable `DerivedProcessingCheck` replaces the
  hard-coded fixture-only checks in discovery, recommendations, analysis,
  planning and candidate storage. Its default stays fixture-only.
- **Live handlers.** The live composition passes `recorded_policy_check`,
  which re-reads the reviewed record on every call. The live server now
  runs FR-1 to FR-4 and a preview-only FR-5 proposal when the record is
  resolved.
- **Still closed.** Live workflows and live creation stay unavailable.

See [[13-api-policy-dependency]] and [[2026-11-28-live-serve-mode]].

## What worked

- **Reused services.** The services already took any read provider, so the
  live handlers reuse the same ranking, planning and analysis code as the
  fixture server.
- **Offline tests.** The existing live test harness serves Google from
  fixture data, so the resolved path runs end to end offline. It covers
  bearer auth, ledger rows under `default-project`, released reservations
  and GET-only traffic.

## What failed

- **Shell quoting.** A large inline shell edit script hit the known
  heredoc quoting problem and was redone with file edits.
- **Default lint scope.** The first lint run covered the whole repository
  and flagged old SRS build scripts. The CI-scoped command was used
  instead.

## Verification

- **Tests.** 368 offline tests passed, including 10 new ones. One of these
  checks that reverting the record closes the gate mid-session with no new
  provider calls.
- **Lint and types.** CI-scoped Ruff and mypy passed.
- **Live.** No live request was sent. D-02 is still unresolved.
