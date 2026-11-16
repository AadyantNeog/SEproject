---
id: "RN-15"
type: "research"
title: "Implementation boundaries and team contracts"
created: "2026-11-16"
author: "Codex"
status: "distilled"
sources: ["docs/requirements/SRS.md sections 2-11 and 13-15", "User implementation-plan and team-allocation request in this chat, 2026-11-16"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "NFR-03", "NFR-11", "GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05"]
---

# Implementation boundaries and team contracts

## Finding

The fixed SRS couples difficult cross-cutting concerns: authenticated provider calls, bounded workflow quota, immutable account-bound proposals, trusted human approval, partial remote writes and account-data retention. These need a coherent application boundary; independent agents must not implement different approval or quota rules.

The user requested a detailed master implementation plan, Aadyant's ownership of the bulk of difficult work, smaller substantive assignments for Jeswin and Paul, and shared AGENTS.md instructions for their own coding agents. This is an allocation preference, not evidence that teammates accepted, authored or completed work.

## Project choices

Propose a Python local modular monolith with strict contracts and fixture/live providers. Assign core algorithms/security/integration to Aadyant, pure snapshot-based analytics/presentation to Jeswin, and independent synthetic fixtures/CI/skills/documentation to Paul. Freeze merged contracts before consumer implementation. Keep actual human authorship, reviews and demonstrations attributable.

Keep operation intent/IDs durable while API payloads expire under the SRS retention rules; deleting old details must not turn replay into a new create. A native human approval path needs an early Windows/client proof and an honest local OS trust boundary. Full designs/estimates are in `docs/implementation/` outside the vault and ADRs are in `docs/adr/`; all remain local proposals awaiting human review.

## Sources and links

- Repository SRS sections 2–11, 13–15, read 16 November 2026. This note distils requirements and project decisions; it does not introduce an instructor-approved scope change.
- User request in this chat, 16 November 2026.
- [[06-preview-and-human-approval]], [[07-playlist-writes-and-partial-failure]], [[09-quota-buckets-and-budgeting]], [[12-engineering-and-knowledge-workflow]], [[13-api-policy-dependency]].

Issues/PRs and implementation tests: pending. No team-member contribution, live permission or release is claimed.
