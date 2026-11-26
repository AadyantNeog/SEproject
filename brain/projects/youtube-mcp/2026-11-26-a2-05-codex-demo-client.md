---
id: 2026-11-26-a2-05-codex-demo-client
type: ai-session
title: A2-05 Codex demo client and P2-03 fixture check
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - Project_1_YouTube_MCP.pdf p. 1
  - docs/requirements/SRS.md
  - docs/adr/0009-codex-demonstration-client.md
  - https://developers.openai.com/codex/mcp
  - https://developers.openai.com/codex/skills
  - https://developers.openai.com/codex/app-server
  - https://github.com/AadyantNeog/SEproject/issues/8
  - https://github.com/AadyantNeog/SEproject/pull/17
requirements:
  - NFR-01
  - NFR-03
  - FR-5.4
  - FR-5.5
  - SK-01
---

## Goal and outcome

Aadyant chose Codex Desktop for the Windows demonstration. Codex recorded the decision in ADR-0009 and prepared the configuration and fixture verification steps. The A2-05 client setup and P2-03 native dialog retain their existing owners.

## What worked and what failed

Claude Code connected to the fixture transport but reported a missing login when asked to read the preview. The first Codex app-server startup was blocked from accessing its state directory in the development sandbox. A separate test state directory and an authorised local run allowed the check to proceed. The first interactive fixture run returned a synthetic approval and discarded the grant. A second run reported that both manual dismissal paths issued no grant.

## Verification

- The Codex Desktop app server `0.171.0-alpha.13.2` on Windows build `26300` read the creation preview and `brain-ingest` resource via MCP at `d583793f4a6e44ab43f7a0f32f38d8c07413c3de`.
- The Codex client invoked the temporary fixture diagnostic through stdio. The diagnostic used Paul's native launcher with Windows Python 3.13.1 and Tcl 8.6.15. The responses for Close and Reject each reported launcher exit code 0 and no grant.
- The fixture check did not run a model turn. Product workflow execution, review and live acceptance remain separate.
- After merging `main` at `b54573e` into [PR #20](https://github.com/AadyantNeog/SEproject/pull/20), the read-only Windows Codex probe, 229 offline tests, all 34 planning checks, scoped Ruff and mypy passed. The manual dismissal evidence is from the earlier run above.

Related notes: [[11-mcp-and-agent-skill-contracts]] and [[06-preview-and-human-approval]].
