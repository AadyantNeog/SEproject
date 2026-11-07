---
id: "RN-10"
type: "research"
title: "Test fixtures and error cases"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf p. 2", "SDLC_and_Workflow.pdf pp. 2-3"]
requirements: ["FR-8", "NFR-09", "NFR-11", "SK-06"]
---

# Test fixtures and error cases

## Finding

The brief requires unit, integration and MCP-driven system tests. Explicit negatives include malformed IDs, private/deleted videos, missing tags, quotaExceeded, youtubeSignupRequired, expired tokens and rate limits. PR CI must use fixtures or mocks; live API testing belongs in a separately budgeted scheduled workflow.

## Project implication

Keep synthetic fixture data and predictable scoring/constraint assertions. Test zero provider calls after failed preflight and zero writes without valid human approval. Do not present planned tests as passed tests. Add regression cases for significant defects.

## Sources

- Project_1_YouTube_MCP.pdf p. 2 (supplied brief)
- SDLC_and_Workflow.pdf pp. 2-3 (supplied brief)

## Related notes

[[09-quota-buckets-and-budgeting]]; [[11-mcp-and-agent-skill-contracts]].

Issues and PRs: pending; no external work item is claimed.
