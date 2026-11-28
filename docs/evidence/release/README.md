# Release candidate record

28 November 2026 · P2-08 release assembly · Assembled by Aadyant (transferred, [ADR-0010](../../adr/0010-solo-completion-ownership-transfer.md)) · **Merged to `main`, not released.** There is no tag and no final human acceptance yet.

## Candidate

| Item | Value |
| --- | --- |
| Merged `main` | `061932d` (merge of PR #63). Its tree is identical to the reviewed `0a960af`. |
| Code-checked commit | `283a330`. The later commits change only documentation. |
| PRs | [#57](https://github.com/AadyantNeog/SEproject/pull/57) to [#62](https://github.com/AadyantNeog/SEproject/pull/62), each with Aadyant's owner review. [#63](https://github.com/AadyantNeog/SEproject/pull/63) brought the stacked commits into `main` unchanged, and #59 was closed as superseded by it. |
| Hosted CI | #57 and #63 passed on Linux and Windows, and the secret scan passed |
| Release tag | None. Only a human creates the tag, after the remaining items below. |

### Branches (all merged)

#57 merged into `main`. #58, #60, #61 and #62 merged into their stacked
bases, so #63 then merged the complete stack into `main`. The branches
were:

1. `codex/a2-08-feature-evidence`: A2-08 NFR-08 benchmark and the
   feature and skill evidence
2. `codex/v2-3-solo-completion`: v2.3 ownership transfer (ADR-0010, RN-20)
3. `codex/j2-07-live-read-setup`: consent runbook, `yt-intel disconnect`,
   the fixed-budget live read check and its workflow
4. `codex/j2-08-read-path-evidence`: read-path stdio tests, the
   denied-source fix and the cached-read benchmark
5. `codex/p2-08-write-quota-acceptance`: write, authority and quota stdio
   tests
6. `codex/release-candidate-evidence`: CI knowledge validation, register
   backfill, architecture page and this record

## Checks on merged `main`

All of these ran at `061932d`, or on a byte-identical local merge result
before the GitHub merge:
- **Tests and lint.** 349 offline tests, Ruff, and mypy for Windows and
  Linux passed.
- **Local check.** All five stages of `check_local.py` passed.
- **Validators.** The planning validator passed 35 of 35, and the knowledge
  validator passed.
- **Performance.** All 12 NFR-08 targets passed again
  ([re-run](../performance/report.md#re-run-on-merged-main)).
- **Hosted CI.** Passed on #63.

## Checks run on `283a330`

All checks ran on Windows 11 with 16 logical CPUs, 15.6 GiB of RAM and
Python 3.13.1 in the locked `.venv`. They spent zero live quota. Hosted
Linux and Windows CI has **not** run on these branches yet.

| Check | Result |
| --- | --- |
| `ruff check` and `ruff format --check`, with the CI scope plus the new scripts | Pass. 119 files. |
| `mypy src` for the Windows and Linux platforms | Pass. 74 source files. |
| `pytest -m "not live"` | **349 passed** |
| `python -m build --wheel --no-isolation` | Pass |
| `scripts/check_local.py` | All 5 stages pass: build, test, start, fetch, cleanup |
| `scripts/benchmark_features.py --runs 30` | All 12 NFR-08 targets pass ([report](../performance/report.md)) |
| `scripts/validate_implementation_plan.py` | 35 of 35 |
| `scripts/validate_knowledge.py` | Pass. 72 notes, 5 skills, 10 ADRs, 377 wikilinks. |

The first `check_local.py` run in this session failed its test stage. The
sandbox denied access to pytest's shared temp folder. Pointing
`TEMP`/`TMP` and `--basetemp` at a scratch folder fixed it. This was an
environment problem, not a product defect.

## Acceptance status (AT-01 to AT-20)

"Fixture pass" means automated synthetic evidence passed. It is not live
acceptance. The per-requirement links are in
[requirement-trace.csv](requirement-trace.csv).

| AT | Fixture evidence | Still needed |
| --- | --- | --- |
| AT-01 MCP init, schemas, stdio, client | Fixture pass. Codex Desktop observed with both the fixture and live servers ([live evidence](../live/README.md)). | None |
| AT-02 Video ranking | Fixture pass | None for fixtures. Live run is blocked on D-02. |
| AT-03 Channel resolution and ranking | Fixture pass | Live run, blocked on D-02 |
| AT-04 Personalisation, sparse sources, pagination | Fixture pass | Live run, blocked on D-02 |
| AT-05 Hand-calculated analysis and UTC boundaries | Fixture pass ([read evidence](../read-and-privacy/README.md)) | Live analytics, blocked (`POLICY_BLOCKED`) |
| AT-06 Constrained proposal, approval and creation | Fixture pass. Native-dialog approve observed in Codex. | Live creation is blocked |
| AT-07 Duration, language and topic constraints | Fixture pass | None for fixtures |
| AT-08 Reject, absent, expired, replayed, changed or wrong-account approval | Fixture pass ([write evidence](../write-and-quota/README.md)). Native reject observed in Codex. | None for fixtures |
| AT-09 Partial, restart, ambiguous timeout, reconciliation | Fixture pass. Native resume approve and reject observed in Codex. | Live recovery is blocked |
| AT-10 Malformed IDs, hosts, limits, private content | Fixture pass | None for fixtures |
| AT-11 Expired or revoked tokens, scope, refresh | Fixture pass with mocked OAuth | Live token lifecycle on the test account |
| AT-12 Prompt injection and forged approval | Fixture pass | None for fixtures |
| AT-13 Insufficient quota, concurrent reservations | Fixture pass | None for fixtures |
| AT-14 Secrets, isolation, deletion, cache expiry | Fixture pass. Vault backend detected on the workstation. | Runner vault check. Inspection of the logs. |
| AT-15 Caps, accounting, reset, external exhaustion | Fixture pass | None for fixtures |
| AT-16 Rate limits, timeouts, 5xx, bounded retries | Fixture pass | None for fixtures |
| AT-17 Offline performance | **Pass**, all 12 targets at `283a330` and again on merged `main` `061932d` | Re-run if code changes before the tag |
| AT-18 Skills, notes, validation, offline CI | Skill tests and validators pass. Hosted CI ran knowledge validation on #63. | Skill evaluation with the live client |
| AT-19 Walkthroughs and live skill demo | Codex walkthrough done ([features](../features/README.md)). Live reads, live FR-1 to FR-4 and the live FR-5 preview demonstrated in Codex ([live evidence](../live/README.md#live-derived-runs-fr-1-to-fr-4-and-the-fr-5-preview)). D-02's basis is a team-lead decision (ADR-0012). | A supervised live `create_playlist` through the native dialog. It is built ([ADR-0013](../../adr/0013-live-approved-playlist-creation.md)) and passes offline, but has not yet been run live. |
| AT-20 Design, ADR, plan, review, trace, release | ADRs 0001–0010, [architecture](../../developer/architecture.md), coverage register, this record | **Human owner reviews**, stage reviews and the release tag |

## Defects and regressions found in this cycle

| ID | Found in | Defect | Fix | Regression test |
| --- | --- | --- | --- | --- |
| D-2026-11-28-1 | J2-08 probe | `compare_periods` reported denied or unrequested sources as `0 → 0` "no events", which presented missing evidence as zero activity | Compare only retrieved sources. Warn about not-requested sources. | `test_denied_and_unrequested_sources_are_not_reported_as_zero` (fails on the old code), `test_unretrieved_sources_are_not_compared_as_zero_activity` |
| D-2026-11-28-2 | J2-07 audit | The runbook needed a live disconnect, but the CLI had only `auth` | Added `yt-intel disconnect` | `test_cli_disconnect_*` |

Live runs also showed three ranking-quality weaknesses: link tokens in
similarity, short clips crowding playlists, and weak channel matches. They
are recorded in the [live evidence](../live/README.md#ranking-quality-observed-live-not-failures)
as follow-up candidates. No limit or constraint was broken. There were
no other product defects. One test expectation was corrected:
moving a stored expiry produces `PROPOSAL_CHANGED`, because the digest
covers the expiry.

## Conflicts recorded, not resolved by an agent

- **Protected traceability file.** The status checklist asked to backfill
  `docs/requirements/traceability.csv`. That file is in the SHA-protected
  submitted-SRS baseline
  ([protected-baseline-2026-11-19.json](../../implementation/protected-baseline-2026-11-19.json)),
  so it was left unchanged. The live trace is in
  [coverage.csv](../../implementation/coverage.csv) and
  [requirement-trace.csv](requirement-trace.csv). Changing the baseline
  needs instructor direction.
- **Teammate acknowledgement.** The ownership transfer was reported by the
  team lead. Jeswin's and Paul's written acknowledgement is not in the
  repository yet.

## Human and external actions remaining

1. **Done.** Issues #53 to #56, PRs #57 to #63, owner reviews and hosted CI.
   #54 and #55 are closed. The completed older issues (#1, #6, #8, #10,
   #12, #14 and #26) were closed with evidence comments. #22, #53 and #56
   stay open for the items below.
2. **Manual runs (done 28 November 2026).** The Codex walkthrough, the
   native create approve and reject, and the resume approve and reject are
   recorded. #22 and #53 are closed.
3. **D-02 (resolved 28 November 2026 by team-lead decision).** See
   [ADR-0012](../../adr/0012-d02-team-lead-resolution.md). It is not
   instructor or provider evidence, and it departs from SRS §13.2.
4. **Live setup.** Provision the test account, OAuth client and protected
   runner, then run the supervised live demonstrations.
5. **Reflections.** Each member writes their own reflection and
   contribution record.
6. **Release.** Re-run the checks if anything changes, then create the
   release tag.

Prepared with AI assistance. This is not a review or an acceptance record.
