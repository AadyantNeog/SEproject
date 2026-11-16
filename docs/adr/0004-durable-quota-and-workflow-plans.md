# ADR-0004: Project-scoped quota reservations before provider calls

Date: 16 November 2026 · Author: Codex · Status: proposed for human review

## Context

FR-7 requires rejection before the first provider call if any applicable quota bucket cannot fund the bounded workflow. NFR-12 requires configurable dated costs, separate general/search buckets, restart persistence and the provider's reset boundary. Read retries and nested pagination make per-request guesses insufficient.

Distilled basis: [09-quota-buckets-and-budgeting](../../brain/resources/09-quota-buckets-and-budgeting.md), [10-test-fixtures-and-error-cases](../../brain/resources/10-test-fixtures-and-error-cases.md), [16-official-api-design-check-2026-11-16](../../brain/resources/16-official-api-design-check-2026-11-16.md).

## Decision

Construct a finite endpoint/page/candidate/attempt/deadline plan and reserve its entire bucket vector in SQLite before provider access. Use atomic project/reset-period transactions across requests/instances. Every attempt is charged before dispatch; read attempts are bounded, writes have no automatic retry, unused reservations are released, and ambiguous crash accounting is conservative.

For a declared composed product skill, start a workflow session before seed retrieval and share its complete reservation across all tool stages. Standalone read tools reserve their whole service workflow. Splitting an end-to-end user request into separately affordable tool calls does not satisfy preflight; insufficient composed budget rejects even the initial seed fetch.

Keep versioned costs/limits/reference dates and use America/Los_Angeles midnight with DST. A restarted process cannot reset used quota, and disconnect cannot delete the shared-project accounting. Detect local duplicate instances; share their ledger or refuse them. Budgeted reconciliation is part of the plan, not an unplanned side request.

## Consequences

Conservative worst-case reservation may reject work that might succeed with fewer actual calls. This is preferable to violating the preflight commitment. The ledger cannot observe every other consumer of the Cloud project, so balances are explicitly estimates and external quota failures stop affected calls. A cost-profile/reset-period change requires re-planning unstarted work. No additional Cloud projects are created to avoid limits.

## Verification and links

Requirements: FR-7, NFR-06/09/12, TQ-6. Tasks: A03/A05/A10, P01. Acceptance: AT-13/15/16. Concurrent/restart/DST/cost-change fixture tests and Issue/PR links: pending. [Budget formulas and examples](../implementation/MASTER_PLAN.md).
