---
id: "RN-05"
type: "research"
title: "Time based analysis without watch history"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "https://developers.google.com/youtube/data/reference/rest/v3/playlistItems", "https://developers.google.com/youtube/data/reference/rest/v3/subscriptions"]
requirements: ["FR-4.1", "FR-4.2", "FR-4.3"]
---

# Time based analysis without watch history

## Finding

Official playlist-item metadata identifies when an item was added; subscription metadata identifies subscription creation. A video publication timestamp describes the video, not when the user engaged. Available likes do not establish watch time or reliable like-event dates.

## Project implication

Base comparisons on supported timestamps and name the date basis. Define start-inclusive/end-exclusive UTC intervals, missing-date handling and zero-baseline percentages. Distinguish collection composition from actual viewing behaviour. Mean runtime is a property of selected videos, not time watched.

## Sources

- Project_1_YouTube_MCP.pdf pp. 1-2 (supplied brief)
- https://developers.google.com/youtube/data/reference/rest/v3/playlistItems (accessed 7 November 2026)
- https://developers.google.com/youtube/data/reference/rest/v3/subscriptions (accessed 7 November 2026)

## Related notes

[[03-authorised-preference-signals]]; [[13-api-policy-dependency]].

Issues and PRs: pending; no external work item is claimed.
