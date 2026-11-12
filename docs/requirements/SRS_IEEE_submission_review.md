# IEEE SRS pre submission review

Date: 9 November 2026. Reviewer: Codex. Scope: review of the current IEEE SRS against the supplied YouTube problem statement, common SDLC requirements and relevant official API documentation. The submission PDF and Word document were not edited by this review.

## Verdict

The document covers every explicitly named core feature, the product skill, common skills, testing requirements and principal API/security constraints. No core feature is missing. Two items need attention before treating the interpretation and live feasibility as fully settled: the metadata-only meaning of video summarisation and the documented live API policy dependency. Their acceptance cannot be established from the supplied assignment alone.

## Assignment coverage

| Supplied requirement | IEEE SRS location | Assessment |
| --- | --- | --- |
| FR-1 ranked similar videos from URL/ID | 4.1; FR-1.1 to FR-1.3 | Covered, including locally computed metadata similarity and missing fields |
| FR-2 ranked similar channels from URL/handle/ID | 4.2; FR-2.1 to FR-2.2 | Covered, including seed resolution and evidence/sample limitations |
| FR-3 recommendations using likes, subscriptions and playlists | 4.3; FR-3.1 to FR-3.3 | Covered, including sparse or denied data |
| FR-4 top channels/categories, duration preferences and period comparisons | 4.4; FR-4.1 to FR-4.3 | Covered using accessible collection data and supported event timestamps; watch history is not claimed |
| FR-5 natural-language topic/time/item-length/language constraints, preview, confirmation, creation | 4.5; FR-5.1 to FR-5.7 | Covered, including rejected approval, partial writes and duplicate prevention |
| video-to-playlist workflow | 6.1; SK-05 | All five workflow steps appear; the summary input is explicitly restricted to title/description metadata, as discussed below |
| Unit/integration/MCP system tests and negative cases | 6.3; AT catalogue and TQ-1 to TQ-4 | Covered |
| Mock/fixture CI and separately budgeted scheduled live tests | 6.3; TQ-5 | Covered as required future evidence, not claimed execution |
| Cost per request and rejection before any over-budget workflow calls | FR-7; NFR-12; AT-13; TQ-6 | Covered |
| OAuth, secrets, input validation, prompt injection and personal-data testing | 5.3 and AT-10 to AT-16 | Covered |
| Official API only, no scraping, caching, no extra-project quota evasion | 1.4, 2.5, FR-7 and NFR-12 | Covered |
| OAuth re-authorisation and missing YouTube channel | FR-6; AT-11 | Covered |
| FR/NFR/SK, PARA, skills, ADRs, traceability, reviewed PRs and contribution evidence | 6.1 to 6.3; GOV-01 to GOV-05 | Covered as engineering obligations |
| IEEE template outline and team identification | Cover, contents, sections 1 to 6 and appendices A to C | Covered; roster matches the user's supplied names and roll numbers |

## Findings requiring interpretation

### R1 Video summary scope

The project brief says the product skill shall summarise a given video. SK-05 instead commits to summarising available title/description metadata and explicitly disclaims full-content/transcript access. That is a technically honest, narrower interpretation. The official captions.download method requires the user to have permission to edit the video, so the official Data API does not provide an unrestricted transcript-download route for arbitrary third-party videos. It is not possible to conclude from the brief alone that the teaching assistants accept a metadata-only summary.

Recommended clarification before freezing: ask whether a clearly labelled summary based on official API title/description metadata satisfies the video-to-playlist summary step. Do not resolve this by silently promising unavailable transcripts or using prohibited scraping. If a full-content summary is required, an allowed evidence/source mechanism needs an explicit course decision.

### R2 Live policy dependency

D-02 and Appendix C TBD-01 are genuinely unresolved. The assignment requires metadata similarity and aggregation, whereas the official policy contains restrictions on derived data/metrics and aggregation. The SRS correctly records the issue; it does not demonstrate that affected live processing is permitted. Confirm the course's intended compliant live-demo approach with the teaching assistants, and record the interpretation. This is an unresolved live feasibility dependency, not proof that the SRS format is invalid or that all similarities are categorically prohibited in every context.

## Explicit project commitments to understand

The source brief does not supply these exact bounds; the SRS makes them explicit project choices: total duration is an upper bound rather than an exact-fill guarantee, proposals contain 1 to 50 items, the default candidate pool is 200, approval expires within 10 minutes, and local offline performance has specified timing targets. These are reasonable testable choices but become commitments when the SRS is submitted. Exact-fill requests are clarified or rejected; constraints are not silently relaxed.

The supported client/version and implementation versions remain design selections in Appendix C. The mandatory behaviour is already specified, so those items do not by themselves omit a required feature. The course materials do not establish a ban on leaving implementation selections to the design stage.

## Technical and document verification

- Compared all 46 requirement IDs, titles, full statements and verification strings against the current Word document.
- Confirmed all 20 acceptance scenarios and TQ-1 through TQ-8 in the PDF.
- Verified all 43 contents entries point to the actual PDF page containing their heading; the document remains 27 pages with three template sections and two diagrams.
- Checked for remaining generic placeholders and Word field errors; none found.
- Confirmed Random Stuff, Aadyant Neog BT2024186, Jeswin Jose BT2024142 and Paul T Mathew BT2024135 against the cover.
- Reconfirmed the official separate search allowance/general quota profile, OAuth Testing-mode expiry, authorised like retrieval and playlist-addition timestamp semantics. No conflicting API fact was found in those checks.
- Current IEEE PDF SHA-256: `20b02918d5f51897a9989ced432d14e6869e0938a362e78566874b969929b1a1`.
- Previous SRS PDF SHA-256 remains `dcce9dafd873cdc0db34c7d4211d9d6e4e3852c776a1f116ec2c39b66c21dc20`.

These document checks are not product test results, human approval or a guarantee of grading outcomes.

## Sources

- `Project_1_YouTube_MCP.pdf`, pages 1-2.
- `SDLC_and_Workflow.pdf`, pages 1-3.
- Current IEEE Word/PDF and existing requirement register.
- https://developers.google.com/youtube/data/reference/rest/v3/captions/download, checked 9 November 2026.
- https://developers.google.com/youtube/terms/developer-policies, especially III.E.2 and III.E.4.8, checked 9 November 2026.
- https://developers.google.com/youtube/data/determine_quota_cost, checked 9 November 2026.
- https://developers.google.com/identity/protocols/oauth2, checked 9 November 2026.
- https://developers.google.com/youtube/data/reference/rest/v3/videos/list, checked 9 November 2026.
- https://developers.google.com/youtube/data/reference/rest/v3/playlistItems, checked 9 November 2026.
