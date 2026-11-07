---
id: "AI-2026-11-07-SRS"
type: "ai-session"
title: "SRS preparation"
created: "2026-11-07"
author: "Codex"
status: "recorded"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "SDLC_and_Workflow.pdf pp. 1-3"]
requirements: ["GOV-02", "GOV-05", "SK-01"]
---

# SRS preparation

## Goal

Prepare the YouTube project SRS for the first graded submission while maintaining the Second Brain.

## Outcome

Read both source briefs, researched official API/OAuth/quota/MCP/skill references, prepared an SRS with 46 numbered requirements and 20 planned acceptance scenarios, added source-linked research and a brain-ingest skill, and generated a single submission PDF. Team identity was intentionally deferred at the user's request. This is local preparation, not submission or human approval.

## What worked

Preserving FR-1 to FR-5 made scope coverage explicit. Separating collection timestamps from viewing history avoided unsupported analytics claims. Explicit duration, language, approval and partial-write rules made acceptance tests concrete.

## What failed or needs correction

The handout's quota summary alone is insufficient for the current separate search allowance. Current policy introduces a live derived-data dependency that cannot be established as resolved in this session. No product implementation experiments or API calls were performed.

The initial consistency check found two governance requirements without explicit acceptance-scenario IDs; both were linked to AT-20 and all checks were rerun successfully. The skill validator initially lacked PyYAML in the bundled interpreter; the user's existing canonical interpreter completed it without installing packages.

## Verification

The final verification record is `docs/requirements/SRS_QA.md` outside the vault. It covers PDF page inspection, requirement/test consistency, source links, frontmatter and wikilinks. These document checks do not establish passing product tests or complete Stage 1 delivery.

## Related knowledge

[[srs-baseline]]; [[09-quota-buckets-and-budgeting]]; [[13-api-policy-dependency]]; [[requirements-preparation-review]].

Issues and PRs: pending. Human authorship and human review: pending.
