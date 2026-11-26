---
id: 2026-11-27-a2-04-playlist-preview-stdio
type: ai-session
title: A2-04 fixture playlist preview through MCP
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - docs/developer/playlist-planning.md
  - tests/system/test_playlist_planning_stdio.py
  - https://github.com/AadyantNeog/SEproject/issues/12
  - https://github.com/AadyantNeog/SEproject/pull/30
requirements:
  - FR-5.1
  - FR-5.2
  - FR-5.3
  - FR-5.4
---

## Goal and outcome

Publish `propose_playlist` over the fixture MCP server. The server uses the existing planner, language normalizer, proposal renderer and SQLite repository. The tool resolves the bundled synthetic candidate set, applies strict validation and saves the exact preview before it returns it.

## What worked and what failed

The locked SDK preserved typed clarification errors when the boundary validated the original arguments. Exact-duration requests, unsupported or infeasible inputs, foreign candidate references and a supplied confirmation argument returned errors. The rejected cases left the isolated database uncreated. The successful case returned the same immutable proposal that SQLite held after the subprocess exited, with zero operation rows.

## Verification

On Windows with Python 3.13.1, all 247 offline tests, scoped Ruff lint and formatting, and mypy on 52 source files passed. Codex Desktop `0.171.0-alpha.13.2` invoked the tool through a local app-server probe without a model turn. It showed a private fixture preview with 600 seconds selected and 120 seconds unused. The stdio test verified the stored digest, the ten-minute expiry and the ordered item list.

This fixture slice uses an existing static catalog. Discovery-backed candidate sets, shared quota, atomic revisions with approval invalidation and the human owner review remain pending.

Related notes: [[2026-11-26-a2-04-playlist-planning]], [[2026-11-27-a2-02-discovery-stdio]], [[04-duration-and-language-constraints]] and [[06-preview-and-human-approval]].
