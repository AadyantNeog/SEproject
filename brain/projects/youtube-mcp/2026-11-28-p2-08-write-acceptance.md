---
id: 2026-11-28-p2-08-write-acceptance
type: ai-session
title: P2-08 write, authority and quota acceptance over stdio
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/evidence/write-and-quota/README.md
  - tests/system/test_playlist_authority.py
  - tests/system/test_playlist_creation.py
requirements:
  - FR-5
  - NFR-03
  - NFR-06
---

## Goal and outcome

P2-08 moved to Aadyant under [[20-solo-completion-ownership-transfer]].

- **Launcher.** The session added a shared stdio launcher with isolated
  seams: a scripted approval adapter, extra candidates, injected metadata,
  a write fault and a POST audit.
- **Authority tests.** Six tests cover forged account, digest and operation
  decisions, model-controlled arguments, a borrowed or made-up operation,
  tampered and expired storage, and prompt injection. Every case made zero
  writes.
- **Creation tests.** Two tests cover an ambiguous timeout that is never
  retried and is reconciled to `completed`, and the per-write attempt
  ceilings inside the composed reservation.

## What failed

Moving `expires_at` in storage produced `PROPOSAL_CHANGED`, not
`APPROVAL_EXPIRED`, because the digest covers the expiry. The test asserts
the observed code and points to the controlled-clock expiry test. No
product defect was found in the write path.

## Verification

The eight new stdio tests pass. The native dialog and live writes were not
exercised.
