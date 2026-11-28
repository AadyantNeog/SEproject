# ADR-0011 Stage live serve mode behind D-02

Date: 28 November 2026 · Author: Claude Code, for Aadyant Neog · Status: pending human owner review

## Context

Stage 4 needs a live demonstration in a client, but `yt-intel serve`
offered only the fixture provider. The live pieces already existed
separately:
- the OAuth sign-in and vault (J2-03)
- the accounted executor (J2-01)
- the read provider (J2-02)
- the ledger (P2-02)
- the native approval (P2-03)
- the guarded writes (P2-04 and P2-05)

The MCP handlers were written against fixture bindings and providers.
D-02 remains unresolved, and the official developer policy restricts
derived metrics and data. Similarity, recommendations, analysis and the
playlist workflow built on similarity are all derived processing.

Distilled basis: [API policy dependency](../../brain/resources/13-api-policy-dependency.md)
and [OAuth and secret handling](../../brain/resources/08-oauth-and-secret-handling.md).

## Decision

- **Live composition.** `yt-intel serve --provider live` builds a separate
  live composition in [`mcp/live.py`](../../src/yt_intel/mcp/live.py). It
  uses the saved account from `yt-intel auth`, its OS-protected vault, a
  bearer-authenticated accounted executor, the persistent ledger (project
  `default-project`, shared with the CLI) and the official read provider.
- **Startup.** The server refuses to start without an OAuth client file.
- **Non-derived tools work live.** These are `live_status`,
  `get_account_status`, `disconnect_account`, `get_video` and
  `get_library`.
- **Derived tools refuse.** `find_similar_videos`, `find_similar_channels`,
  `recommend_videos`, `analyse_library`, `begin_workflow` and
  `propose_playlist` are registered so a client gets a typed refusal.
  - **D-02 unresolved:** they return `POLICY_BLOCKED` with zero provider
    calls.
  - **D-02 resolved:** they return `PROVIDER_UNAVAILABLE` until their live
    handlers exist. They never fall back to fixtures.
- **One D-02 rule.** [`policy.py`](../../src/yt_intel/policy.py) checks the
  reviewed D-02 record, shared with the scheduled live check. No tool
  argument, flag or model output can change it.
- **No live writes.** No write, operation or recovery tool is exposed in
  live mode.

## Consequences

- **What can be demonstrated.** The account lifecycle, metadata reads and
  library retrieval can be shown live with an authorised test account,
  once one exists.
- **Remaining step.** The derived FR-1 to FR-5 handlers still need a live
  path if D-02 is resolved. That step generalises the fixture handlers
  around an injected runtime, using live candidate storage and planning
  bound to the real account. It also adds live writes through the native
  dialog. Until then, the Stage 4 live demo of FR-1 to FR-5 is reported as
  blocked, not passed.
- **Fixture behaviour is unchanged.**

## Amendment: step two (28 November 2026)

Status: pending human owner review.

- **One injected check.** Discovery, recommendations, analysis, planning
  and candidate storage used to hard-code fixture-only checks. They now
  take a `DerivedProcessingCheck`
  ([`domain/derived.py`](../../src/yt_intel/domain/derived.py)). Its
  default, `fixture_only`, keeps the old behaviour.
- **Live check.** The live composition passes `recorded_policy_check`
  from `policy.py`. It allows a live binding only while the reviewed D-02
  record is resolved, re-reading the record on every call.
- **Live handlers.** When the record is resolved,
  [`mcp/live_derived.py`](../../src/yt_intel/mcp/live_derived.py) runs:
  - `find_similar_videos` and `find_similar_channels` (FR-1, FR-2)
  - `recommend_videos` from a live `get_library` snapshot (FR-3)
  - `analyse_library` (FR-4)
  - a preview-only `propose_playlist` from a live candidate set (FR-5
    planning)

  Each handler reserves its bounded worst case before the first call, under
  `default-project`. Tool handlers check the record before any provider
  call, and the services check it again.
- **Superseded for creation.** ADR-0013 adds `begin_workflow` and live
  creation through the native dialog. Live recovery is still not built.
- **Was not built at step two.** `begin_workflow`, live creation through the native
  dialog, and live recovery. The live FR-5 creation demo stays blocked.
- **D-02 is unchanged.** It is still unresolved. Nothing runs live until a
  human records the instructor's or provider's direction through a reviewed
  PR.

Requirements NFR-01, NFR-02, NFR-05, FR-1 to FR-5, FR-6. Issue #56.
