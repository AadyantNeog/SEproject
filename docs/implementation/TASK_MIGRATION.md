# Version 2 task migration and starting order

19 November 2026 · Allocation revision only · Author: Codex

The user replaced the earlier unequal allocation with equal work. Version 2 of the master plan, contracts, workplan, role briefs, coverage register and AGENTS.md is authoritative for new work. Every member has eight tasks and 56–80 planned hours, including implementation/tests/docs/integration/reviews. [tasks.json](tasks.json) records the new task IDs. This does not change the SRS or claim any previous implementation/review occurred.

## Retired task IDs

The old IDs below are historical references only; do not execute an old chat prompt or interpret its owner as current. Existing human authorship, commits, Issues and PRs must not be rewritten or reassigned. If real work exists by the time implementation begins, inspect it and link its actual evidence to the corresponding new tasks rather than rebuilding or attributing it to someone else. At this revision, the inspected checkout contained planning/document-generation artefacts and no product package; this is not a claim about uninspected remote branches.

| Retired ID | Current task destination |
| --- | --- |
| A01 | A2-01 bootstrap/common contracts |
| A02 | A2-05 client/MCP shell; P2-03 native approval proof |
| A03 | J2-01 parsing/executor; J2-02 read/fixture provider; P2-04 write adapters |
| A04 | J2-03 OAuth/vault/account; P2-01 deletion/storage interface |
| A05 | P2-01 repositories/cache; P2-02 quota/sessions |
| A06 | A2-02 video/channel discovery/ranking |
| A07 | J2-04 library retrieval; A2-03 profile/recommendations |
| A08 | A2-04 strict playlist planning/proposals |
| A09 | P2-03 native approval/grants; A2-06 exact preview |
| A10 | P2-04 writer/journal; P2-05 reconciliation/recovery |
| A11 | A2-05 composition plus each owner's handlers; A2-08/J2-08/P2-08 actual integration |
| A12 | A2-08 feature measures/evidence; J2-08 read/privacy; P2-07 harness and P2-08 write/release assembly |
| J01 | J2-05 collection analytics |
| J02 | J2-05 period comparisons |
| J03 | A2-06 presentation/preview |
| J04 | J2-08 analytics/read evidence and individual human contribution |
| P01 | All three supply owned feature fixtures; J2-02 shared read/fixture engine; P2-04/P2-05 write-state fixtures |
| P02 | P2-06 CI/secret/shared test setup; J2-06 knowledge/skill validation |
| P03 | J2-06 brain skills; P2-07 local-check; A2-07 video-to-playlist; A2-05 client adapter |
| P04 | J2-07 consent/privacy/scheduled reads; P2-07 harness; A2-08/J2-08/P2-08 owned docs/evidence/integration |

## Start now and continue later

1. All three read the revised plan, review allocation and prepare real task Issues/branches. Aadyant implements **A2-01 only** first, with Jeswin and Paul reviewing their interface examples.
2. After that contract PR is human-reviewed and merged, Aadyant starts **A2-06** and the early **A2-05** client shell, Jeswin starts **J2-01**, and Paul starts **P2-01**. Paul begins the **P2-03** human-approval proof as soon as the preview is ready. Consumers need no live credentials for synthetic development.
3. Continue dependency-ready tasks in [TEAM_WORKPLAN.md](TEAM_WORKPLAN.md), not the old numeric/chat sequence. Publish interfaces early, implement in separate branches, commit coherent verified steps, obtain actual human PR review, then pull merged dependencies before the next task.
4. Every owner integrates/tests/documents their own track. A2-08, J2-08 and P2-08 share final evidence and review; nobody inherits all integration by default. Re-estimate actual remaining effort at G1/G3 and explicitly rebalance if necessary.

New copyable prompts are in section 10 of the workplan. Human approvals, policy D-02, credentials/runner setup, actual product tests/CI and live acceptance remain separate requirements; equal allocation does not bypass them.

Basis: [17-equal-team-allocation](../../brain/resources/17-equal-team-allocation.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md).
