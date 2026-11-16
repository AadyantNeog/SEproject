# ADR-0005: Durable write recovery, bounded retention and explicit live gates

Date: 16 November 2026 · Author: Codex · Status: proposed for human review

## Context

YouTube playlist and item writes are separate remote operations; a timeout can leave a write applied without a saved response. FR-5.7 requires duplicate prevention and truthful partial state. NFR-05 requires deleting/refreshing API data within retention limits. D-02 remains an unresolved dependency for affected live-derived processing.

Distilled basis: [07-playlist-writes-and-partial-failure](../../brain/resources/07-playlist-writes-and-partial-failure.md), [08-oauth-and-secret-handling](../../brain/resources/08-oauth-and-secret-handling.md), [13-api-policy-dependency](../../brain/resources/13-api-policy-dependency.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Persist operation IDs, exact proposal bindings, intent and attempted costs before each serial write, and remote IDs/results before the next. Unknown outcomes stop writes. Reconcile known playlists by bounded reads before resuming verified missing items with new approval. Unknown playlist creation without an ID requires human-assisted identification and ownership/content checks; title matching is not an idempotency guarantee. Completed replays return recorded results; stale IDs never silently begin new work.

Issue a fresh immutable resume proposal with a new digest/expiry for the original operation's verified playlist, existing prefix and exact missing suffix. Historical grants remain consumed; at most one new current grant may authorise recovery. Expiry of the original preview does not revive it or prevent a separately revalidated recovery preview. Resume is insert-only on the verified project-created playlist and cannot create another playlist.

Store tokens in a verified protected OS vault and runtime data outside the repository. Expire cache access at 24 hours and remove/refresh API-derived payloads by 30 days. Preserve only minimal non-API replay tombstones or reject stale server-issued operation IDs after payload expiry. Successful disconnect clears account data/tokens and attempts revocation, without restoring project quota. Verify cleanup failures rather than claiming erasure.

Keep fixture mode the default, offline PR CI and separately budgeted/scheduled read-only live checks. Live derived algorithms remain disabled until D-02 is resolved with recorded instructor/provider evidence; live writes additionally require credentials/scopes/channel and trusted exact-proposal approval.

## Consequences

The application provides safe duplicate prevention and disclosed uncertainty, not impossible distributed exactly-once guarantees. Recovery may require a human and cannot automatically repair external edits using excluded playlist editing/deletion. Detailed historical results eventually expire for privacy, so an old replay may yield an expired-result error. External blocks remain visible and do not remove mandatory features from the SRS.

## Verification and links

Requirements: FR-5.6/5.7, FR-6, NFR-02–06, NFR-11, GOV-05. Tasks: A04/A05/A09–A12, P04. Acceptance: AT-08/09/11/12/14/20. Real Issue/PR, cleanup, crash and live evidence: pending. [Full recovery design](../implementation/MASTER_PLAN.md).
