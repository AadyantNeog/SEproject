# ADR-0003: Native human confirmation bound to an immutable proposal

Date: 16 November 2026 · Author: Codex · Status: proposed; Windows/client proof required

Task/ownership references amended 19 November 2026 under [ADR-0006](0006-equal-team-workload-and-shared-integration.md); trusted-human boundary unchanged.

## Context

FR-5.5 and NFR-03 reject model-controlled confirmation. A client tool annotation, OAuth write scope or generated chat sentence does not prove human agreement to one exact account/title/privacy/order/constraint set. External metadata is untrusted.

Distilled basis: [06-preview-and-human-approval](../../brain/resources/06-preview-and-human-approval.md), [11-mcp-and-agent-skill-contracts](../../brain/resources/11-mcp-and-agent-skill-contracts.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Use a server-launched native approval helper, reading the full immutable stored proposal and capturing a direct human decision. Bind its private parent/helper interaction to an unpredictable challenge, current account/channel, digest/version and server-issued operation ID. The server creates an internal one-use grant, valid no longer than ten minutes or proposal expiry. No tool/CLI flag accepts a grant or auto-approval. Rejection, expiry, helper failure and unavailable UI fail closed.

Keep a shared pure proposal renderer owned by Aadyant (A2-06) so MCP output and human confirmation describe the same content. Paul (P2-03) proves actual native-helper launch/lifecycle and full-preview refusal with zero writes using Aadyant's client shell (A2-05); Jeswin supplies account binding (J2-03). Unit/system tests inject fake approval adapters only from fixture test code.

### Creation proposal digest

The A2-04 fixture planner defines `proposal-authority-v1` for creation proposals. It hashes compact UTF-8 JSON with sorted keys using SHA-256. The payload binds the account and mode, proposal ID and version, candidate set, expiry, destination label, playlist body, constraints, ordered items, totals, exclusions, warnings, and algorithm versions. Arrays retain their order. The canonical video links derive from the bound video IDs.

The stored proposal carries issuance time and mutable state separately. The approval path checks state and expiry before a write. An explicit revision supersedes the old version and creates a new `proposed` version with a new digest. The application and repository must persist both changes and invalidate obsolete approval in one transaction. P2-05 owns the separate authority payload for recovery. This digest definition is pending human review and integration with P2-03 and P2-04. [A2-04 issue #12](https://github.com/AadyantNeog/SEproject/issues/12)

## Consequences and limits

The baseline depends on an interactive Windows desktop with Tk availability. It avoids assuming every MCP client has a trusted proposal-specific confirmation widget. A compromised OS or unrestricted agent that can alter the process/state or drive its UI is outside the local trust boundary. The demonstration client must not have unattended shell/computer automation capable of acting on the helper. If that boundary cannot be demonstrated, live writes remain blocked; do not substitute a boolean. A future client-native path needs separate proof and an ADR update.

## Verification and links

Requirements: FR-5.4/5.5, NFR-03/07. Tasks: P2-03/P2-04, A2-05/A2-06, J2-03. Acceptance: AT-06/08/12/14/19. Actual client proof, Issue/PR and test links: pending. [Authority contract](../implementation/CONTRACTS.md).
