# ADR-0009 Choose Codex Desktop for the Windows demonstration

Date: 26 November 2026 · Author: Codex · Status: pending human review

## Context

The project brief gives several AI client examples. SRS NFR-01 requires at least one documented MCP client, and A-01 requires a client that can load skills, display structured results and work with a trusted local confirmation path. The early A2-05 experiment used Claude Code. Aadyant selected Codex as the demo client on 26 November 2026.

Distilled basis: [MCP and agent skill contracts](../../brain/resources/11-mcp-and-agent-skill-contracts.md) and [preview and human approval](../../brain/resources/06-preview-and-human-approval.md).

## Decision

Use Codex Desktop on Windows with the local stdio server and the canonical repository skills under `.agents/skills/`. Keep A2-05 and P2-03 ownership and the SRS acceptance criteria. Use the server-owned native dialog and exact-proposal approval rules from [ADR-0003](0003-native-human-approval.md).

## Verification

Use the [Codex fixture runbook](../developer/codex-fixture.md) to verify resource discovery, the synthetic preview and the native refusal path. The test uses an isolated fixture process and leaves the native controls to the human operator. Any future live demonstration still requires a client configuration that prevents the agent from operating the dialog, plus the project's other live prerequisites.

Requirements NFR-01, NFR-03, FR-5.4, FR-5.5 and SK-01. Issues [#8](https://github.com/AadyantNeog/SEproject/issues/8) and [#16](https://github.com/AadyantNeog/SEproject/issues/16).
