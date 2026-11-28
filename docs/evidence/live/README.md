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

## What this does and does not show

- **Shows.** The live stack works end to end against Google's real API:
  - OAuth consent
  - an OS-protected token vault
  - bearer-authenticated requests through the accounted executor
  - quota debited before dispatch
  - normalised metadata
  - bounded, continuable library retrieval with honest per-source coverage
  - the D-02 gate refusing derived processing with no provider calls
- **Does not show.** Live FR-1 to FR-5 (similarity, recommendations,
  analysis and playlist creation). They stay **blocked** until D-02 has a
  recorded instructor or provider resolution and the live derived handlers
  exist (ADR-0011). This is a blocked prerequisite, not a passed acceptance
  case (SRS §13.2).
- **Not run.** The scheduled protected-runner check and live token expiry or
  revocation recovery.

Prepared with AI assistance from Aadyant's Codex transcripts and the local
ledger. Aadyant's owner review is pending.
