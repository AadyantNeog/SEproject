# Team lead review policy

Version 2.1 · 21 November 2026 · Team lead: Aadyant Neog · Author: Codex

Aadyant is the required human reviewer for every PR and deliverable produced by Jeswin or Paul. This replaces the rotating-review arrangement. The existing 24 implementation tasks, their owners, prerequisites and 56–80-hour engineering ranges remain; lead review and coordination are additional work tracked separately. The SRS and product approval/security boundaries are unchanged.

## Review ownership

| Work author or contributor | Required review and acceptance |
| --- | --- |
| Jeswin | Aadyant reviews every PR and deliverable; Jeswin addresses feedback and returns the updated version to Aadyant |
| Paul | Aadyant reviews every PR and deliverable; Paul addresses feedback and returns the updated version to Aadyant |
| Jeswin and Paul jointly | Aadyant reviews the combined work and its integration/evidence |
| Aadyant | Jeswin or Paul, who did not author or materially coauthor the change, provides the independent human PR review; Aadyant's self-check is not that review |
| Teammate work materially coauthored by Aadyant | Aadyant still checks the teammate deliverable as lead; another non-author human supplies independent review of the combined change |

This applies to code, tests, fixtures/oracles, architecture/contracts/ADRs, documentation, skills, brain notes, validation reports, demonstrations, integration evidence and stage/release deliverables. A passing CI run, AI review, model-controlled approval field or another teammate's feedback does not replace Aadyant's required review. If no eligible independent reviewer is available for Aadyant-authored/coauthored work, keep the PR unmerged until a real reviewer is available.

The non-author rule is the project's independent-review safeguard. GitHub also prevents an author from approving their own PR. [GitHub review documentation](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request).

## Handoff and review cycle

1. The author completes a coherent change on their task branch, commits regularly, runs the relevant checks and prepares a PR or versioned deliverable. Each author remains responsible for implementation, tests, docs, integration fixes and truthful evidence.
2. The handoff names the task/requirements, actual Issue/PR links, exact commit or artefact version, changed behaviour, checks/observations, remaining blocks and decisions needed. A standalone report or demo links its source commit and observable evidence. Keep secrets/private payloads out of review records.
3. Teammates request Aadyant's human review. He checks scope, correctness, interfaces, relevant authority/quota/privacy/recovery invariants, necessary tests, documentation and traceability. Affected owners may give technical input; it does not substitute for the required reviewer.
4. Record Aadyant's actual decision against that version: changes requested, approved, or still pending. The author fixes findings, commits the changes and requests review again. A materially changed commit/deliverable needs fresh review; do not carry an earlier approval forward silently.
5. Merge/accept only after the required current-version human review and checks. Aadyant coordinates stage/release readiness and reviews the teammate evidence bundle; the owner still assembles and demonstrates their contribution. Aadyant-authored portions retain the independent-review rule above.

Review requests and approvals are genuine human actions. Agents may prepare diffs, run checks, explain findings and draft handoff text, but cannot impersonate Aadyant, Jeswin or Paul, submit fabricated approvals, mark lead acceptance from chat inference, or send review-request messages without authority. Local preparation or a commit is not a completed PR review.

Engineering review does not grant OAuth scope or approve a learner's playlist. Live account writes still require the application's trusted human approval of the exact account-bound proposal through the existing FR-5 workflow.

## Repository configuration and evidence

P2-06 prepares CODEOWNERS/PR-template/required-review settings or checks to implement this policy using verified real accounts and available repository capabilities. It must cover both teammate-authored and Aadyant-authored PRs without creating a self-approval loophole or blocking legitimate independent review. Merely listing several owners does not require every listed owner to approve; GitHub documents that any one matching owner may satisfy its code-owner approval requirement. [GitHub code-owner documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).

Verify the author/reviewer matrix, changed-version re-review and absent-approval refusal before claiming repository enforcement. Do not invent GitHub handles, change remote settings as part of this local planning edit, or claim existing protection/approvals were inspected. Until configuration is actually verified, this is the documented workflow and its enforcement evidence remains pending.

## Workload and scheduling

The eight tasks and 56–80-hour range per person describe the equal implementation baseline, including tests/docs/integration, author self-checks, review preparation and feedback fixes. They exclude Aadyant's centralized lead-review/coordination time and independent reviews of Aadyant's PRs. Track those review hours separately. Total workload is therefore not asserted equal after this leadership assignment. At G1/G3 and weekly checkpoints, Aadyant schedules review capacity and records any explicitly agreed remaining-work adjustment; no agent silently reallocates coding or removes a review gate to meet a date.

Basis: [18-team-lead-review-governance](../../brain/resources/18-team-lead-review-governance.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [ADR-0007](../adr/0007-team-lead-review-and-deliverable-acceptance.md). The author/reviewer policy is also represented in [tasks.json](tasks.json).
