# ADR-0008: Owner AI assisted review and frozen SRS

Date: 21 November 2026 · Author: Codex · Status: user-directed workflow; actual review evidence pending

## Context and source

The user excluded Jeswin/Paul from review of his PRs, prefers his chosen AI reviewer and confirmed the SRS was final/submitted about a week earlier. The exact submission date/rendition was not supplied. SRS GOV-03 and the workflow brief page 2 require human review, but do not explicitly prescribe those teammates or a different reviewer. The named-peer rule in ADR-0007 was an added design choice and is removed.

Distilled basis: [source note 19](../../brain/resources/19-owner-ai-assisted-review-and-submitted-srs.md), [engineering workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [lead review governance](../../brain/resources/18-team-lead-review-governance.md).

## Decision

Aadyant reviews every teammate PR/deliverable. For his own work, his chosen AI provides review findings and he personally reads/verifies the changes and records the human owner-review step. No Jeswin/Paul review assignment is made. Material revisions receive renewed checks and human review. AI output alone is never human-review evidence, and owner verification is never labelled independent GitHub approval. Existing repository protections remain in force; no settings are bypassed or changed by this local planning revision.

Preserve the final SRS and all existing source/output files. Do not silently remove its human-review commitment or infer instructor acceptance of a particular owner-review record. The 24 A2/J2/P2 implementation tasks, owners, effort ranges and dependencies stay unchanged. Centralized teammate review remains additional lead work; own AI-assisted manual verification remains author work.

## Consequences and verification

Version 2.2 supersedes only earlier named-peer/non-author requirements for Aadyant's work. Actual review records must distinguish AI findings, owner manual checks and formal external approval. Course acceptance, real repository enforcement and completed reviews require evidence and are not generated claims. Verify the review matrix, no teammate assignments to Aadyant, retained human verification, requirement coverage and protected SRS hashes. [Review policy](../implementation/REVIEW_POLICY.md), [planning QA](../implementation/PLAN_QA.md). Actual Issue/PR/review links: pending.
