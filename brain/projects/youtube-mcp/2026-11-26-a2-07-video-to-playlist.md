---
id: 2026-11-26-a2-07-video-to-playlist
type: ai-session
title: A2-07 video-to-playlist fixture slice
created: 2026-11-26
author: Codex
status: pending-review
sources:
  - docs/requirements/SRS.md
  - docs/implementation/CONTRACTS.md
  - docs/evidence/skills/video-to-playlist.md
  - https://github.com/AadyantNeog/SEproject/issues/22
requirements:
  - FR-1.1
  - FR-5.1
  - FR-5.4
  - FR-5.5
  - FR-7
  - SK-05
  - SK-06
---

## Goal and outcome

Author the canonical video-to-playlist skill and a walkthrough for Windows Codex. The skill uses the composed workflow reservation before seed retrieval, retains server-issued references, and leaves playlist approval to the native human dialog.

## What worked and what failed

The existing allowlist already exposes the new skill when its canonical file exists. Codex reached the read-only fixture server and stopped before fetching the seed because `begin_workflow` was unavailable. The initial test candidate set was missing its required topic field and candidate bound. Adding both let the fixture exercise the real planner.

## Verification

The [evaluation record](../../../docs/evidence/skills/video-to-playlist.md) covers a positive constrained preview, an exact-fill clarification, infeasible language, stdio resource discovery, and the Codex refusal. The skill validator, 233 offline tests, all 34 planning checks, scoped Ruff and mypy passed on Windows. End-to-end quota, native decision, creation and recovery evaluation remains blocked on the integrated handlers and write path. Human owner review is pending.

Related notes: [[04-duration-and-language-constraints]], [[06-preview-and-human-approval]], [[09-quota-buckets-and-budgeting]] and [[11-mcp-and-agent-skill-contracts]].
