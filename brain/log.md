# Brain run log

## 2026-11-07 SRS preparation

- Workflow: repository brain-ingest skill; performed by Codex.
- Inputs: both supplied PDFs and official technical references accessed on this date.
- Output: 13 distinct distilled research notes, project baseline note, significant AI-session note, requirements-preparation review, index, schema and PARA vault structure.
- Requirement links: FR-1 to FR-8, NFR, SK and GOV families in the SRS and traceability register.
- Result: local records prepared; review and submission pending. No human contribution or GitHub approval is fabricated.

Subsequent operations must append their actual outcome here.

## 2026-11-07 SRS verification

- Result: 17 rendered PDF pages visually checked, 46 requirements and matching traceability rows checked, 20 acceptance scenarios and 12 references confirmed, and 57 wikilinks resolved.
- The brain-ingest skill passed its frontmatter/name validator using the existing canonical interpreter after the bundled interpreter lacked PyYAML. No environment or package installation was performed.
- Recorded document QA in `docs/requirements/SRS_QA.md` outside the vault. Product tests, human review, GitHub changes and submission remain pending.

## 2026-11-07 Team details added

- Input: the user supplied team name Random Stuff and member/roll pairs Aadyant Neog (BT2024186), Jeswin Jose (BT2024142), and Paul T Mathew (BT2024135).
- Updated the SRS cover, PDF author metadata, editable source and current project roster in [[srs-baseline]].
- Regenerated and rendered the 17-page PDF. Verified every name/roll mapping and visually checked the revised cover. Pages 2-17 are textually and visually unchanged; all 46 requirements are unchanged.
- This administrative update does not constitute human review, contribution evidence, GitHub publication or submission.

## 2026-11-09 IEEE template adaptation

- Input: user-supplied `srs_template-ieee.doc` and the instruction to retain the previous SRS.
- Workflow: inspected the template, preserved its layout/outline, mapped all 46 exact requirements, refreshed Word fields and exported a separate Word/PDF rendition.
- Output: 27-page IEEE-style SRS, editable content, 46-row placement map, retained template copies, provenance and QA records; see [[2026-11-09-ieee-template-adaptation]] and [[14-ieee-srs-template-structure]].
- Verification: all 43 contents entries matched their pages; all 46 statements and verification strings retained; final pages visually reviewed; original template and previous PDF hashes unchanged.
- Result: local preparation complete. Live-policy applicability, human review, issues/PR workflow, implementation and submission remain pending.

## 2026-11-09 SRS pre submission review

- Compared the IEEE document with both original briefs and checked official quota, OAuth, metadata, captions and policy references.
- Confirmed core feature/skill/test coverage, all 46 statements and 43 contents references. Recorded the detailed result in `docs/requirements/SRS_IEEE_submission_review.md` outside the vault and [[2026-11-09-srs-submission-review]].
- Flagged the unconfirmed metadata-only video-summary interpretation and the existing live-policy dependency. Did not invent teaching-assistant acceptance or treat document verification as product test execution.
- The IEEE Word/PDF and previous SRS PDF were not edited. Submission and human approval are not claimed.

## 2026-11-09 Summary scope accepted by user

- The user accepted the current metadata-based video-summary interpretation for the SRS and deferred implementation investigation to coding.
- Recorded the agreement in [[srs-baseline]]. This does not establish TA approval or resolve the separate API policy dependency.
- No requirement text or submission document was changed.

## 2026-11-12 IEEE SRS condensation

- Input: user requested a 15-20 page SRS; prior instruction to retain previous versions remains applicable.
- Output: separate 18-page compact IEEE Word/PDF, condensation/export scripts, document QA and source-file preservation hashes. See [[2026-11-12-srs-condensation]].
- Verification: all 46 exact numbered requirements and verification strings, all 43 contents references, 20 acceptance cases, TQ-1 to TQ-8, two figures, supplied team details and all final page layouts checked. Three existing deliverable hashes remain unchanged.
- Rendering: packaged renderer lacked LibreOffice; native Word exported the final DOCX and bundled Poppler rendered it for review. No dependency installation was needed.
- Result: local presentation revision complete. No product tests, human review, GitHub changes or submission are claimed.

## 2026-11-16 Implementation master plan and agent instructions

