---
id: 2026-11-28-d02-team-lead-resolution
type: ai-session
title: D-02 recorded as a team-lead decision
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/adr/0012-d02-team-lead-resolution.md
  - docs/evidence/policy-and-consent/d02-status.json
  - tests/integration/test_live_read_check.py
requirements:
  - FR-1
  - FR-2
  - FR-3
  - FR-4
  - FR-5
  - NFR-05
---

## Goal and outcome

In chat, Aadyant directed that D-02 be resolved without asking the
instructor. The session recorded it truthfully:
- **The record.** ADR-0012 and `d02-status.json` show the state as
  resolved, with `basis: "team-lead-decision"`. The record says plainly
  that this is not instructor or provider evidence.
- **The deviation.** The ADR and the release record note that this departs
  from SRS §13.2 and RN-13.
- **Scope.** The resolution covers locally computed derived processing for
  the team's own authorised accounts. It does not cover live writes.

`AGENTS.md` was updated to match. See [[13-api-policy-dependency]] and
[[2026-11-28-live-derived-handlers]].

## What worked

The gate already accepted any complete, human-recorded https record. So the
decision needed no code change, only an honest record, and it can be
revoked by reverting one file.

## What failed

The repository test that asserted D-02 was unresolved, and a gate test
that used the repository record, had to move to explicit temporary
records.

## Verification

- **Checks.** The offline tests, CI-scoped lint and mypy, and both
  validators were run before the PR. The results are in the PR.
- **Live.** No live request was sent.
