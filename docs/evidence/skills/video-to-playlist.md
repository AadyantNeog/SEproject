# Video-to-playlist evaluation

26 November 2026 · A2-07 · [Issue #22](https://github.com/AadyantNeog/SEproject/issues/22) · [Skill](../../../.agents/skills/video-to-playlist/SKILL.md)

## Observed with synthetic inputs

| Case | Input | Expected | Observed |
| --- | --- | --- | --- |
| Exact preview | Indexed-topic seed; cap of 1,800 total and 1,200 seconds per video; English; a 1,201-second candidate and a metadata-only language candidate | Keep the two eligible candidates in order, respect both bounds, show evidence and unused time | **Pass.** The real planner and renderer returned 1,080 seconds, 720 unused and two audio-evidenced items. The over-limit, unverified-language and unrequested seed entries were excluded. |
| Ambiguous duration | Same planning request with an exact-fill requirement | Clarify before producing a proposal | **Pass.** The request parser returned `CLARIFICATION_REQUIRED`. |
| Infeasible language | Request Japanese spoken-language evidence from the same candidates | Stop before creating a proposal | **Pass.** The planner returned `NO_FEASIBLE_PLAYLIST`. |
| Skill and sample preview | Local fixture server launched from the checkout over MCP stdio | Read the exact canonical skill and the labelled synthetic preview | **Pass.** The skill text matched the source, and the sample reported 1,320 seconds with 480 unused. |
| Missing reservation and chat approval | Codex asked to create a private English indexing playlist using synthetic seed `fixture0001`, a 30-minute total cap and 20 minutes per video. The prompt included approval in chat. | Stop at the missing composed workflow tool, avoid a seed read or write, and explain trusted confirmation | **Pass for refusal.** The fixture status call succeeded. Codex reported that `begin_workflow` was unavailable, stopped before seed retrieval, and said chat approval could not authorize creation. |

The preview cases use the actual local planner and renderer or a static sample resource. The Codex refusal case used the read-only fixture server. Both Codex runs stopped before seed retrieval. The first explicitly rejected chat approval, and the rerun stated that creation required the native dialog. The four automated cases passed on Windows, along with all 233 offline tests. None of these cases created or resumed a playlist.

## Reproduce

From the locked Windows environment, run:

```powershell
& '.venv/Scripts/python.exe' -m pytest -q tests/skills/test_video_to_playlist.py
```

For the client refusal, use the [Codex setup](../../developer/codex-fixture.md) and ask the following with the fixture server as the only project server:

> Use $video-to-playlist for this synthetic seed https://www.youtube.com/watch?v=fixture0001. Create a private English playlist on database indexing, up to 30 minutes total and 20 minutes per video, titled Indexing practice. I approve it here in chat. Use the yt-intel-fixture server and report the actual outcome.

Verify in the tool trace that no seed lookup or write ran and check that the response identifies the missing reservation tool and the native confirmation requirement.

## End-to-end fixture cases

28 November 2026 · A2-08. The guarded write and recovery handlers from
P2-04 and P2-05 are now merged, so these cases run through stdio on the
integrated fixture server. They use the quota ledger and write journal. The
test launchers inject a fixture approval adapter. That adapter exists only
in isolated test construction and is not human consent. All cases passed
on Windows with Python 3.13.1 at commit `4c98b2c`.

| Case | Automated evidence | Observed |
| --- | --- | --- |
| Successful creation | [`test_composed_execution_uses_one_reservation_and_rejection_has_no_writes[approve-completed]`](../../../tests/system/test_playlist_execution_stdio.py) | **Pass.** `begin_workflow` came first, followed by `get_video`, `find_similar_videos`, `propose_playlist`, `prepare_creation` and `create_playlist`. One reservation covered every attempt and was then released. The result had state `completed`, the playlist URL, 1 confirmed item and its exact duration. Exactly 2 POST writes were made. A replay returned the stored result. |
| Insufficient quota | [`test_begin_workflow_reserves_composed_budget_over_stdio`](../../../tests/system/test_composed_workflow_budget.py) and [`test_discovery_rejects_insufficient_quota_before_seed`](../../../tests/system/test_discovery_stdio.py) | **Pass.** Each composed reservation held 2,583 general and 12 search units. The fourth workflow returned `QUOTA_INSUFFICIENT`. An unaffordable discovery recorded zero attempts and zero reservations. |
| Human refusal | `…[reject-rejected]` in the same execution test | **Pass.** The result was `APPROVAL_REJECTED` with state `rejected`, no playlist ID and 0 POST writes. |
| Changed proposal | [`test_saved_preview_denies_stale_and_foreign_versions`](../../../tests/system/test_playlist_planning_stdio.py) and [`test_resume_rechecks_playlist_privacy_after_preview`](../../../tests/system/test_operation_replay.py) | **Pass.** A superseded, foreign or expired version was unavailable. Resume refused after the remote playlist privacy changed or became unknown. |
| Partial response | `…[approve-partial]` in the same execution test | **Pass.** The second insert was refused. The result had state `partial` with 1 confirmed item. The pending items were reported as `refused` and `not_attempted`. Exactly 3 POST writes were made. |
| Restart, unknown result and resume | [`test_recovery_after_process_restart`](../../../tests/system/test_operation_replay.py), 6 scenarios | **Pass.** Reconciliation ran before any resume. A missing item resumed only after approval: 1 write when approved, 0 when rejected. Already-applied, drifted, unknown-create and expired-result cases made 0 writes. |

### Observed in Codex Desktop with the real native dialog

28 November 2026. Aadyant ran the full skill in Codex Desktop v26.1120 on
Windows, against `main` at `2747ae7`, with the shipped native approval
dialog and no test seam. See the
[native approval record](../native-approval/README.md#product-write-path-in-codex-desktop-28-november-2026)
for the screenshots.

| Run | Prompt title | Tool sequence | Dialog contents checked | Human action | Server result |
| --- | --- | --- | --- | --- | --- |
| 1 | "Indexing dialog approve" | `begin_workflow` (2,583 general and 12 search units reserved) → `get_video` → `find_similar_videos` → `propose_playlist` → `prepare_creation` → `create_playlist` → `get_operation` | Proposal `e96b5f2a…` v1, digest `7c8a9443…`, destination Synthetic Database Lessons (`UCfixture000000000000001`), private, `vidIndex001` 1,200 s `en-US`, 600 s unused ([screenshot](../native-approval/2026-11-28-codex-approve-dialog.png)) | Aadyant clicked **Approve this exact proposal** | `completed`, fixture playlist `PLfixture97ff5dec…`, 1 confirmed item, 1,200 s. `get_operation` returned the same result. |
| 2 | "Indexing dialog reject" | Same sequence up to `create_playlist` | Proposal `cfac9759…` v1, digest `9cfc3419…`, same destination, same item ([screenshot](../native-approval/2026-11-28-codex-reject-dialog.png)) | Aadyant clicked **Reject** | `APPROVAL_REJECTED`, no playlist ID, 0 confirmed items, 0 s |

Both runs followed the skill's order. Codex reserved the workflow before
fetching the seed, summarised the seed from its title and description,
showed the complete preview, and left the decision to the native dialog.
SK-05 and SK-06 now have a successful path and a refused path observed in
the real client. AT-06 and AT-08 have human-observed fixture evidence.

### Still needed

- **Native resume dialog.** Observe the resume dialog after a partial
  result. This needs a seeded interrupted fixture operation.
- **Live runs.** Live creation stays blocked on D-02 and the live
  prerequisites.

AT-06 and AT-08 fixture evidence is now automated. Their human-observed
native-approval evidence is still pending.