- Input: user requested a detailed SRS-based architecture/technology/team implementation plan, with Aadyant owning the bulk of difficult work and smaller substantive contributions for Jeswin/Paul using their own coding agents.
- Read the full SRS, baseline/brain/skill records and requirement register; checked official MCP, YouTube, OAuth, keyring and chosen-client references. Inspected canonical CPython 3.13.1 without installs or PyTorch changes.
- Prepared `docs/implementation/` master plan, contracts, team task/dependency/gate schedule, three role briefs, exact 46-row coverage register and planning QA report; expanded root AGENTS.md; added five proposed ADRs and [[15-implementation-boundaries-and-contracts]] / [[16-official-api-design-check-2026-11-16]]. Session: [[2026-11-16-implementation-master-plan]].
- Verification: final 16 planning integrity checks passed. Corrected a manual effort-total mismatch found by the first check run; final allocation is Aadyant 96–140 hours, Jeswin 20–28, Paul 22–30, about 70% for Aadyant at midpoint. All 46 IDs/titles/verification strings, AT-01–AT-20, defined task/note/link references, note authorship and ADR distilled citations checked. Fourteen pre-existing requirement/PDF files retained their session-start SHA-256 hashes; existing user PDF edits/deletion/untracked file were left as found.
- Result: local planning complete. No product implementation/tests, live API calls, environment installation, GitHub mutation, team-member authorship, human review, instructor permission, submission or release is claimed. Native approval/client proof, D-02 resolution, dependency locks and actual delivery evidence remain pending.

## 2026-11-19 Equal workload revision

- Input: user replaced the earlier unequal allocation with an equal split and requested that all affected documents be revised.
- Inspected the clean main checkout and current SRS/brain/plans; isolated changes on `codex/equal-team-plan`. No product package existed in the inspected checkout; no uninspected remote implementation or member contribution was reassigned.
- Prepared version 2 master plan/contracts/team workplan/three role briefs/AGENTS.md and updated all 46 coverage rows. Added 24 current A2/J2/P2 tasks, retired-task mapping, ADR-0006 and [[17-equal-team-allocation]]. Updated previous ADR references and appended supersession notices to historical notes without rewriting the original outcome. Session: [[2026-11-19-equal-workload-revision]].
- Allocation: eight tasks and 56–80 planned hours each. Aadyant owns ranking/recommendations/planning/MCP/presentation; Jeswin owns HTTP/provider/OAuth/library/analytics/privacy; Paul owns storage/quota/approval/writes/recovery/CI. Each supplies own fixtures/tests/docs/handler integration/reviews/evidence; actual-effort checkpoints allow explicit rebalancing.
- Verification: all 26 planning checks passed; all 24 tasks and prerequisites, equal estimate arithmetic, 46 exact requirements, AT-01–AT-20, current ownership/roles, migration, links/frontmatter/citations and regular-commit rules checked. All 18 protected SRS/source/output files retained their pre-edit hashes. Initial role-language check was clarified and rerun; no product test or diagram-rendering result is implied.
- Result: local allocation revision prepared. No dependency installation, PyTorch change, fresh upstream research, live API request, actual CI/product acceptance, human member acceptance/authorship/review, remote PR, instructor permission, submission or release is claimed. Earlier 16 November log/session records remain historical; use version 2 for new work.

## 2026-11-21 Team lead review governance

- Input: user identified Aadyant as team lead and instructed that he review every teammate PR and deliverable.
- Prepared plan/governance version 2.1: REVIEW_POLICY.md, machine-readable author/reviewer matrix and all 24 task review gates, root AGENTS, master/contracts/workplan, role briefs/prompts, coverage review gates and affected ADR references. Added ADR-0007 and [[18-team-lead-review-governance]]; session [[2026-11-21-team-lead-review-update]]. Historical allocation/session outcomes retain chronological amendment notices.
- Review rule: Aadyant personally reviews every Jeswin/Paul PR and artefact; authors fix feedback and request re-review of material changes. His authored/materially coauthored work receives eligible independent non-author review. AI/CI/technical input never fabricates or replaces actual human approval. Module owners retain their implementation/integration/fixes.
- Preserved eight implementation tasks and 56–80 engineering hours each; centralized lead review/coordination and independent PR review are additional and tracked separately. No equal-total-workload claim remains. Existing A2/J2/P2 IDs/owners/hour ranges/dependencies were asserted unchanged during the edit.
- Verified official GitHub review/code-owner documentation on 21 November; actual account identities/settings/enforcement were not inspected or changed. API/SDK research remains dated 16 November. No environment installation or PyTorch change occurred.
- Verification: 33 planning checks passed, including required-reviewer matrix, coauthor/version/scope/effort rules, all 46 coverage gates, 24 tasks and 20 acceptance IDs, links/frontmatter/citations and regular commits. All 18 protected SRS/source/output files retained their hashes. No product/live/actual CI test, PR review, remote configuration, submission or release is claimed. Local preparation is on the existing planning branch; real review links remain pending.

