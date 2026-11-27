---
name: brain-query
description: Answer project questions or draft grounded documents from Second Brain notes and ADRs, citing supporting notes and disclosing missing or conflicting evidence.
metadata:
  version: "0.1.0"
---

# Brain query

Retrieve and synthesise grounded answers or document drafts strictly from the repository's Second Brain (`brain/`), ADRs (`docs/adr/`), and requirement traceability registers.

## Invocation conditions

Use this skill when:
- Answering a requirement-to-decision, architecture, governance, or status question about the project.
- Drafting a summary, handoff, or stage document that must be backed by existing distilled notes and verified session records.

Do not use this skill to speculate beyond recorded evidence or to claim unverified tests, approvals, or live runs.

## Inputs

- A project question or drafting brief (for example, tracing a requirement ID such as `FR-5.5` or `FR-4.2` to its distilled research, ADR, and current verification status).

## Workflow

1. Read `brain/index.md` to locate relevant distilled notes in `brain/resources/` and active records in `brain/projects/youtube-mcp/`.
2. For requirement or governance questions, check `docs/requirements/traceability.csv`, `docs/implementation/coverage.csv`, and relevant ADRs in `docs/adr/` so the answer follows the actual requirement -> distilled note -> ADR -> implementation/test chain.
3. Verify each claim directly against the source note text and check note `status` (`distilled`, `recorded`, `pending-review`) and dates (respecting chronological amendments such as plan v2.2 superseding earlier allocations).
4. Draft the answer or document with explicit citations (`[[note-stem]]` and repository-relative paths/ADR IDs) for every factual claim.
5. Add a dedicated **Missing or conflicting evidence** section whenever any part of the question is unsupported, pending human review/live credentials, or contradicted across notes.

## Output

- A concise, grounded answer or draft where every claim cites its supporting `[[note-stem]]` / ADR / register entry.
- An explicit disclosure of any gaps, pending links, unresolved dependencies (such as D-02), or conflicting records.

## Failure and boundary behaviour

- If the vault and repository contain no evidence supporting a question or claim, state clearly that it is unsupported or not in scope; do not invent decisions, approvals, test results, or sources.
- Never treat a `pending-review` AI session note or planned test path as passed acceptance or human approval.
- Never expose credentials or private account data in query outputs.

Distilled basis: [[12-engineering-and-knowledge-workflow]] and [[11-mcp-and-agent-skill-contracts]].
