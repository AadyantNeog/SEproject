# MCP tool and resource reference

28 November 2026 · SE-7 developer API documentation · NFR-01

This page documents the tools and resources the server exposes over MCP
stdio. Each tool has a machine-readable input and output schema, which
clients discover with `tools/list`. Every result has the same envelope:

| Field | Meaning |
| --- | --- |
| `mode` | `fixture` (synthetic data) or `live` |
| `status` | `ok`, `empty`, `partial`, `unknown`, `blocked` or `error` |
| `data` | The typed result, or `null` on error |
| `error` | `{code, message, retryable, safe_next_action}` when the call failed |
| `coverage` | Retrieved, usable, inaccessible and unknown counts, plus pagination, sampling, truncation, limits and basis |
| `quota` | The quota profile used, where the call reserved quota |
| `warnings` | Evidence limits the client should show |

The text content is a readable rendering of the same data. Retrieved titles
and descriptions are untrusted text. They cannot change approval, quota or
which account is used.

## Fixture server (`serve --provider fixture`)

These tools use synthetic data only and spend no live quota. "Writes"
means writes to local state or to the simulated YouTube endpoint.

| Tool | Arguments (`?` = optional) | Read-only | Purpose | FR |
| --- | --- | --- | --- | --- |
| `fixture_status` | — | yes | Check the server is available | NFR-01 |
| `get_video` | `video`, `workflow_id?` | yes | Normalised metadata for one video URL or ID | FR-0 |
| `find_similar_videos` | `video`, `limit?` (1–50), `workflow_id?` | no, saves a candidate set | Ranked similar videos with reasons, matched terms, evidence and coverage. Returns `candidate_set_id`. | FR-1 |
| `find_similar_channels` | `channel` (URL, handle or ID), `limit?` | yes | Ranked similar channels from sampled uploads | FR-2 |
| `get_library` | `sources?` (`likes`, `subscriptions`, `playlists`), `continuation_ref?` | yes | Bounded authorised library snapshot with per-source coverage | FR-3, FR-4 |
| `recommend_videos` | `topic?`, `total_seconds?`, `max_video_seconds?`, `language?`, `limit?`, `snapshot_id?` | yes | Recommendations from a saved snapshot, with source-specific reasons | FR-3 |
| `analyse_library` | `snapshot_id?`, `sources?`, `period_a?`, `period_b?` | yes | Top channels and categories, duration bands, and UTC `[start, end)` period comparison over retrieved sources | FR-4 |
| `get_account_status` | — | yes | Non-secret binding and scopes | FR-6 |
| `disconnect_account` | — | no | Remove local account data and tokens | FR-6 |
| `begin_workflow` | `kind` (`video_to_playlist`), `video?` | no | Reserve the whole video-to-playlist quota before the seed fetch | FR-5, NFR-06 |
| `propose_playlist` | `title`, `topic`, `total_seconds`, `max_video_seconds`, `language`, `description?`, `privacy?` (default private), `duration_mode?` (`max`), `include_seed?`, `candidate_set_id?`, `workflow_id?` | no, stores the preview | Exact, immutable, account-bound preview with a digest and a 10-minute expiry. Returns a `yt-intel://proposals/{id}/{version}` link. | FR-5 |
| `prepare_creation` | `workflow_id`, `proposal_id`, `version` | no | Server-issued operation ID for the exact preview | FR-5 |
| `create_playlist` | `workflow_id`, `proposal_id`, `version`, `operation_id` | no | Opens the **native dialog**, then writes with one attempt per write | FR-5 |
| `get_operation` | `operation_id` | yes | Recorded state, confirmed items, duration and pending items | FR-5 |
| `reconcile_operation` | `operation_id`, `remote_playlist_id?` | no | Verifies the recorded playlist and prepares an exact resume preview | FR-5 |
| `resume_operation` | `operation_id`, `proposal_id?`, `version?` | no | Fresh native approval, then inserts only the verified missing suffix | FR-5 |