## 2026-11-21 Own PR review and submitted SRS clarification

- Input: user excluded Jeswin/Paul from reviewing his PRs, asked whether human review was mandatory, and confirmed the SRS was final/submitted about one week earlier. Exact submission date/rendition were not supplied.
- Checked `SDLC_and_Workflow.pdf` page 2 and SRS GOV-03: human review is explicit, but the passages do not name those teammates or explicitly require a different reviewer. Removed the agent-added named-peer requirement rather than treating it as course wording. No SRS source/output was edited.
- Prepared version 2.2 policy/AGENTS/role/task/coverage amendments, ADR-0008 and [[19-owner-ai-assisted-review-and-submitted-srs]]. Aadyant reviews teammate work; his chosen AI provides findings for his own work, then he personally verifies and records actual human owner review. AI output is not human review and owner review is not independent GitHub approval. Existing repository protections remain; no remote settings changed.
- Preserved all implementation task IDs/owners/hour ranges/dependencies and regular commits. Recorded user-reported submission in [[srs-baseline]] without inventing a date/rendition/grade. Prior review-policy records remain historical with clarification notices. Session: [[2026-11-21-own-pr-review-clarification]].
- Verification: all 34 planning checks passed; all 18 protected SRS/source/output files match their hashes. Guarded text-replacement/equal-share-label issues were corrected before final validation. No product test, actual CI/PR/human approval, instructor acceptance or live request was performed; no dependency/PyTorch change occurred. Actual review evidence and later-stage release remain pending.

## 2026-11-21 A2-01 foundation

