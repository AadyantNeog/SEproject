---
id: "RN-09"
type: "research"
title: "Quota buckets and budgeting"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf p. 2", "https://developers.google.com/youtube/data/determine_quota_cost"]
requirements: ["FR-7", "NFR-12"]
---

# Quota buckets and budgeting

## Finding

The brief describes a 10,000-unit daily default and requires rejecting over-budget workflows before any call. Current official documentation separates search.list into a 100-call daily bucket while other relevant methods use the 10,000-unit general bucket; resets occur at midnight Pacific Time.

## Project implication

Use a configurable dated cost profile. Estimate bounded pagination, revalidation, writes and retries; reserve every applicable bucket before the first call. Keep local estimates conservative and disclose shared-project usage that is invisible locally. Extra Cloud projects must not be used to evade limits.

## Sources

- Project_1_YouTube_MCP.pdf p. 2 (supplied brief)
- https://developers.google.com/youtube/data/determine_quota_cost (accessed 7 November 2026)

## Related notes

[[07-playlist-writes-and-partial-failure]]; [[10-test-fixtures-and-error-cases]].

Issues and PRs: pending; no external work item is claimed.
