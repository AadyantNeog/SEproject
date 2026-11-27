# Feature integration evidence

28 November 2026 · A2-08 · FR-1, FR-2, FR-3 and FR-5 planning · Issue pending · PR pending

This record covers Aadyant's feature track on the fixture provider. FR-4
analysis belongs to [J2-08](../../implementation/tasks.json). Write,
quota-refusal and recovery acceptance belongs to P2-08. Live results are
not claimed. D-02 and the live prerequisites remain open.

## How it was run

Each case ran through a real `python -m yt_intel serve --provider fixture`
subprocess over MCP stdio. Each case used a fresh temporary fixture database
and the project's quota profile. The cases are automated system tests, so
the inputs and checked outputs below are what the tests assert. The tests
passed on Windows 11 with Python 3.13.1 at commit `4c98b2c`, as part of the
330-test offline suite.

```powershell
& '.venv/Scripts/python.exe' -m pytest -q tests/system/test_discovery_stdio.py tests/system/test_recommendation_stdio.py tests/system/test_playlist_planning_stdio.py tests/system/test_composed_workflow_budget.py tests/system/test_playlist_execution_stdio.py tests/system/test_operation_replay.py tests/skills/test_video_to_playlist.py tests/performance/test_local_targets.py
```

## FR-1 similar videos

[`test_fixture_discovery_over_stdio`](../../../tests/system/test_discovery_stdio.py)

| Input | Checked output |
| --- | --- |
| `find_similar_videos {"video": "https://youtu.be/vidIndex001", "limit": 1}` | `ok` fixture envelope with one result, `vidIndex002` (1,201 s). Coverage is paginated with two unknown candidates. Quota profile is `youtube-2026-11-16`, and a `candidate_set_id` is returned. Text says `Mode: fixture (synthetic data)` and `Audio language: unknown`. Progress reports 1/3, 2/3 and 3/3. |
| Off-host URL `https://example.com/watch?v=vidIndex001` | `UNSUPPORTED_IDENTIFIER`. No data and no candidate set. |
| `limit: "1"`, an extra `binding`, or an unknown `workflow_id` | `INVALID_INPUT` |
| Unavailable seed `vidOmit0009` | `CONTENT_UNAVAILABLE` |
| Search budget below the worst-case reservation | `QUOTA_INSUFFICIENT`, with zero quota attempts and zero reservations recorded ([`test_discovery_rejects_insufficient_quota_before_seed`](../../../tests/system/test_discovery_stdio.py)) |
| Cancelled discovery | Provider closed and no candidate set published ([`test_cancelled_discovery_closes_provider_without_publishing`](../../../tests/system/test_discovery_stdio.py)) |

## FR-2 similar channels

[`test_fixture_discovery_over_stdio`](../../../tests/system/test_discovery_stdio.py)

| Input | Checked output |
| --- | --- |
| `find_similar_channels {"channel": "https://www.youtube.com/@SystemsStudyLab"}` | One result, `UCbbbbbbbbbbbbbbbbbbbbbb`. The sample is `vidIndex002` under rule `first-accessible-uploads-v1`, and coverage is marked sampled. Text says `Channel sample: 1 usable`. Each of the two discovery calls spent 2 search units from its reservation. The reservation recorded 10 remaining and was released. |

## FR-3 recommendations from saved preferences

[`test_recommendation_stdio.py`](../../../tests/system/test_recommendation_stdio.py)

| Input | Checked output |
| --- | --- |
| `recommend_videos` on `fixture-snapshot` for `database indexing`, `en`, 720 s total and 600 s per video | `fixture0301` from `likes`. Subscriptions are `not_requested`. Result is 600 s with 120 s unused. Text says `Unused time: 120 s`. |
| `get_library {"sources": ["likes"]}`, then `recommend_videos` on the saved snapshot, `en`, 1,300 s | `vidIndex001`. Result is 1,200 s with 100 s unused. Coverage is paginated, with 3 retrieved and 2 usable. |
| Foreign or expired saved snapshot, `limit: "1"`, a foreign `account_id`, or an unknown `workflow_id` | `CONTENT_UNAVAILABLE` or `INVALID_INPUT`. No data. |
| `language: "ja"` | `empty` status with no results. A missing match is not treated as an error. |