- Started [issue #1](https://github.com/AadyantNeog/SEproject/issues/1) on `codex/a2-01-foundation` from the v2.2 plan. Added the fixture MCP bootstrap, shared DTOs and infrastructure interfaces with synthetic examples. See [[2026-11-21-a2-01-foundation]].
- Verified 19 offline tests, including the MCP 2.3.0 stdio handshake, tool calls and resource reads. The locked wheel passed a clean Windows install and console-entry-point smoke. The planning validator passed 34 checks. Published [draft PR #2](https://github.com/AadyantNeog/SEproject/pull/2). Owner input and human review are pending.

## 2026-11-26 P2-01 SQLite storage

- Implemented versioned SQLite migrations and account-bound snapshot/proposal/cache/operation repositories on `codex/p2-01-sqlite-storage`; added restart, expiry, isolation, deletion and replay tests plus an implementation handoff. Aadyant requested changes on commit `852bd6f`; the fixture loader now uses JSON-mode validation, and regressions cover multiprocess startup, open-reader cleanup, stale completed-operation updates, and superseding an approved proposal. Session: [[2026-11-26-p2-01-storage]].
- Initial P2-01 checks under isolated WSL Python 3.13.18 passed 26 offline tests, scoped Ruff lint/format and mypy on 18 files. After merge commit `9589ada` (latest `origin/main` at `c8f5a3b`), the full offline suite passed 70 tests; scoped P2-01 Ruff lint/format passed; mypy passed on 35 source files. The last repository-wide Ruff run before this merge reported 182 findings; no unrelated files were changed.
- Follow-up commit `859c508` (Paul's Git identity) updated the existing draft PR after Aadyant's requested changes. Aadyant checked [commit `cded9fc`](https://github.com/AadyantNeog/SEproject/commit/cded9fca077c5ed06235d2b3d4de1ede18e5642c) and confirmed all first-review cases pass. Merged `origin/main` at `c8f5a3b` in `9589ada`, preserving the P2-01 and A2 brain index/log entries. Review of the merged branch result remains pending; no new approval is inferred. Issue/PR URLs are pending inclusion in this local traceability note. No live API/OAuth/write data was used.

## 2026-11-26 A2-06 presentation

- Implemented fixture-tested creation and recovery previews, ranked results, report sections and typed errors for [issue #6](https://github.com/AadyantNeog/SEproject/issues/6). The handoff shows how to render fixture previews for the native-dialog proof. See [[2026-11-26-a2-06-presentation]].
- Passed 28 offline tests, scoped Ruff lint and formatting, strict mypy and the wheel build on Windows. Published [draft PR #7](https://github.com/AadyantNeog/SEproject/pull/7). The real report adapter, handler routing, native dialog and human review remain pending.

## 2026-11-26 A2-05 early fixture shell

- Added the checkout-backed synthetic preview and canonical skill resources and the Claude Code skill sync command for [issue #8](https://github.com/AadyantNeog/SEproject/issues/8). See [[2026-11-26-a2-05-fixture-shell]].
- Claude Code 2.1.143 connected over stdio in an isolated Windows profile. Passed 31 offline tests, scoped Ruff, strict mypy and the locked wheel build. Published [draft PR #9](https://github.com/AadyantNeog/SEproject/pull/9). Product integration, trusted native approval proof and human owner review remain pending.

## 2026-11-26 A2-02 ranking and discovery

- Implemented bounded video and channel discovery and deterministic TF-IDF ranking for [issue #10](https://github.com/AadyantNeog/SEproject/issues/10). Verified exact scoring, stable ties and fixed upload sampling using synthetic contracts. See [[2026-11-26-a2-02-ranking]].
- Passed 42 offline tests, scoped Ruff lint and formatting, strict mypy and the locked wheel build. Published [draft PR #11](https://github.com/AadyantNeog/SEproject/pull/11). Real provider, reservation, handler integration and human owner review remain pending.

## 2026-11-26 A2-04 strict playlist planning

- Added strict playlist request validation, exact-second packing, metadata evidence gates and versioned proposals for [issue #12](https://github.com/AadyantNeog/SEproject/issues/12). Verified the 6,420-second SRS example. See [[2026-11-26-a2-04-playlist-planning]].
- Passed 56 offline tests, scoped Ruff, strict mypy, the locked wheel build and 34 planning checks. Published [draft PR #13](https://github.com/AadyantNeog/SEproject/pull/13). Production integration and human owner review remain pending.

## 2026-11-26 A2-03 recommendations

- Added the fixture preference profile, shared-space ranker, optional filters and source coverage for [issue #14](https://github.com/AadyantNeog/SEproject/issues/14). See [[2026-11-26-a2-03-recommendations]].
- Passed 63 offline tests, scoped Ruff, strict mypy, the locked wheel build and 34 planning checks. Published [draft PR #15](https://github.com/AadyantNeog/SEproject/pull/15). Real library and provider integration, quota, MCP routing and human owner review remain pending.

## 2026-11-26 P2-03 native approval

- Implemented challenge-bound helper responses and process-local, exact-binding, one-use grants on `codex/p2-03-native-approval`; added close/reject/expiry/forgery/helper-failure tests and handoff/evidence docs. See [[2026-11-26-p2-03-approval]].
- Focused Python 3.13.18 WSL checks passed: 13 tests across approval and fixture stdio; the final full offline suite passed 81 tests. Scoped Ruff lint/format and mypy on 40 source files passed. Repository Ruff reports 179 existing lint findings and six unrelated format failures; unrelated files were not changed. The first focused run found two issues that were fixed before the passing run.
- Windows Claude Code proof is pending because this environment has no Windows Python 3.13 or `claude` command. No confirmation control was clicked. Issue [#16](https://github.com/AadyantNeog/SEproject/issues/16) and draft [PR #17](https://github.com/AadyantNeog/SEproject/pull/17) were created under Paul's GitHub account; Aadyant's human review is pending.
- For the PR review follow-up, added a SQLite recheck after the native decision and a regression test that saves a revision while the helper waits. The offline suite passed 83 tests. Both dismissal callbacks returned rejection in offline tests. The Windows fixture runbook records the launch command and the two manual observations still needed.
- Added a current-proposal check when consuming an issued grant. The SQLite regression reproduced stale grant acceptance before the fix. All 84 offline tests passed after the fix on Windows Python 3.13.0. Tk 8.6 is available for Paul's manual dismissal checks. Claude Code integration remains pending for a teammate with access.
- Paul manually checked both window close and Reject from Windows PowerShell with the Tcl/Tk library paths set. Both runs reported no grant issued and returned exit code 0. Claude Code integration remains pending.

## 2026-11-26 J2-01 input parsing and accounted HTTP executor

- Implemented pure domain parsers (`identifiers.py`, `durations.py`, `language.py`) and the allowlisted, deadline-bound, quota-accounted HTTPS executor (`http.py`, `redaction.py`) on `codex/j2-01-http-parsing` from `origin/main` (`dec5d7f`). See [[2026-11-26-j2-01-http-parsing]].
- Verified 138 J2-01 synthetic tests (fake `QuotaLedger`, `httpx.MockTransport`), 208 total offline tests (`pytest -m "not live"`), strict `mypy src` (40 source files), and scoped Ruff lint/format checks on all 10 J2-01 files. Published [issue #18](https://github.com/AadyantNeog/SEproject/issues/18) and [draft PR #19](https://github.com/AadyantNeog/SEproject/pull/19). Real P2-02 quota ledger integration, J2-02/J2-03/P2-04 wiring, and Aadyant's lead review remain pending.
- For Aadyant's review follow-up on PR #19, added pre-dispatch deadline rechecks after async auth/debit, froze canonical approved write params/body bytes with wire-digest verification, and mapped unclear write outcomes (5xx, redirects, malformed/non-object 2xx JSON, timeouts, network errors) to `OPERATION_UNKNOWN` for reconciliation (`9333c40`), then merged `origin/main` (`b26737d`) in `54d6b24` preserving both P2-03 and J2-01 log/index entries. Verified 140 J2-01 tests, 224 total offline tests, strict `mypy src` (45 source files), and scoped Ruff lint/format on all 10 J2-01 files. Re-review by Aadyant remains pending.

## 2026-11-26 J2-02 official read provider and fixture engine

- Implemented `LiveYouTubeReadProvider`, `LiveYouTubeProvider`, shared API-JSON normalizers (`src/yt_intel/providers/youtube.py`), and `FixtureYouTubeProvider` (`src/yt_intel/providers/fixture.py`) with API-shaped fixtures (`tests/fixtures/youtube_reads/catalog.json`) and contract/DiscoveryService integration tests (`tests/integration/test_provider_contract.py`) for [issue #21](https://github.com/AadyantNeog/SEproject/issues/21) on `codex/j2-02-read-provider`. See [[2026-11-26-j2-02-read-provider]].
- Verified J2-02 contract tests (5 passed), full offline pytest suite (234 passed), strict `mypy src` (48 source files), and scoped Ruff lint/format checks. Published [draft PR #23](https://github.com/AadyantNeog/SEproject/pull/23). Real P2-02 quota ledger integration, P2-04 write adapters, and Aadyant's lead review remain pending.
- For Aadyant's review follow-up on PR #23, removed `maxResults` from ID-batch lookups, made the live provider reject `mode="fixture"` requests before debit/dispatch, made unsupported fixture writes fail clearly (`PROVIDER_UNAVAILABLE` / HTTP 501), and rejected malformed API responses (`items`/`nextPageToken`/`pageInfo`) with `PROVIDER_UNAVAILABLE`. Re-verified 11 J2-02 contract tests, 240 total offline tests, strict `mypy src` (48 source files), and scoped Ruff checks. Re-review by Aadyant remains pending.

## 2026-11-26 J2-03 OAuth, protected secrets, and account lifecycle

- Implemented `src/yt_intel/auth/{vault,oauth,account}.py`, `docs/user/privacy.md`, `tests/security/test_account_isolation.py`, and `tests/integration/test_oauth_lifecycle.py` on `codex/j2-03-oauth-account` from `origin/main` (`4c94c49`). See [[2026-11-26-j2-03-oauth-account]].
- Verified 13 J2-03 security/integration tests (including real P2-01 `SqliteAccountDataRepository` disconnect), 258 total offline tests (`pytest -m "not live"`), strict `mypy src` (53 source files), and scoped Ruff lint/format checks. Published [issue #28](https://github.com/AadyantNeog/SEproject/issues/28) and [draft PR #29](https://github.com/AadyantNeog/SEproject/pull/29); Aadyant's lead review remains pending.
- For Aadyant's review follow-up on `7e552d6`, wired `yt-intel auth --read/--enable-writes` with a local `127.0.0.1` loopback callback server, kept accounts inactive until channel verification completes, blocked access immediately during disconnect/refresh/partial-cleanup, enforced explicit desktop scopes (`include_granted_scopes=false`), and added cancellation, refresh-during-disconnect, and browser/CLI tests. Re-verified 16 J2-03 tests, full offline suite, strict `mypy src` (53 source files), and scoped Ruff checks. Re-review by Aadyant remains pending.
- For Aadyant's second review on PR #29, merged `origin/main` (`6025d88`), added non-secret `JsonAccountStateStore` reload across separate CLI invocations so `--enable-writes` enforces same-channel verification, removed the bootstrap no-op ledger in favor of real `QuotaLedger` reserve/debit/release (dynamically binding Paul's P2-02 `SqliteQuotaLedger` and failing closed until P2-02 merges), and added a separate-invocation sign-in → enable-writes test. Re-verified 17 J2-03 tests, 275 total offline tests, strict `mypy src` (57 source files), and scoped Ruff checks. Committed locally pending Jeswin's PR comment wording and push.

- At Aadyant's request, Codex added a total send timeout and OAuth-specific errors to [PR #19](https://github.com/AadyantNeog/SEproject/pull/19). All 229 offline tests, scoped Ruff and mypy passed. See [[2026-11-26-j2-01-executor-follow-up]] for the separate contribution.

## 2026-11-26 A2-05 Codex demonstration client

- Aadyant selected Codex Desktop for the Windows demonstration. Recorded the selection in ADR-0009 and updated the fixture setup. See [[2026-11-26-a2-05-codex-demo-client]].
- The Windows Codex app server read the synthetic creation preview and canonical skill resource at Paul's PR #17 head. The operator's second attempt returned no grant and exit code 0 for both manual window close and Reject.
- Updated PR #20 with `main` at `b54573e`, preserving both teammate records. The Windows preview and skill resource probe, 229 offline tests, all 34 planning checks, scoped Ruff and mypy passed. The manual dismissal result is from the earlier fixture run.

## 2026-11-26 A2-07 video-to-playlist fixture slice

- Wrote the canonical product skill, the Codex walkthrough and the evaluation record for [issue #22](https://github.com/AadyantNeog/SEproject/issues/22). The fixture check verified discovery and preview, and the Codex refusal stopped before seed retrieval when the reservation tool was absent. See [[2026-11-26-a2-07-video-to-playlist]] for the evidence and blocked end-to-end cases.

## 2026-11-26 A2-03 recommendation MCP fixture

- Exposed the existing recommendation service over fixture MCP for [issue #14](https://github.com/AadyantNeog/SEproject/issues/14). Codex called the tool and reported the expected English result, liked-video evidence and 120 unused seconds. All 234 offline tests, scoped Ruff, mypy and all 34 planning checks passed. See [[2026-11-26-a2-03-recommendation-stdio]].

## 2026-11-26 J2-02 provider follow-up

- At Aadyant's request, Codex restored the channel batch size and gave unimplemented fixture writes a definite failure in [PR #23](https://github.com/AadyantNeog/SEproject/pull/23). Verified on current main with 245 offline tests, scoped Ruff and mypy. See [[2026-11-26-j2-02-provider-follow-up]].

## 2026-11-27 A2-02 fixture discovery through MCP

- Added the similar-video and similar-channel fixture tools for [issue #10](https://github.com/AadyantNeog/SEproject/issues/10). Codex Desktop returned the expected fixture ranks for both. All 246 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-02-discovery-stdio]].

## 2026-11-27 A2-04 fixture playlist preview

- Added `propose_playlist` over fixture MCP for [issue #12](https://github.com/AadyantNeog/SEproject/issues/12). Codex Desktop returned a private preview of 600 seconds with 120 seconds unused. The stdio test verified the exact stored proposal and zero operation rows. All 247 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-04-playlist-preview-stdio]].

## 2026-11-27 A2-02 discovery candidate handoff

- Connected the discovery pool to the fixture planner using an account-scoped SQLite reference for [issue #10](https://github.com/AadyantNeog/SEproject/issues/10) and [issue #12](https://github.com/AadyantNeog/SEproject/issues/12). Codex Desktop resolved the reference and returned 1,200 seconds selected and 600 seconds unused. All 248 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-02-discovery-candidates]].

## 2026-11-27 A2-05 saved proposal preview resource

- Added the versioned MCP preview link for [issue #8](https://github.com/AadyantNeog/SEproject/issues/8). Codex reopened the exact stored fixture preview. All 249 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-05-saved-proposal-resource]].

## 2026-11-27 A2-04 partial proposal revision planning

- Extended the planner for [issue #12](https://github.com/AadyantNeog/SEproject/issues/12) to apply explicit changes and keep the other saved fields. The atomic revision transaction remains pending. All 257 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-04-partial-proposal-revisions]].

## 2026-11-27 A2-05 discovery progress and cancellation

- Added progress for fixture discovery and verified that a cancelled stdio request closes its provider and leaves the candidate cache untouched for [issue #8](https://github.com/AadyantNeog/SEproject/issues/8). All 258 offline tests, scoped Ruff and mypy passed. See [[2026-11-27-a2-05-discovery-progress]].
