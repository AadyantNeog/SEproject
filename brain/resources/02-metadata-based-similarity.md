---
id: "RN-02"
type: "research"
title: "Metadata based similarity"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["Project_1_YouTube_MCP.pdf p. 2", "https://developers.google.com/youtube/data/reference/rest"]
requirements: ["FR-1", "FR-2"]
---

# Metadata based similarity

## Finding

The brief explicitly says there is no related-video or related-channel endpoint and requires locally computed similarity. It suggests TF-IDF, cosine similarity or basic weighted scoring using video/channel metadata.

## Project implication

Specify observable ranking behaviour, seed exclusion, stable tie rules, missing-feature handling and selection reasons. Leave exact weights for design. Similarity is an application estimate and does not establish teaching quality. Consult the policy dependency before enabling live derived processing.

## Sources

- Project_1_YouTube_MCP.pdf p. 2 (supplied brief)
- https://developers.google.com/youtube/data/reference/rest (accessed 7 November 2026)

## Related notes

[[01-project-problem-and-scope]]; [[13-api-policy-dependency]].

Issues and PRs: pending; no external work item is claimed.
