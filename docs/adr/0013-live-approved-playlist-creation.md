# ADR-0013 Live playlist creation through the native approval dialog

Date: 28 November 2026 · Author: Claude Code, for Aadyant Neog · Status: pending human owner review

## Context

Stage 4 needs one supervised live write: an approved playlist created on
the test account, with its quota spend recorded. The fixture server already
had the full guarded path:
- the native approval helper (P2-03)
- the guarded creation service and the real write adapter (P2-04 and P2-05)
- the composed workflow budget (P2-02)

Live mode exposed none of it.

D-02 was resolved by team-lead decision (ADR-0012), but that decision
explicitly does not authorise live writes. What authorises a write is the
human approval of the exact proposal (SRS §4, ADR-0003).

Distilled basis: [Preview and human approval](../../brain/resources/06-preview-and-human-approval.md)
and [quota buckets and budgeting](../../brain/resources/09-quota-buckets-and-budgeting.md).

## Decision

- **One path to a live write.** The only route is one video-to-playlist
  workflow, with every step using the same `workflow_id`:
  1. `begin_workflow`
  2. `get_video`
  3. `find_similar_videos`
  4. `propose_playlist`
  5. `prepare_creation`
  6. `create_playlist`

  A standalone `propose_playlist` stays a preview only.
- **Quota first.** `begin_workflow` reserves the whole worst-case budget,
  including 50 item inserts, before the seed is fetched. Every stage spends
  that one reservation, and it is released at the end or on any failure.
- **Approval.** `create_playlist` uses the same `PlaylistCreationService` as
  the fixture server, with the real `YouTubeWriteAdapter`:
  - **The dialog.** The server-owned native dialog shows the complete stored
    proposal. The CLI never passes a test adapter, so the dialog is always
    the real one.
  - **The grant.** It is bound to the account, the proposal digest and
    version, and the operation. It expires within 10 minutes and is used
    once.
  - **Before any write.** Intent is persisted first, and the destination
    channel, durations and audio languages are revalidated.
  - **Each write.** It gets one attempt. Partial and unknown outcomes are
    recorded. A repeated `create_playlist` returns the recorded result and
    never writes again.
- **Preconditions.** Every step needs:
  - **D-02 resolved** in the reviewed record, because the proposal comes
    from derived ranking.
  - **The `youtube.force-ssl` scope**, from `yt-intel auth --enable-writes`.
    Without it, `begin_workflow` returns `SCOPE_REQUIRED` with zero calls.
- **Not exposed.** Live `resume_operation` and `reconcile_operation`. An
  unknown or partial live result is reported through `get_operation` for a
  human to check and fix in YouTube. Nothing retries or deletes
  automatically.

## Consequences

- **What can be demonstrated.** The Stage 4 supervised write can now run
  live in Codex, with the real dialog and real quota.
- **Approval is still the user's.** The model cannot approve. A test can
  inject a scripted decision only in isolated test construction.
- **Recovery is manual.** Live recovery needs a human, which is a
  documented limitation.

Requirements FR-5, NFR-03, NFR-04, NFR-05. Issue #56.
