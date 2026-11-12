---
id: "PROJECT-SRS"
type: "decision"
title: "YouTube SRS baseline"
created: "2026-11-07"
author: "Codex"
status: "pending-review"
sources: ["Project_1_YouTube_MCP.pdf pp. 1-2", "SDLC_and_Workflow.pdf pp. 1-3"]
requirements: ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "GOV-05"]
---

# YouTube SRS baseline

The user selected YouTube and requested the first graded SRS. Team details were initially deferred and subsequently supplied by the user on 7 November 2026. Submission is one document per team, and the topic and SRS cannot be edited afterwards.

## Team roster

Team name: Random Stuff.

| Member | Roll number |
| --- | --- |
| Aadyant Neog | BT2024186 |
| Jeswin Jose | BT2024142 |
| Paul T Mathew | BT2024135 |

Source: the user's team-details message in this chat, 7 November 2026. These details are included on the SRS cover; listing a member does not claim that the member authored or reviewed this AI-generated document.

## Local artefacts

- Editable source: `docs/requirements/SRS.md` outside the vault.
- Submission candidate: `output/pdf/YouTube_Video_Intelligence_SRS.pdf` outside the vault.
- Traceability register: `docs/requirements/traceability.csv` outside the vault.
- Rebuild source: `scripts/build_srs.py` outside the vault.

## Additional template rendition

On 9 November 2026 the user supplied the teaching assistants' IEEE-style SRS template and requested a separate document alongside the previous version. The new outputs are `output/docx/YouTube_Video_Intelligence_SRS_IEEE.docx` and `output/pdf/YouTube_Video_Intelligence_SRS_IEEE.pdf` outside the vault. All 46 existing requirement statements and verification strings are unchanged. The original PDF remains unchanged. The adaptation is documented in [[2026-11-09-ieee-template-adaptation]] and [[14-ieee-srs-template-structure]].

## Compact template rendition

On 12 November 2026 the user requested a 15-20 page SRS. Prepared a separate 18-page compact IEEE rendition at `output/docx/YouTube_Video_Intelligence_SRS_IEEE_Compact.docx` and `output/pdf/YouTube_Video_Intelligence_SRS_IEEE_Compact.pdf` outside the vault. All 46 numbered statements and verification strings remain exact; the existing files are unchanged. The existing full IEEE PDF is currently named `output/pdf/RandomStuff_SRSsubmission.pdf`. This is a presentation revision, not a scope change or evidence of submission. See [[2026-11-12-srs-condensation]] for the actual checks and remaining work.

## Preserved scope choices

Preserve all five core features. Use a local stdio MCP server with one documented client. Interpret duration as an upper limit and require verifiable language evidence. Summarise video metadata honestly. Use a trusted proposal-specific approval interaction and preserve partial-write state. These are proposed requirements, not implemented behaviour.

## Summary scope agreement

On 9 November 2026, after the pre-submission review, the user accepted the current metadata-based summary interpretation as sufficient for the SRS and deferred further investigation to coding. Keep SK-05's stated evidence basis: summarise available title/description metadata honestly. Implementation details and richer permitted evidence sources can be investigated during development, within the submitted requirements and official-API-only constraint. This is the user's scope decision, not a claim of teaching-assistant approval. The existing SRS files remain unchanged.

Related review: [[2026-11-09-srs-submission-review]].

## Remaining dependencies and pending work

Resolve D-02 for affected live derived processing. Complete repository/CI setup and team review separately. Add actual issue/PR links when available. No submission, review or release is claimed.

Basis: [[01-project-problem-and-scope]], [[04-duration-and-language-constraints]], [[06-preview-and-human-approval]], [[09-quota-buckets-and-budgeting]], [[13-api-policy-dependency]].
