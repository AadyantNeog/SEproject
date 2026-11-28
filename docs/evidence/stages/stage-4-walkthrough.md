# Stage 4 review: demonstration script

28 November 2026 · AT-19, AT-20, GOV-01 · A run sheet for the Stage 4 session

The SDLC brief (§7) lists the Stage 4 items:
1. live demonstration of the FRs in a client
2. run the product skill end to end
3. run local-check live
4. run brain-query live
5. walk through a requirement from brain note to ADR, code and test
6. final release tag

This sheet gives each item a script, expected results and a fallback. It is
a plan, not a record. Mark each step pass, fail or blocked on the day, with
the actual output.

## Before the session

- **Update and check.** Pull `main`, then run `scripts/check_local.py` once
  to warm up.
- **Codex servers.** Open Codex Desktop with `yt-intel-fixture` enabled.
  Enable `yt-intel-live` too if D-02 allows and a test account exists.
- **Resume step.** Run `scripts/seed_resume_fixture.py` and keep the
  operation ID it prints.
- **Open these files** for the walkthrough:
  [06-preview-and-human-approval](../../../brain/resources/06-preview-and-human-approval.md),
  [ADR-0003](../../adr/0003-native-human-approval.md),
  [`approval/service.py`](../../../src/yt_intel/approval/service.py) and
  [`test_playlist_authority.py`](../../../tests/system/test_playlist_authority.py).

## 1. FRs in a client (about 8 min)

Use the prompts in the
[feature evidence](../features/README.md#codex-walkthrough-prompts):
FR-1, FR-2, FR-3 (both prompts) and FR-5 planning. For FR-4, ask:

> Using yt-intel-fixture, load my library and analyse it, comparing September and November 2026.

Expected FR-4 result: playlist additions 0 → 4, subscriptions 1 → 0, and
the likes trend reported as unavailable
([read evidence](../read-and-privacy/README.md)).

**Live.** If D-02 is resolved and a test account exists, call `live_status`,
`get_video` and `get_library` on `yt-intel-live`. Otherwise, show
`live_status` reporting D-02 unresolved and a derived tool returning
`POLICY_BLOCKED`. Say plainly that live FR-1 to FR-5 is **blocked by
policy, not passed**, as SRS §13.2 requires.

## 2. Product skill end to end (about 5 min)

> Use $video-to-playlist with yt-intel-fixture for the synthetic seed vidIndex002. Create a private English playlist about database indexing called "Stage 4 demo", up to 1800 seconds total and 1200 seconds per video.

Point out each step as it happens:
1. the reservation comes before the seed
2. the seed is summarised
3. similar videos are found
4. the exact preview appears
5. the **native dialog** appears, and a human approves
6. the result is verified

Optionally show the resume path with the seeded operation:

> reconcile operation `<id>`, show me the resume preview, and resume it if it is ready.

## 3. local-check live (about 2 min)

```powershell
& '.venv/Scripts/python.exe' scripts/check_local.py
```

Expected: build, test, start, fetch and cleanup all report `passed`.

## 4. brain-query live (about 3 min)

Ask Codex to use the `brain-query` skill:

> Using $brain-query, which decision record governs how playlist writes are approved, and which distilled notes support it?

Expected: ADR-0003, citing
[[06-preview-and-human-approval]] and
[[11-mcp-and-agent-skill-contracts]].

Then ask a question the brain cannot answer, such as "What is the
instructor's D-02 decision?". The expected answer says it isn't recorded.

## 5. Requirement walkthrough: FR-5.5, trusted human approval (about 5 min)

| Step | Artefact | What to show |
| --- | --- | --- |
| Requirement | [SRS FR-5.5](../../requirements/SRS.md) | A write needs explicit human approval of the current proposal through a trusted path |
| Research | [06-preview-and-human-approval](../../../brain/resources/06-preview-and-human-approval.md) | Why a model-controlled boolean is not consent |
| Decision | [ADR-0003](../../adr/0003-native-human-approval.md) | A server-owned native dialog. Grants are bound to the account, digest, version and operation, expire in 10 minutes and are single-use. |
| Code | [`approval/service.py`](../../../src/yt_intel/approval/service.py), [`approval/grants.py`](../../../src/yt_intel/approval/grants.py), [`services/creation.py`](../../../src/yt_intel/services/creation.py) | Where a grant is issued only from the native decision and checked before the write |
| Tests | [`test_human_approval.py`](../../../tests/security/test_human_approval.py), [`test_playlist_authority.py`](../../../tests/system/test_playlist_authority.py) | Forged account, digest or operation, a `confirmed=true` argument, a tampered proposal and injected metadata all produce zero writes |
| Skill | [video-to-playlist step 6](../../../.agents/skills/video-to-playlist/SKILL.md) | The decision is left to the native dialog |
| Observed | [Native approval record](../native-approval/README.md) | Dialog screenshots and the approve and reject outcomes in Codex |
| Trace | [requirement-trace.csv](../release/requirement-trace.csv) | The FR-5.5 row, with its issues and PRs |

Each member should be able to explain any of these files (brief §6).

## 6. Release tag

Do this only after the remaining items in issue
[#56](https://github.com/AadyantNeog/SEproject/issues/56) are resolved or
recorded as blocked with the instructor:
1. Re-run the checks on the final `main` commit.
2. Update the [release record](../release/README.md).
3. A human creates the tag and the GitHub release from `CHANGELOG.md`.
