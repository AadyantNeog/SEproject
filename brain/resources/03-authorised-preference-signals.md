---
id: "RN-03"
type: "research"
title: "Authorised preference signals"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "https://developers.google.com/youtube/data/reference/rest/v3/videos/list"]
requirements: ["FR-3", "FR-4", "FR-0.2"]
---

# Authorised preference signals

## Finding

The brief requires recommendations from likes, subscriptions and playlists and excludes watch-history assumptions. The official videos.list method supports authorised myRating retrieval and documents a maximum of 1,000 returned rated videos.

## Project implication

Treat accessible collections as bounded preference evidence. Report collection completeness, deduplicate shared videos and disclose unavailable sources. Do not claim the retrieved set is the complete lifetime account history. Ask for a seed or topic when no usable signals exist.

## Sources

- Project_1_YouTube_MCP.pdf pp. 1-2 (supplied brief)
- https://developers.google.com/youtube/data/reference/rest/v3/videos/list (accessed 7 November 2026)

## Related notes

[[05-time-based-analysis]]; [[08-oauth-and-secret-handling]].

Issues and PRs: pending; no external work item is claimed.
