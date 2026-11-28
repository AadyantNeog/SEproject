---
id: 2026-11-28-live-serve-mode
type: ai-session
title: Live serve mode, step one
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/adr/0011-staged-live-serve-mode.md
  - src/yt_intel/mcp/live.py
  - tests/system/test_live_server.py
requirements:
  - NFR-01
  - NFR-02
  - NFR-05
---

## Goal and outcome

The goal was to make a live MCP server exist for Stage 4. The session added
`serve --provider live`, which composes:
- the saved OAuth account and its vault
- a bearer-authenticated accounted executor
- the SQLite ledger
- the official read provider

The non-derived tools work live. The derived FR-1 to FR-5 tools refuse with
`POLICY_BLOCKED` until D-02 is resolved. The D-02 check moved into a shared
`policy.py`. See [[13-api-policy-dependency]] and
[[20-solo-completion-ownership-transfer]].

## What worked

The fixture dataset's request handler can stand in for Google, so the
offline stdio tests run the real live stack end to end: account record,
vault, bearer header, ledger and provider.

## What failed

- **Fixture-bound handlers.** The handlers hard-code fixture bindings, with
  two different fixture channels, and fixture-only planning and
  candidate storage. A full live FR-1 to FR-5 path therefore needs a
  runtime-injection refactor. ADR-0011 records it as the next step.
- **Test channel ID.** The first test channel ID was one character too long
  for the channel pattern.

## Verification

- **Tests.** 358 offline tests passed, including six new live-mode tests.
- **Lint and types.** Ruff passed, and mypy passed for Windows and Linux.
- **Live.** No live request was sent.
