---
id: "RN-19"
type: "research"
title: "Owner AI assisted review and submitted SRS"
created: "2026-11-21"
author: "Codex"
status: "distilled"
sources: ["User instructions in this chat, 2026-11-21: no Jeswin/Paul review of Aadyant PRs; SRS final and submitted about one week earlier", "SDLC_and_Workflow.pdf p. 2, sections 4 and 6, extracted 2026-11-21", "docs/requirements/SRS.md GOV-03 and GOV-05"]
requirements: ["GOV-01", "GOV-02", "GOV-03", "GOV-05"]
---

# Owner AI assisted review and submitted SRS

## Source facts

The user excluded Jeswin/Paul from reviewing his PRs and prefers his selected AI model for automated review. He also confirmed the SRS was final and submitted about a week before 21 November; exact submission date/rendition were not specified.

The supplied workflow brief page 2 requires a review for each PR and a human review of every AI-generated PR change. SRS GOV-03 requires at least one human review per PR. Neither passage names a particular teammate or explicitly requires a different person. The earlier mandatory teammate/non-author assignment was a planning choice, not the source's wording.

## Current process choice

Keep Aadyant's human review of teammate work. His own PRs use chosen-AI findings plus his actual manual owner review, separately evidenced against the exact commit. Jeswin/Paul are not assigned. AI output is not human review; owner review is not independent GitHub approval. Do not claim instructor acceptance of an evidence format, bypass actual repository protections or fabricate review records.

The SRS topic/requirements and all source/output files remain frozen. Only development instructions and evidence handling change. Implementation IDs/owners/hours/dependencies remain unchanged. Current policy is version 2.2; [[18-team-lead-review-governance]] records the earlier own-work rule and is superseded on that point.

Related: [[12-engineering-and-knowledge-workflow]], [[17-equal-team-allocation]], [[srs-baseline]], [[2026-11-21-own-pr-review-clarification]]. Actual reviews, enforcement, precise submitted-file identity and instructor acceptance: not invented.
