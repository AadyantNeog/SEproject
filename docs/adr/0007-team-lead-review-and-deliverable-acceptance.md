# ADR-0007: Team lead review and deliverable acceptance

Date: 21 November 2026 · Author: Codex · Status: user-directed review responsibility; actual reviews/configuration pending

## Context

The user identified Aadyant as team lead and directed that he review all teammate PRs and everything they produce. The previous plan rotated reviews and coordination. SRS GOV-03 requires actual human-reviewed PRs; the project also retains an independent non-author review rule. Equal implementation ownership does not imply equal total workload once centralized review is added.

Distilled basis: [18-team-lead-review-governance](../../brain/resources/18-team-lead-review-governance.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [17-equal-team-allocation](../../brain/resources/17-equal-team-allocation.md).

## Decision

Aadyant reviews all Jeswin/Paul PRs and deliverables, including tests, fixtures, contracts/design, docs, skills, brain records and acceptance evidence. Authors prepare reviewable versions, fix feedback and request re-review after material changes. Technical feedback, CI and AI review do not replace Aadyant's actual approval. He coordinates review scheduling and stage/release acceptance; module owners still implement, integrate, document and repair their own work.

Aadyant-authored work needs an independent review from a non-author Jeswin or Paul. If Aadyant materially coauthors teammate work, another eligible non-author reviews the combined change while Aadyant retains lead oversight of the teammate delivery. No self-approval, fabricated reviewer or review inferred from an earlier version is accepted.

Keep the A2/J2/P2 task IDs, owners, dependency graph and equal 56–80-hour implementation estimates. Track lead review/coordination and independent review separately; do not claim total hours remain equal. P2-06 prepares verified real-account review enforcement later, covering the author exceptions without weakening the lead gate. No remote settings are changed by this planning revision.

## Consequences and supersession

This supersedes the rotating-review/coordination portions of ADR-0006 and the review wording in the version 2.0 plan. The implementation allocation, technical decisions, SRS and playlist human-approval boundary remain unchanged. Lead review is a human scheduling dependency; when it is pending, work remains pending rather than auto-approved. Aadyant's lead role does not make him the author of all teammate fixes or evidence.

## Verification

Check the author/reviewer matrix in tasks.json, every task's review requirement, all role prompts/docs and the coverage review gates. Preserve 24 implementation tasks, eight per owner, all 46 requirements and 20 acceptance scenarios. Actual Issue/PR/reviewer decisions, account handles, repository enforcement and workload measurements remain pending. See [REVIEW_POLICY.md](../implementation/REVIEW_POLICY.md) and [PLAN_QA.md](../implementation/PLAN_QA.md).