## FR-5 strict planning and preview

[`test_playlist_planning_stdio.py`](../../../tests/system/test_playlist_planning_stdio.py)

| Input | Checked output |
| --- | --- |
| `propose_playlist` on `fixture-recommendations`: "Indexing for beginners", `database indexing`, 720 s total, 600 s per video, `en` | Version 1 is stored as `proposed` and private, with `fixture0301` (`en-US` audio). Result is 600 s with 120 s unused and one audio-language exclusion. The 10-minute expiry and the digest are checked. The preview text matches the `yt-intel://proposals/{id}/1` resource. One proposal and zero operations are stored. |
| Missing fields, or `duration_mode: "exact"` | `CLARIFICATION_REQUIRED` |
| `language: "ja"`, or `max_video_seconds: 599` | `NO_FEASIBLE_PLAYLIST`, and no state is written |
| `confirmed: true`, or `total_seconds: "720"` | `INVALID_INPUT`. `create_playlist` has no `confirmed` parameter. |
| Stale, foreign, expired, changed or rejected preview version | Resource unavailable ([`test_saved_preview_denies_stale_and_foreign_versions`](../../../tests/system/test_playlist_planning_stdio.py)) |
| Discovery candidates after a server restart | They reach the planner from SQLite ([`test_discovered_candidates_reach_planner_after_restart`](../../../tests/system/test_discovery_stdio.py)) |

## Video-to-playlist composition

The pending end-to-end cases are now automated through stdio. The tests
inject a fixture approval adapter in the isolated test launcher. The manual
native-dialog run is still a separate step. See the
[updated skill evaluation](../skills/video-to-playlist.md#end-to-end-fixture-cases).

## Performance

All NFR-08 validation, ranking and proposal targets passed at `4c98b2c`.
See the [performance report](../performance/report.md).

## Still open for A2-08

- **Codex walkthrough.** A manual Windows Codex Desktop walkthrough of
  FR-1, FR-2, FR-3 and FR-5 planning is still needed, using the
  [Codex fixture setup](../../developer/codex-fixture.md). The tests above
  drive stdio from a Python MCP client, not from Codex. The prompts to use
  are listed below.
- **Native approval.** The manually observed native approval or refusal in
  the full product-skill path is still pending. It must be run by a human,
  not by an agent.
- **Traceability.** Real Issue and PR links for the FR-1, FR-2, FR-3 and
  NFR-08 rows in [coverage.csv](../../implementation/coverage.csv) and
  [traceability.csv](../../requirements/traceability.csv) are still pending.
- **Owner review.** The dated human owner-review note for this A2-08 change
  and the individually authored reflection are still pending.

### Codex walkthrough prompts

Use the fixture server as the only project server and record the tool trace
for each prompt.

1. FR-1: "Using yt-intel-fixture, find videos similar to https://youtu.be/vidIndex001, limit 1, and report the evidence and coverage."
2. FR-2: "Using yt-intel-fixture, find channels similar to https://www.youtube.com/@SystemsStudyLab and explain the channel sample."
3. FR-3: "Using yt-intel-fixture, load my likes and recommend English videos about database indexing that fit in 720 seconds, at most 600 seconds each."
4. FR-5 planning: "Using yt-intel-fixture, preview a private English playlist called Indexing for beginners about database indexing, 720 seconds total and 600 seconds per video, from the fixture-recommendations candidate set. Do not create it."

The expected results are the checked outputs above. Check that the client
shows the fixture mode label. For the FR-5 prompt, check that the client
stops at the preview and does not create anything.

Prepared with AI assistance. Human owner review is pending.
