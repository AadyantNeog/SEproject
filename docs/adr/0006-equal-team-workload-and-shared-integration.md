# ADR-0006: Equal engineering tracks and shared integration

Date: 19 November 2026 · Author: Codex · Status: user-directed allocation; implementation details pending human review

Review governance amended 21 November under [ADR-0007](0007-team-lead-review-and-deliverable-acceptance.md); equal implementation ownership/task IDs remain.

## Context

The original 16 November planning allocation placed most difficult engineering with Aadyant and smaller analytics/workflow assignments with Jeswin/Paul. On 19 November the user explicitly changed that preference to an equal split and requested all planning documents be revised. The fixed SRS still requires all five features, authority/quota/security boundaries, reviews and attributable contributions.

Distilled basis: [17-equal-team-allocation](../../brain/resources/17-equal-team-allocation.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Allocate eight tasks and 56–80 estimated hours to each member, covering complex production code plus tests/fixtures/docs/integration, AI-assisted author checks, handoffs and feedback fixes; centralized lead-review/coordination is tracked separately:

- Aadyant: common bootstrap/contracts/MCP, similarity/recommendations, strict proposal planning, shared presentation and product skill.
- Jeswin: input parsing/accounted HTTP, official read/fixture provider, OAuth/vault/account, library collection, analytics, knowledge workflows and privacy/live-read setup.
- Paul: repositories/cache/retention, project quota/sessions, native human approval, guarded writes/journal/recovery, CI and local-check/measurement tooling.

Use versioned task IDs A2-01–A2-08, J2-01–J2-08, P2-01–P2-08. Retire the earlier IDs with a mapping. A2-01 publishes reviewed contracts first; all three then implement in parallel with isolated fixtures. Every service owner supplies their handler integration and fixes, rather than delegating all assembly to the composition owner. Share documentation/evaluations; Aadyant leads review of all teammate work and stage acceptance under ADR-0007, while his authored/coauthored portions use AI-assisted recorded human owner review. Judge actual workload by effort/complexity/defects/reviews, not equal counts alone; re-estimate at G1/G3.

## Consequences

Jeswin and Paul now own substantial security/reliability modules. Cross-owner contracts require early executable examples and explicit integration checks: real quota debit through the HTTP executor; disconnect through storage deletion; exact proposal → grant → writes; snapshots → recommendation/analytics. One editor per shared-file PR prevents agent races. Extra handoffs are included in the equal task ranges and a team contingency remains necessary.

The modular-monolith technology/algorithms/authority rules are unchanged. This ADR supersedes earlier ownership portions of ADR-0001 and task references in ADR-0002–0005, not their technical decisions. Historical session notes/logs retain what actually happened and carry supersession notices. No teammate acceptance, implementation, Issue/PR, human review, permission or release is invented.

## Verification and links

Requirements: FR-1–FR-5, NFR-11, GOV-01–GOV-05. Verify all 24 tasks, acyclic prerequisites, equal 56–80-hour totals, current owner/coverage/role agreement, retired-task mapping, 46 unchanged requirements and 20 acceptance cases. [Master plan](../implementation/MASTER_PLAN.md), [workplan](../implementation/TEAM_WORKPLAN.md), [migration](../implementation/TASK_MIGRATION.md), [planning QA](../implementation/PLAN_QA.md). Real Issues/PRs, human reviews and actual effort/evidence: pending.
