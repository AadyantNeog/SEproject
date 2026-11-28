---
id: "REVIEW-STAGE-2-DESIGN"
type: "review"
title: "Stage 2 design review"
created: "2026-11-28"
author: "Claude Code draft for the team; human authors pending"
status: "pending-review"
sources: ["SDLC_and_Workflow.pdf p. 2, section 7", "docs/implementation/MASTER_PLAN.md", "docs/adr/", "docs/developer/architecture.md"]
requirements: ["GOV-01", "GOV-02", "GOV-04"]
---

# Stage 2 design review

> **Draft.** SB-2 asks each stage's review note to say what worked, what did
> not, and what to change. This draft only lists facts recorded in the
> repository. Aadyant, Jeswin and Paul should rewrite the judgements in their
> own words, sign them, and change the status after their review. It is not
> a human review.

## Deliverables and where they are

| Stage 2 deliverable (brief §7) | Evidence |
| --- | --- |
| Architecture and design documentation | [Master plan](../../../docs/implementation/MASTER_PLAN.md) (16 November), [contracts](../../../docs/implementation/CONTRACTS.md), and the as-built [architecture page](../../../docs/developer/architecture.md) |
| Diagrams | A component flowchart, a composed-workflow sequence diagram, and an ER diagram from the real SQLite migrations |
| Decisions | ADR-0001 to ADR-0009 in this stage. ADR-0010 and ADR-0011 came later. |
| `brain-refine` and `brain-query` skills | `.agents/skills/`, evaluated in [brain workflow evidence](../../../docs/evidence/skills/brain-workflows.md) (J2-06, #50) |
| First `local-check` skill | P2-07 ([#43](https://github.com/AadyantNeog/SEproject/pull/43)): build, test, start, fetch and cleanup stages |

## What worked (facts to reflect on)

- **Design choices held.** The modular monolith, the single quota-accounted
  executor, the persistent ledger and the native approval dialog were
  decided early (ADR-0001 to ADR-0005). Later implementation did not
  reverse any of them.
- **Parallel work.** Publishing contracts first (A2-01) let all three
  tracks build against synthetic fixtures in parallel.
- **Early trust-boundary check.** The approval helper was checked against a
  real client (P2-03, ADR-0009) before the write path was built.

## What did not work (facts to reflect on)

- **Fixture-bound handlers.** The handlers were written against
  fixture-specific bindings and providers. Two different fixture channels
  are in use. Live mode later had to be staged (ADR-0011), because one
  injected runtime had not been designed in.
- **Allocation churn.** The allocation was revised twice (16, 19 and 21
  November) before implementation settled.
- **Planning register lag.** The coverage and traceability registers fell
  behind GitHub until the 28 November backfill.

## What to change (for the team to decide)

- Design one provider and account runtime for fixture and live modes from
  the start.
- Keep the registers updated in each PR rather than in batches.

Related: [[2026-11-16-implementation-master-plan]], [[15-implementation-boundaries-and-contracts]].
