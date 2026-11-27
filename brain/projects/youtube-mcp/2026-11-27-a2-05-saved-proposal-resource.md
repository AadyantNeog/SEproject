---
id: 2026-11-27-a2-05-saved-proposal-resource
type: ai-session
title: A2-05 exact saved proposal resources
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - docs/implementation/CONTRACTS.md
  - docs/developer/codex-fixture.md
  - tests/system/test_playlist_planning_stdio.py
  - https://github.com/AadyantNeog/SEproject/issues/8
  - https://github.com/AadyantNeog/SEproject/pull/31
requirements:
  - FR-5.4
  - NFR-01
  - NFR-03
---

## Goal and outcome

Publish a versioned MCP resource for an exact stored fixture creation proposal. The planning tool advertises its URI alongside the preview. The resource resolves the requested version against the active synthetic account, latest SQLite record, expiry, state and proposal digest. It reuses the complete preview renderer.

## What worked and what failed

The first resource-link attempt passed a Pydantic URL object. This SDK version expects a plain URI string, which restored tool invocation and type checking. The stdio tests matched the returned and reopened preview text and exercised unknown IDs, previous versions, foreign accounts, expiry, rejected states and mismatched digests. An unknown preview on an empty store left the fixture database uncreated.

## Verification

On Windows with Python 3.13.1, all 249 offline tests, scoped Ruff lint and formatting, and mypy on 53 source files passed. The Codex Desktop `0.171.0-alpha.13.2` app-server probe created a local synthetic preview and reopened it through the returned resource link. The text matched exactly. The probe used isolated fixture storage and ran without a model turn.

Shared quota, atomic revision and approval invalidation, and human owner review remain pending. The resource reads the preview and does not launch an approval dialog.

Related notes: [[2026-11-26-a2-05-codex-demo-client]], [[2026-11-27-a2-04-playlist-preview-stdio]], [[06-preview-and-human-approval]] and [[11-mcp-and-agent-skill-contracts]].
