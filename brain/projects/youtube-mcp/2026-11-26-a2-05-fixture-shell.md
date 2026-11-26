---
id: 2026-11-26-a2-05-fixture-shell
type: ai-session
title: A2-05 early Claude Code fixture shell
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - docs/implementation/MASTER_PLAN.md
  - docs/implementation/TEAM_WORKPLAN.md
  - docs/implementation/CONTRACTS.md
  - https://code.claude.com/docs/en/mcp
  - https://code.claude.com/docs/en/skills
  - https://github.com/AadyantNeog/SEproject/issues/8
  - https://github.com/AadyantNeog/SEproject/pull/9
requirements:
  - NFR-01
  - SK-01
  - GOV-02
---

## Goal and outcome

Provide the early A2-05 fixture shell for the P2-03 handoff. Moved fixture composition into the shared MCP module and kept the existing module and console launch path. With an explicit checkout root, the service provides the two A2-06 previews and available canonical skills under fixed read-only resource URIs. Added a skill sync and byte-verification command. The work is tracked in [issue #8](https://github.com/AadyantNeog/SEproject/issues/8) and [draft PR #9](https://github.com/AadyantNeog/SEproject/pull/9).

## What worked and what changed during verification

The Windows Claude Code process connected from an isolated local profile using the installed v2.1.143 client. Its health check confirms the stdio connection. The Python MCP client verified tool and resource operations. An initial negative test expected both failure modes to raise a protocol exception. The pinned SDK returned a tool error result for the unknown tool, so the assertion now checks that result. Unknown resource reads still raise a protocol error.

## Verification and remaining integration

- 31 offline tests passed. Ruff lint and formatting passed for `src` and `tests`. Strict mypy passed on 23 source files and the locked wheel built.
- The sync command and its read-only check returned the same SHA-256 for a generated `brain-ingest` copy in a disposable workspace.
- The [fixture handoff](../../../docs/developer/claude-code-fixture.md) records the setup and connection check. Full product handlers, real account guards, progress and cancellation integration, and P2-03's native approval proof remain pending. Human owner review is pending.

Related notes: [[11-mcp-and-agent-skill-contracts]], [[15-implementation-boundaries-and-contracts]], [[2026-11-26-a2-06-presentation]].
