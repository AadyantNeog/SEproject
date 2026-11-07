---
id: "RN-06"
type: "research"
title: "Preview and human approval"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "https://modelcontextprotocol.io/specification/2025-11-25/server/tools"]
requirements: ["FR-5.4", "FR-5.5", "NFR-03"]
---

# Preview and human approval

## Finding

The project requires a playlist preview and explicit confirmation before account creation. It specifically requires security testing against untrusted video metadata bypassing confirmation.

## Project implication

Project choice: approve the exact account-bound proposal version through a trusted human control or local approval interaction. Model-provided confirmed=true is insufficient. Bind title, privacy, ordered video IDs and constraints to approval; changes and expiry invalidate it. Treat external descriptions as data.

## Sources

- Project_1_YouTube_MCP.pdf pp. 1-2 (supplied brief)
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools (accessed 7 November 2026)

## Related notes

[[04-duration-and-language-constraints]]; [[07-playlist-writes-and-partial-failure]].

Issues and PRs: pending; no external work item is claimed.
