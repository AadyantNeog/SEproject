---
id: 2026-11-28-j2-07-live-read-setup
type: ai-session
title: J2-07 consent runbook and fixed-budget live read-only check
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/user/setup-and-consent.md
  - docs/evidence/policy-and-consent/README.md
  - .github/workflows/live-read-only.yml
requirements:
  - FR-6
  - NFR-02
  - NFR-04
  - NFR-05
  - NFR-07
---

## Goal and outcome

J2-07 moved to Aadyant under [[20-solo-completion-ownership-transfer]].

- **Runbook.** The session added a clean-checkout setup, consent,
  AI-client disclosure, disconnect, recovery and retention runbook.
- **Disconnect.** It added a `yt-intel disconnect` command. Before this, the
  live CLI could sign in but had no way to disconnect.
- **Live check.** It added a fixed-budget read-only check: 10 general
  units a day, a 6-unit worst-case reservation, and at most 2 reads per
  run. A weekly workflow runs a readiness job on a GitHub-hosted runner and
  a live job only on a protected self-hosted runner.
- **Readiness record.** It recorded D-02, account, vault, runner and budget
  readiness honestly. D-02 is unresolved, and the runner and account are
  not recorded.

## What worked

- **Ordered gates.** Every gate runs before the vault, the network or the
  ledger is touched, so a blocked run creates no database.
- **Budget.** The ledger's per-project limits give the check its own budget
  without changing interactive accounting.

## What failed

- **Type check.** The first mypy run rejected a plain `str` tuple as a
  quota endpoint key. The fix types it as `Endpoint`.

## Verification

- **Tests.** Six offline tests in `test_live_read_check.py` cover the gates,
  three successful runs, a fourth refusal at the budget, a channel mismatch,
  disconnect, and a failed revocation. The existing OAuth lifecycle tests
  still pass.
- **Vault.** `WinVaultKeyring` was detected on the development workstation.
  Nothing was stored.
- **Live.** No live request was sent.
