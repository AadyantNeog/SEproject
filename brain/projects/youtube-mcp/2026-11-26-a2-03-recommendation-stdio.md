---
id: 2026-11-26-a2-03-recommendation-stdio
type: ai-session
title: A2-03 recommendation MCP fixture
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - docs/implementation/CONTRACTS.md
  - docs/developer/recommendations.md
  - tests/system/test_recommendation_stdio.py
  - https://github.com/AadyantNeog/SEproject/issues/14
requirements:
  - FR-3.2
  - FR-3.3
  - NFR-01
  - NFR-03
---

## Goal and outcome

Allow Windows Codex to call the existing recommendation service over the local fixture MCP server. The tool uses one bundled synthetic snapshot and a two-video candidate set at their recorded fixture time. It returns ranked output, exact duration, and source coverage and refuses unknown snapshots and unsupported arguments.

## What worked and what failed

The installed MCP SDK validates the Python result against the strict output model before serializing it. An initial JSON-mode dump turned tuples into lists too early. Returning the Python-mode dump preserved the strict types through SDK validation.

## Verification

The stdio regression covers discovery, the ranked response, an empty result and refusal of invalid filter, unknown snapshot, account override and workflow arguments. Codex invoked the actual fixture tool and received Database indexing with B-trees at 600 seconds, likes evidence and 120 unused seconds. All 234 offline tests, scoped Ruff and mypy, and all 34 planning checks passed on Windows. The authorized snapshot, candidate hydration, workflow quota and human owner review remain pending.

Related notes: [[2026-11-26-a2-03-recommendations]], [[03-authorised-preference-signals]] and [[11-mcp-and-agent-skill-contracts]].
