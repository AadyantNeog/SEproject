# Live read evidence

28 November 2026 · NFR-01, NFR-02, NFR-05, FR-0, FR-3 and FR-4 retrieval · AT-01, AT-10, AT-14, AT-19 (live part) · Part of #56

This is the first evidence from the real YouTube Data API v3. Aadyant ran it
on `main` at `fafbbd7`, which includes live serve mode (PR #70,
[ADR-0011](../../adr/0011-staged-live-serve-mode.md)). The client was Codex
Desktop v26.1120 on Windows 11, using the `yt-intel-live` server.

**Privacy.** The account is Aadyant's own YouTube account, which he
authorised. Following the brief and AGENTS.md, this record leaves out the
channel ID, the channel name, library titles and exact library counts. It
records only statuses, tool names, the coverage shape and quota totals.
Public video metadata is included.

## Setup

| Step | Observed |
| --- | --- |
| Google Cloud project | One project, with YouTube Data API v3 enabled. The OAuth consent screen is in **Testing** mode, with the account added as a test user. |
| Desktop OAuth client | Created. The JSON is stored outside the checkout under the user profile and referenced through `YT_INTEL_OAUTH_CLIENT_SECRETS`. |
| First sign-in attempt | `Error 403: access_denied`, because the account was not yet a test user. Adding it fixed this. |
| `yt-intel auth --read` | The browser consent flow completed ("Authorisation received"). The saved account record has mode `live`, a valid `UC…` channel ID, scope `youtube.readonly` only and no token fields. The tokens are in Windows Credential Manager, which was not opened. The sign-in recorded one `channels.list` quota attempt. |

## Codex runs

| Prompt | Tool calls | Result | Verdict |
| --- | --- | --- | --- |
| "Using yt-intel-live, call live_status." | `live_status` | Account connected, D-02 unresolved. Five tools available, six derived tools blocked. | Pass |
| "…get the video https://www.youtube.com/watch?v=dQw4w9WgXcQ" | `get_video` | Real metadata labelled `Mode: live`: "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)", 214 s, `defaultAudioLanguage` `en` (audio evidence), category 10, available, recorded. Single-video coverage. | Pass |
| "…load my likes, subscriptions and playlists." | `get_library`, then four calls passing the returned `continuation_ref` | All three sources `retrieved`. Subscriptions and playlists completed in the first call and are marked sampled. Likes hit the 4-page budget and reported `truncated: true` with a continuation reference. Codex followed it four times until likes reported `complete: true`. Each call returned a separate snapshot. Nothing was truncated silently. | Pass |
| "…call find_similar_videos with video dQw4w9WgXcQ." | `find_similar_videos` | `POLICY_BLOCKED`: "uses derived processing of live YouTube data, which is disabled until D-02 has a recorded resolution". Not retryable. | Pass (refused as designed) |

An earlier, looser prompt ("find videos similar to that video") led Codex
to call `live_status` and explain the block without calling the tool. It
also offered a separate web search. That offer is outside the project's
official-API-only rule and was not taken. As in the fixture runs, Codex
also ran a read-only shell command to read the SRS and brain index before
one of the tool calls.

## Quota accounting (from the live SQLite ledger)

| Endpoint | Attempts |
| --- | ---: |
| `videos.list` | 32 |
| `playlistItems.list` | 13 |
| `subscriptions.list` | 3 |
| `channels.list` | 2 |
| `playlists.list` | 1 |
| **Total** | **51 attempts, 51 general units** (of 10,000 a day) |

- **Project.** Every attempt was recorded under project `default-project`,
  shared by the CLI and the server.
- **Reservations.** No reservation was left unreleased.
- **Blocked call.** The attempt count stayed at 51 after the
  `find_similar_videos` call, so the refusal made zero API calls.

## Live derived runs (FR-1 to FR-4 and the FR-5 preview)

