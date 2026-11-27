---
id: 2026-11-27-p2-02-cancellation-follow-up
type: ai-session
title: P2-02 release quota when a workflow stage is cancelled
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - https://github.com/AadyantNeog/SEproject/issues/26
  - https://github.com/AadyantNeog/SEproject/pull/27
  - tests/system/test_composed_workflow_budget.py
  - docs/developer/quota-workflows.md
requirements:
  - FR-7
  - NFR-09
---

## Goal and outcome

At Aadyant's request, Codex followed up on Paul's `4ed9072` quota implementation. A cancelled request for the next valid stage now closes the session and releases its remaining SQLite reservation. The cleanup is shielded from cancellation. An invalid or duplicate stage still cannot release a valid running workflow.

## What worked and what failed

With the quota fully reserved, the original code refused a replacement workflow after the first stage was cancelled before entry. The new regression reproduced that failure before the fix. After the fix it starts the replacement immediately and rejects reuse of the cancelled workflow ID. The tests also exercise cancellation during stage execution and an invalid duplicate request carrying a cancelled token.

## Verification

On Windows, 11 focused quota and workflow tests and all 269 offline tests passed. Scoped Ruff lint and formatting, mypy on 56 source files, and the planning validator passed. Paul’s existing service test exercises seed, discovery and preview through one reservation. The separate stdio test verifies start and preflight refusal. The owner handlers still need to use the shared runtime over MCP. Human review remains pending.

Related notes: [[2026-11-26-p2-01-storage]], [[2026-11-27-a2-05-discovery-progress]], [[09-quota-buckets-and-budgeting]] and [[11-mcp-and-agent-skill-contracts]].
