# Team lead and owner review policy

Version 2.2 · 21 November 2026 · Team lead: Aadyant Neog · Author: Codex

Aadyant reviews every Jeswin/Paul PR and deliverable. Jeswin and Paul are not assigned to review Aadyant's PRs. His chosen AI model provides automated review assistance, followed by his own actual, recorded human review of the changes. The SRS is frozen as submitted; AI output alone is not human-review evidence.

## Review responsibilities

**Transferred work (v2.3).** Since 28 November 2026, Aadyant authors
J2-07, J2-08, P2-08 and the remaining release work. Those changes follow
the own-work rule below: chosen AI review, then his dated human owner
review of the exact commit. No Jeswin or Paul review is assigned. An owner
review is never described as independent GitHub approval.
[ADR-0010](../adr/0010-solo-completion-ownership-transfer.md)


| Work | Review workflow |
| --- | --- |
| Jeswin's or Paul's PRs/deliverables | Aadyant personally reviews the exact version; authors fix findings and return material changes for re-review |
| Aadyant's PRs/deliverables | His chosen AI reviews the diff; he personally reads/verifies it, resolves findings and records his own human owner-review note; no Jeswin/Paul review assignment |
| Joint work | Disclose authorship. Aadyant reviews teammate portions and performs AI-assisted recorded human owner review of his own portions; do not claim independent review of material he authored |

The workflow covers code, tests/fixtures, contracts/design/ADRs, docs, skills, brain notes, reports/demos and stage/release evidence. Authors retain implementation, integration, fixes and truthful evidence. Aadyant's review role does not transfer their work to him.

## Source requirement and truthful evidence

The submitted SRS GOV-03 requires at least one human review per PR. The supplied `SDLC_and_Workflow.pdf`, page 2, requires a human to review every AI-generated PR change. Neither passage names Jeswin/Paul or explicitly requires a different teammate. The previous mandatory teammate/non-author assignment was a design choice and is removed. This plan records Aadyant's actual manual owner review as such; it does not invent instructor acceptance of a particular evidence format.

AI findings must remain labelled AI-generated. A human review record names the person, exact commit or artefact version, checks actually performed, findings/resolutions, decision, date and evidence link. Do not generate a completed review record before Aadyant actually performs it. After material changes, rerun relevant AI/checks and repeat the manual review.

Owner review is not independent GitHub approval: GitHub does not let a PR author approve their own PR. Existing repository protection/approval requirements remain in force; do not bypass them, fabricate another reviewer or change remote settings as part of this edit. [GitHub review documentation](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request).

## Handoff and acceptance

1. Authors commit coherent increments, run relevant checks and provide task/requirement/Issue/PR links, the exact version, actual results and open issues.
2. Jeswin/Paul submit their work to Aadyant. He records the actual decision; they fix findings and request re-review of materially changed work.
3. For Aadyant's own work, his AI produces findings; he personally evaluates them, inspects/verifies the change and records human owner-review evidence. A better AI model is not itself a human reviewer.
4. Acceptance requires the appropriate actual human review, relevant checks and any applicable existing repository protections. No AI/CI flag, silence, local commit or generated note is treated as human approval.

Agents may prepare review reports and handoff drafts, but cannot impersonate reviewers or publish messages/approvals without authority. Engineering review does not grant OAuth access or approve a learner's playlist; FR-5's trusted exact-proposal human interaction is unchanged.

## Implementation and workload

The 24 A2/J2/P2 tasks, owners, dependencies and 56–80-hour implementation ranges are unchanged. Author verification includes Aadyant's AI-assisted personal checks. His centralized review/coordination of teammate work is additional and separately tracked; equal total workload is not claimed. P2-06 documents the two review modes and verifies any eventual repository enforcement using real accounts without silently disabling existing protections. Actual settings, review decisions and instructor acceptance remain unverified until evidenced.

SRS submission was reported by the user on 21 November as about a week earlier. Exact date and submitted rendition were not specified; do not invent them or edit any SRS source/output. Basis: [source note 19](../../brain/resources/19-owner-ai-assisted-review-and-submitted-srs.md), [engineering workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [ADR-0008](../adr/0008-owner-ai-assisted-review-and-frozen-srs.md), and [tasks.json](tasks.json).
