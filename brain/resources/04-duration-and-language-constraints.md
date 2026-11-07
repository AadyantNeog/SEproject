---
id: "RN-04"
type: "research"
title: "Duration and language constraints"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "https://developers.google.com/youtube/data/reference/rest/v3/videos/list"]
requirements: ["FR-5.1", "FR-5.2", "FR-5.3", "FR-0.1"]
---

# Duration and language constraints

## Finding

The project requires topic, total-duration, maximum-video-length and language constraints. These need precise acceptance semantics. API metadata may omit useful fields, so relevance or search hints alone cannot establish every constraint.

## Project implication

Project choice: interpret total duration as an upper bound; use integer seconds internally; clarify exact-fill requests. Exclude unknown durations, live/upcoming items and unknown language under a strict filter. Report unused time and infeasibility rather than silently relaxing constraints.

## Sources

- Project_1_YouTube_MCP.pdf pp. 1-2 (supplied brief)
- https://developers.google.com/youtube/data/reference/rest/v3/videos/list (accessed 7 November 2026)

## Related notes

[[06-preview-and-human-approval]]; [[10-test-fixtures-and-error-cases]].

Issues and PRs: pending; no external work item is claimed.
