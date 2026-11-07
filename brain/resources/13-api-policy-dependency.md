---
id: "RN-13"
type: "research"
title: "API policy dependency"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["https://developers.google.com/youtube/terms/developer-policies", "Project_1_YouTube_MCP.pdf pp. 1-2"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "NFR-05"]
---

# API policy dependency

## Finding

The official developer policy restricts derived metrics and data. The brief requires similarity and aggregated analysis, creating a policy applicability question for live use. Metadata also has refresh/deletion and user-removal obligations.

## Project implication

Record dependency D-02 in the SRS. Obtain instructor/provider clarification before affected live deployment. Do not claim that labelling computed scores alone resolves permission. Continue fixture-based verification without representing it as live evidence.

## Sources

- https://developers.google.com/youtube/terms/developer-policies (accessed 7 November 2026)
- Project_1_YouTube_MCP.pdf pp. 1-2 (supplied brief)

## Related notes

[[02-metadata-based-similarity]]; [[05-time-based-analysis]]; [[08-oauth-and-secret-handling]].

Issues and PRs: pending; no external work item is claimed.
