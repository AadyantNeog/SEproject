---
id: "AI-2026-11-16-IMPLEMENTATION-PLAN"
type: "ai-session"
title: "Detailed implementation master plan and team agent instructions"
created: "2026-11-16"
author: "Codex"
status: "recorded"
sources: ["User implementation-plan request in this chat, 2026-11-16", "docs/requirements/SRS.md", "docs/requirements/requirements.json", "docs/implementation/MASTER_PLAN.md", "docs/implementation/CONTRACTS.md", "docs/implementation/TEAM_WORKPLAN.md"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "NFR-01", "NFR-03", "NFR-11", "NFR-12", "SK-01", "GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05"]
---

# Detailed implementation master plan and team agent instructions

Historical record: the allocation and observed checks below describe 16 November 2026. The user replaced that allocation on 19 November; see [[2026-11-19-equal-workload-revision]] and [[17-equal-team-allocation]]. Current planning/QA files contain version 2; this note preserves the original outcome and does not assign current work.

## Goal

Prepare a detailed SRS-based architecture/technology/implementation plan. Give Aadyant most difficult engineering and smaller substantive assignments to Jeswin and Paul. Maintain shared instructions for their separate coding agents, preserving the fixed project requirements and actual authorship.

## Actual outcome

Prepared a linked master plan, shared model/provider/tool/resource/state contracts, dependency/effort/gate-based team workplan, individual agent briefs, a 46-row requirement planning register, five proposed ADRs and expanded root AGENTS.md. Added [[15-implementation-boundaries-and-contracts]] and [[16-official-api-design-check-2026-11-16]], index links and an append-only session log entry.

The proposed stack is Python 3.13, the official MCP SDK, strict typed models, explicit official REST access, SQLite, Google OAuth/protected credentials and native human approval. Core ranking/quota/auth/planning/recovery/integration belongs to Aadyant; Jeswin receives analytics/presentation; Paul receives independent fixtures/CI/skills/documentation. Estimated effort is a planning range, not an accepted team commitment or observed implementation.

## What worked

Reading the full numbered SRS and existing notes exposed constraints that a feature-only breakdown would miss: distinct audio/text language evidence, full composed-workflow quota preflight, durable unknown-write state, human approval outside model arguments and retention without unsafe replay. Official documentation checks informed the dated design; the actual canonical Python interpreter was inspected without installing packages or altering PyTorch.

## What failed or remains uncertain

Two initial official API links using the older `/data/v3/docs/` route were not readable through the web tool; the current `/data/reference/rest/v3/` pages were read instead. An initial large combined tool output was truncated; missing SRS sections and agent/baseline records were reread in smaller chunks. No product run failed because no product implementation or live API calls were attempted.

Initial planning validation caught an incorrect manually added Aadyant effort total and percentage. Recalculated the task rows, corrected the summary to 96–140 hours and about 70%, and reran the document checks. This was a planning arithmetic correction, not a failed implementation test.

Native helper/client trust and compatibility, resolved dependency locks, D-02 policy applicability, credentials/quota configuration, product tests, actual Issues/PRs, human review, member contributions, stage submissions and release remain pending. Planning does not settle those external or implementation dependencies.

## Verification

Planning-only automated checks and their observed outcome are recorded in `docs/implementation/PLAN_QA.md` outside the vault. They compare all 46 source IDs/titles/verification strings with the new planning register, validate task references/ownership/links/frontmatter and confirm protected SRS/PDF files are unchanged from the session-start snapshot. These are document integrity checks, not product acceptance tests or live API evidence.

Final observed result: 16 document checks passed, covering all 46 requirement rows, all 20 acceptance IDs, 20 defined tasks, effort arithmetic, relevant note references, 17 Markdown files' local links/fences, new-note frontmatter and five ADRs' distilled basis. SHA-256 comparison found no changes in the 14 pre-existing requirement/PDF files captured at session start. The proposed diagrams were reviewed as source, not rendered by a diagram tool.

Related: [[srs-baseline]], [[12-engineering-and-knowledge-workflow]], [[13-api-policy-dependency]], [[15-implementation-boundaries-and-contracts]], [[16-official-api-design-check-2026-11-16]]. Actual Issue/PR links: pending. No human authorship, review, submission or release is claimed.