There is no approval argument and no approval-minting tool. A
`confirmed`, `approved` or `grant` argument is rejected with
`INVALID_INPUT` ([authority tests](../../tests/system/test_playlist_authority.py)).

### Resources

| URI | Content |
| --- | --- |
| `yt-intel://help` | Server help |
| `yt-intel://fixture/previews/create` | Labelled synthetic create preview |
| `yt-intel://fixture/previews/resume` | Labelled synthetic resume preview |
| `yt-intel://skills/{brain-ingest, brain-refine, brain-query, local-check, video-to-playlist}` | The canonical `SKILL.md` text |
| `yt-intel://proposals/{proposal_id}/{version}` | A saved preview, for the current version and active account only |

## Live server (`serve --provider live`)

This mode reads from the real YouTube Data API v3 using the account saved
by `yt-intel auth`. It needs `--client-secrets` or
`YT_INTEL_OAUTH_CLIENT_SECRETS`. See
[ADR-0011](../adr/0011-staged-live-serve-mode.md) and the
[setup guide](../user/setup-and-consent.md).

| Tool | Live behaviour |
| --- | --- |
| `live_status` | Account connected, D-02 state, available and blocked tools |
| `get_account_status`, `disconnect_account` | The real account. Disconnect revokes the token at Google. |
| `get_video`, `get_library` | Official API reads with bearer auth and quota accounting |
| `find_similar_videos`, `find_similar_channels`, `recommend_videos`, `analyse_library`, `propose_playlist` | **D-02 unresolved:** `POLICY_BLOCKED` with zero API calls. **D-02 resolved:** the live handlers run (FR-1 to FR-4, and the FR-5 preview). The record is re-read on every call. |
| `recommend_videos` | Needs a `snapshot_id` from live `get_library` |
| `propose_playlist` | Needs a `candidate_set_id` from live `find_similar_videos`. Stores a **preview only**. |
| `begin_workflow` | `POLICY_BLOCKED` while D-02 is unresolved, then `PROVIDER_UNAVAILABLE`: live workflows end in a write, which is not built |

No write, operation or recovery tool is exposed in live mode.

## Common error codes

| Code | Meaning |
| --- | --- |
| `INVALID_INPUT`, `UNSUPPORTED_IDENTIFIER` | Bad arguments or a non-YouTube URL. Rejected before any provider call. |
| `CLARIFICATION_REQUIRED` | A missing field, or an exact-fill duration request |
| `NO_FEASIBLE_PLAYLIST` | No candidate meets the constraints. Constraints are never relaxed. |
| `CONTENT_UNAVAILABLE` | Private, deleted, foreign or expired content or snapshot |
| `QUOTA_INSUFFICIENT`, `QUOTA_EXHAUSTED` | The budget can't cover the whole workflow, so zero calls are made; or YouTube reported exhaustion |
| `PROVIDER_UNAVAILABLE`, `WORKFLOW_TIMEOUT` | Transient failure after at most 3 read attempts |
| `AUTH_REQUIRED`, `SCOPE_REQUIRED`, `ACCOUNT_MISMATCH` | No account, a missing scope, or a different channel |
| `APPROVAL_REQUIRED`, `APPROVAL_REJECTED`, `APPROVAL_EXPIRED`, `PROPOSAL_CHANGED` | The native decision was absent, rejected, stale or didn't match |
| `OPERATION_CONFLICT`, `OPERATION_UNKNOWN`, `OPERATION_RESULT_EXPIRED` | Wrong operation, an ambiguous write that needs reconciliation, or expired detail |
| `POLICY_BLOCKED` | Live derived processing is disabled until D-02 is resolved |

Generated from `tools/list` on the fixture server, and from `mcp/live.py` and `mcp/live_derived.py` for live mode, on branch `codex/live-derived-handlers`.
