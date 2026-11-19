---
id: "AI-2026-11-19-EQUAL-WORKLOAD"
type: "ai-session"
title: "Equal workload implementation-plan revision"
created: "2026-11-19"
author: "Codex"
status: "recorded"
sources: ["User request in this chat, 2026-11-19: divide the work equally and revise everything accordingly", "docs/requirements/SRS.md", "docs/implementation/tasks.json", "docs/implementation/TEAM_WORKPLAN.md", "docs/implementation/PLAN_QA.md"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "NFR-11", "GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05"]
---

# Equal workload implementation-plan revision

## Goal

Replace the earlier unequal allocation with equal engineering responsibility and revise all affected active planning/agent/coverage/decision documents, preserving the fixed SRS and actual project history.

## Actual outcome

Prepared version 2 of the master plan/contracts/team workplan/role briefs and root AGENTS.md. Added a machine-readable 24-task register, retired-ID migration, current equal-owner coverage for all 46 requirements, ADR-0006 and [[17-equal-team-allocation]]. Updated the previous ADRs' ownership/task references and marked earlier allocation/session notes historical rather than rewriting their outcomes. Added a planning validator and preservation baseline; regular-commit and actual human-review requirements remain.

Each member has eight tasks and 56–80 planned hours, including tests/fixtures/docs/integration/reviews: Aadyant ranking/recommendations/planning/MCP/presentation; Jeswin HTTP/provider/OAuth/library/analytics/privacy; Paul storage/quota/approval/writes/recovery/CI. Matching estimates are a planning mechanism; actual-effort checks can trigger a recorded reallocation later. All three own substantial production decisions.

## What worked

Task IDs were versioned to prevent old prompts from assigning the wrong owner. Explicit provider-ledger, account-deletion, proposal-grant-write and snapshot-profile-analysis contracts preserve safety while allowing parallel work. Shared file editors, owned handler integration and rotating reviews prevent a hidden integration burden on one member. No product package existed in the inspected checkout, so no implemented work was silently reassigned.

## What failed or remains uncertain

An initial combined read was too large and was reread in focused chunks. A PowerShell rg glob needed directory filtering rather than a literal wildcard path. Initial planning validation flagged that Paul's brief did not explicitly name integration alongside its responsibilities; the brief was clarified and the checks rerun. These were inspection/document-check issues; no product/live test was attempted. Technical source claims remain dated 16 November; this revision performed no new upstream research. Equal effort has not yet been measured. Policy D-02, runtime/client/native proof, credentials/runner, implementation/CI/live tests, real member contributions and human reviews remain pending.

## Verification

Observed result: all 26 planning checks passed using `scripts/validate_implementation_plan.py --write-report --checked-on 2026-11-19`. They verified 24 unique current tasks, eight tasks/56–80 hours per person, registered dependencies and acyclic implementation prerequisites, all 46 exact requirement IDs/titles/verification strings, 20 acceptance IDs, owner/task/role agreement, retired-ID migration, local links/frontmatter/distilled citations and preserved regular-commit instructions. All 18 protected requirements/source PDFs/output documents match the 19 November pre-edit SHA-256 baseline. This is document integrity only, not product acceptance or measured workload equality; diagrams were source-reviewed, not renderer-tested.

The checkout was clean on main before this revision; work was isolated on `codex/equal-team-plan`. Actual Issue/PR/human review/release links remain pending; local branch/commit preparation does not establish them.

Related: [[2026-11-16-implementation-master-plan]], [[15-implementation-boundaries-and-contracts]], [[17-equal-team-allocation]], [[12-engineering-and-knowledge-workflow]], [[13-api-policy-dependency]].
