---
id: "RN-17"
type: "research"
title: "Equal team allocation and shared integration"
created: "2026-11-19"
author: "Codex"
status: "distilled"
sources: ["User request in this chat, 2026-11-19: divide the work equally and revise everything accordingly", "docs/requirements/SRS.md sections 11, 13-15", "docs/implementation/tasks.json", "docs/implementation/TEAM_WORKPLAN.md"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "NFR-11", "GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05"]
---

# Equal team allocation and shared integration

Review-governance amendment, 21 November: the equal implementation tracks remain, but the earlier rotating-review arrangement below is historical. Aadyant now leads review of every teammate PR/deliverable; his own work needs independent non-author review. Lead-review/coordination hours are tracked in addition to the implementation baseline. See [[18-team-lead-review-governance]] and [[2026-11-21-team-lead-review-update]].

## Finding

On 19 November 2026 the user replaced the earlier unequal workload preference with an equal split. The SRS fixes project behaviour and genuine team contribution/review, but does not require Aadyant to implement most modules. A change of allocation does not authorise a scope change or rewrite actual authorship/history.

## Current project choices

Version 2 assigns eight tasks and 56–80 planned hours per member. Aadyant owns ranking/recommendations/planning/MCP/presentation; Jeswin owns provider/HTTP/OAuth/library/analytics/privacy; Paul owns storage/quota/approval/writes/recovery/CI. Each also supplies tests, fixtures, feature docs, handler integration, reviews and observed evidence. This distributes complex engineering rather than making two people support-only.

New A2/J2/P2 task IDs distinguish the new allocation from retired prompts. Common reviewed contracts enable all three to develop in parallel after a short bootstrap. Named editors and affected-owner review protect shared files. Integration/evidence is shared across tracks; actual-effort checkpoints at G1/G3 trigger explicit rebalancing of remaining work if needed. Matching estimates are a planning mechanism, not measured equality or a grade guarantee.

## Links and evidence limits

[[15-implementation-boundaries-and-contracts]] records the original planning preference; [[2026-11-16-implementation-master-plan]] is its historical session. Current session: [[2026-11-19-equal-workload-revision]]. Technical authority/quotas/approval/policy remain covered by [[06-preview-and-human-approval]], [[07-playlist-writes-and-partial-failure]], [[09-quota-buckets-and-budgeting]], [[12-engineering-and-knowledge-workflow]], [[13-api-policy-dependency]].

Authoritative revised documents are `docs/implementation/`, root AGENTS.md and ADR-0006 outside the vault. Actual Issues/PRs, human member acceptance/authorship/reviews, implementation, live permissions/tests and release remain pending. No new upstream technical research is claimed by this allocation revision.
