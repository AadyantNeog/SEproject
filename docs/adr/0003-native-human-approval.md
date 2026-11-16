# ADR-0003: Native human confirmation bound to an immutable proposal

Date: 16 November 2026 · Author: Codex · Status: proposed; Windows/client proof required

## Context

FR-5.5 and NFR-03 reject model-controlled confirmation. A client tool annotation, OAuth write scope or generated chat sentence does not prove human agreement to one exact account/title/privacy/order/constraint set. External metadata is untrusted.

Distilled basis: [06-preview-and-human-approval](../../brain/resources/06-preview-and-human-approval.md), [11-mcp-and-agent-skill-contracts](../../brain/resources/11-mcp-and-agent-skill-contracts.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Use a server-launched native approval helper, reading the full immutable stored proposal and capturing a direct human decision. Bind its private parent/helper interaction to an unpredictable challenge, current account/channel, digest/version and server-issued operation ID. The server creates an internal one-use grant, valid no longer than ten minutes or proposal expiry. No tool/CLI flag accepts a grant or auto-approval. Rejection, expiry, helper failure and unavailable UI fail closed.

Keep a shared pure proposal renderer owned by Jeswin so MCP output and human confirmation describe the same content. A02 must test actual launch/lifecycle from the selected Windows client, full preview and zero writes after refusal. Unit/system tests inject fake approval adapters only from fixture test code.

## Consequences and limits

The baseline depends on an interactive Windows desktop with Tk availability. It avoids assuming every MCP client has a trusted proposal-specific confirmation widget. A compromised OS or unrestricted agent that can alter the process/state or drive its UI is outside the local trust boundary. The demonstration client must not have unattended shell/computer automation capable of acting on the helper. If that boundary cannot be demonstrated, live writes remain blocked; do not substitute a boolean. A future client-native path needs separate proof and an ADR update.

## Verification and links

Requirements: FR-5.4/5.5, NFR-03/07. Tasks: A02/A09/A10, J03. Acceptance: AT-06/08/12/14/19. Actual client proof, Issue/PR and test links: pending. [Authority contract](../implementation/CONTRACTS.md).
