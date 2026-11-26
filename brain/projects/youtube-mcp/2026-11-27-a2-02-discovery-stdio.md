---
id: 2026-11-27-a2-02-discovery-stdio
type: ai-session
title: A2-02 fixture discovery through MCP
created: 2026-11-27
author: Codex
status: pending-review
sources:
  - docs/developer/metadata-ranking.md
  - tests/system/test_discovery_stdio.py
  - https://github.com/AadyantNeog/SEproject/issues/10
  - https://github.com/AadyantNeog/SEproject/pull/23
requirements:
  - FR-1.1
  - FR-1.2
  - FR-1.3
  - FR-2.1
  - FR-2.2
---

## Goal and outcome

Publish the video and channel discovery services through checkout-backed fixture MCP tools. Both tools normalize user-supplied identifiers with the J2-01 parsers. They use the J2-02 API-shaped catalog through the accounted HTTP executor and return the existing ranking and coverage models with rendered explanations.

## What worked and what failed

The SDK validates strict Python output before serializing it to JSON. The first probe used a JSON-mode dump and the SDK rejected the converted lists. Using a Python-mode dump preserved tuples and timestamps until SDK serialization. The default shell sandbox blocked the Windows Codex app server at startup. The isolated-state probe succeeded after authorized execution outside that sandbox.

## Verification

On Windows with Python 3.13.1, all 246 offline tests, scoped Ruff lint and formatting, and mypy on 50 source files passed. The stdio test covers ranked videos and channels, omitted evidence, metadata-only language, bounded upload sampling, malformed inputs and unavailable seeds. Codex Desktop `0.171.0-alpha.13.2` called both tools through the local app server and returned PostgreSQL B-Tree Index Scan Tuning and Query Craft from the fixture catalog. The probe ran without a model turn.

The synthetic budget is scoped to one mock request. P2-02's persistent workflow quota, account-bound candidate-set publication, affected live ranking and human owner review remain pending.

Related notes: [[2026-11-26-a2-02-ranking]], [[2026-11-26-j2-02-provider-follow-up]], [[02-metadata-based-similarity]] and [[11-mcp-and-agent-skill-contracts]].
