---
id: 2026-11-27-a2-05-composed-preview
type: ai-session
title: A2-05 shared quota reservation for discovery and preview
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - https://github.com/AadyantNeog/SEproject/issues/8
  - https://github.com/AadyantNeog/SEproject/issues/26
  - https://github.com/AadyantNeog/SEproject/pull/47
  - tests/system/test_composed_workflow_budget.py
requirements:
  - FR-1.1
  - FR-5.4
  - FR-7
---

## Goal and outcome

Codex connected Aadyant's video discovery and playlist preview MCP handlers to the composed reservation. Discovery debits the original reservation and registers its candidate ID on the session. Preview rejects a candidate from outside that session. Workflow and standalone calls use the same SQLite quota database in the MCP server.

## What worked and what remains

Earlier MCP tools could start a reservation but could not consume it in discovery or preview. The stdio test uses a test-only seed handler with the real fixture executor, then the registered discovery and preview handlers. It verifies the single reservation, refusal of incorrect stage order, seed and pool, and a preview with 1,200 selected seconds and 600 unused seconds. Jeswin's production seed handler and Paul's creation and recovery handlers are pending. This work does not exercise live YouTube traffic or the native approval dialog.

## Verification

All 294 offline tests passed, including the nine focused discovery and workflow cases. CI-scoped Ruff lint and formatting, mypy on 62 source files and all 34 planning checks passed locally. Aadyant's owner review is pending.

Related notes: [[2026-11-27-a2-02-discovery-quota]], [[09-quota-buckets-and-budgeting]] and [[11-mcp-and-agent-skill-contracts]].
