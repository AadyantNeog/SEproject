---
id: 2026-11-27-j2-03-auth-follow-up
type: ai-session
title: J2-03 durable disconnect and configured sign-in quota
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - https://github.com/AadyantNeog/SEproject/issues/28
  - https://github.com/AadyantNeog/SEproject/pull/29
  - https://github.com/AadyantNeog/SEproject/pull/27
  - tests/security/test_account_isolation.py
  - tests/integration/test_oauth_lifecycle.py
requirements:
  - FR-6
  - FR-7
  - NFR-05
  - NFR-12
---

## Goal and outcome

At Aadyant's request, Codex followed up on Jeswin's `1d5f18f` sign-in implementation. Disconnect writes a pending flag to the non-secret saved account record before cleanup. On restart the service keeps that record disabled and can retry cleanup using the saved binding. The sign-in channel lookup calculates its full reservation with the configured quota profile.

## What worked and what failed

Before the fix, failed revocation and keyring deletion left a saved account that became active after restart. The regression test now verifies the account stays disabled and removes the saved record when cleanup succeeds on retry. It starts with a record written before the pending flag existed. The configured-cost regression verifies all lookup attempts are priced from the supplied profile before a provider call.

## Verification

On Windows with Python 3.13.1, all 17 focused tests and 275 offline tests passed. Scoped Ruff lint and formatting and mypy on 57 source files passed. In a separate synthetic integration check with Paul's P2-02 ledger from `4698669`, a non-default channel cost reserved six units, charged two for one lookup, and released the remainder. A profile with only five units of budget rejected the lookup before the mock provider received a call.

Default sign-in depends on P2-02 landing on `main`. Live consent and human review are pending. Related notes: [[2026-11-26-j2-03-oauth-account]], [[08-oauth-and-secret-handling]] and [[09-quota-buckets-and-budgeting]].
