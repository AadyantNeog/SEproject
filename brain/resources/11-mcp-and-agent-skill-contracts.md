---
id: "RN-11"
type: "research"
title: "MCP and agent skill contracts"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["https://modelcontextprotocol.io/specification/2025-11-25/server/tools", "https://agentskills.io/specification", "SDLC_and_Workflow.pdf p. 2"]
requirements: ["NFR-01", "SK-01", "SK-02", "SK-03", "SK-04", "SK-05", "SK-06"]
---

# MCP and agent skill contracts

## Finding

MCP tools provide named operations and schemas. Agent Skills use instruction folders containing SKILL.md with YAML frontmatter. A skill is not a distinct MCP protocol primitive. The SDLC requires brain-ingest, brain-refine, brain-query and local-check, while the YouTube brief adds video-to-playlist.

## Project implication

Deliver skills as versioned instructions and document the supported client loading route; expose help resources without claiming automatic compatibility with all clients. Keep stdout reserved for the stdio protocol. Every skill must cite a distilled note and have stage-appropriate evaluations.

## Sources

- https://modelcontextprotocol.io/specification/2025-11-25/server/tools (accessed 7 November 2026)
- https://agentskills.io/specification (accessed 7 November 2026)
- SDLC_and_Workflow.pdf p. 2 (supplied brief)

## Related notes

[[12-engineering-and-knowledge-workflow]]; [[06-preview-and-human-approval]].

Issues and PRs: pending; no external work item is claimed.