28 November 2026, later the same day, on `main` at `3a4d45e`. This build
includes the live derived handlers (PR #73, ADR-0011 step two). D-02 was
resolved by team-lead decision (PR #74,
[ADR-0012](../../adr/0012-d02-team-lead-resolution.md)), not by instructor
evidence. Aadyant restarted `yt-intel-live` in Codex Desktop and ran the
prompts below.

**Privacy.** Some results come from the account's own library: the
recommendations, the analysis and the library counts. Their titles,
channel names, counts and the proposal's destination are left out. Public
metadata for the seed video's similarity results is included.

| Prompt | Tool | Result | Verdict |
| --- | --- | --- | --- |
| "…call live_status." | `live_status` | D-02 resolved. All five derived tools are available. Only `begin_workflow` is blocked. | Pass |
| "…call find_similar_videos with video dQw4w9WgXcQ and limit 10." | `find_similar_videos` | 10 ranked videos labelled `Mode: live`, each with a score, a reason, matched terms and language evidence. The 187 candidates came from 4 search pages, under the 200 cap. The result is marked `truncated: true` and `complete: false`. Videos without audio-language data carry `audio_language_missing_metadata_only`. A candidate set was saved. | Pass (FR-1) |
| "…call propose_playlist with title "Live test", topic "rick astley never gonna give you up", total_seconds 1800, max_video_seconds 600, language "en" and the candidate set." | `propose_playlist` | A private preview of 18 videos totalling 1,794 of 1,800 s. Every video is at most 600 s and has English audio confirmed by `defaultAudioLanguage`. Exclusions are reported in full: 94 audio language unverified, 10 audio language mismatch, 5 topic mismatch, 10 over the per-video limit, 50 over the remaining time, and 1 seed not requested. State is `proposed`, with a 10-minute expiry. It is labelled "Preview only", and nothing was written. | Pass (FR-5 planning) |
| "…call find_similar_channels with channel @RickAstleyYT." | `find_similar_channels` | 10 channels, each from a sample of 5 uploads using the `first-accessible-uploads-v1` rule. Coverage is marked as sampled and truncated. Missing channel descriptions are flagged. | Pass (FR-2) |
| "…call get_library." | `get_library` | All three sources `retrieved`. Likes hit the 4-page budget and reported `truncated: true` with a continuation. Subscriptions and playlists completed. | Pass |
| "…call recommend_videos with the snapshot and language "en"." | `recommend_videos` | 10 ranked recommendations from likes, playlist items and subscription topics. It reported that likes were partial. 165 candidates were retrieved within the search limits. | Pass (FR-3) |
| "…call analyse_library with the snapshot." | `analyse_library` | A report with per-source counts, median durations, overlap between likes and playlists, top channels and top categories. It states that likes were partial and that runtimes describe the snapshot, not viewing time. | Pass (FR-4) |

### Quota accounting (live ledger, whole day)

| Endpoint | Attempts |
| --- | ---: |
| `videos.list` | 72 |
| `playlistItems.list` | 37 |
| `subscriptions.list` | 6 |
| `channels.list` | 5 |
| `playlists.list` | 2 |
| `search.list` | 13 |
| **Total** | **122 general units** (of 10,000) and **13 search units** (of the profile's 100 search calls) |

- **Reservations.** All 12 reservations for the day are under `default-project`, and none is left unreleased.
- **This session's share.** It adds 71 general units and all 13 search units to the 51 general units recorded above.

### Ranking quality observed live (not failures)

No hard rule was broken. Every limit, language check and coverage note
held. Three quality weaknesses showed up with real data:

1. **Link noise in similarity.** Tokens such as `lnk` and `https` from URLs
   in descriptions count as matched terms. As a result, re-uploads that
   copy the official description rank above the official videos,
   including a 13-second clip ranked first. Stripping URLs before
   tokenising would fix this.
2. **Short clips crowd the playlist.** The planner packs by relevance
   (`greedy-relevance-v1`), and Shorts with the song name in the title
   score highly. So 7- to 68-second clips fill much of the time, while
   several official full-length videos are excluded for the time
   remaining. A minimum per-video duration option would help.
3. **Weak channel matches.** Channel similarity is bounded to 10 candidates
   from a 5-upload sample each, so the scores are low (0.16 and below).
   Some matches are weak, such as a TV network channel, and link tokens
   affect them again.

They are recorded as follow-up candidates, not as passed or failed
acceptance cases.

## What this does and does not show

- **Shows.** The live stack works end to end against Google's real API:
  - OAuth consent
  - an OS-protected token vault
  - bearer-authenticated requests through the accounted executor
  - quota debited before dispatch
  - normalised metadata
  - bounded, continuable library retrieval with honest per-source coverage
  - the D-02 gate refusing derived processing with no provider calls
- **Also shows (later runs).** Live FR-1 to FR-4 and the FR-5 preview
  in Codex, with honest coverage, strict constraints and no writes. D-02's
  basis is a team-lead decision (ADR-0012), not instructor evidence.
- **Does not show.** Live playlist creation through the native approval
  dialog, which is not built in live mode. This remains a gap, not a
  passed acceptance case (SRS §13.2).
- **Not run.** The scheduled protected-runner check and live token expiry or
  revocation recovery.

Prepared with AI assistance from Aadyant's Codex transcripts and the local
ledger, which was queried read-only. Aadyant's owner review is pending.
