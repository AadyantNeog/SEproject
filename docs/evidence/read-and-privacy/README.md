# Read-path, analytics and privacy evidence

28 November 2026 · J2-08 · FR-4, FR-6, NFR-02, NFR-04, NFR-05, NFR-06, NFR-08 (cached reads) · Implementer: Aadyant (transferred from Jeswin, [ADR-0010](../../adr/0010-solo-completion-ownership-transfer.md)) · Issue pending · PR pending

This record covers the read side on the fixture provider. Requests travel
MCP stdio → library and analysis services → the quota-accounted HTTP
executor → API-shaped fixture dispatch, with state in real SQLite and the
persistent quota ledger. The live read side is gated separately. See the
[policy and consent readiness](../policy-and-consent/README.md). No live
result is claimed.

## Automated evidence

All cases are in
[`test_sparse_and_denied_sources.py`](../../../tests/system/test_sparse_and_denied_sources.py),
with prior coverage in [`test_analysis.py`](../../../tests/system/test_analysis.py)
and [`test_library_sources.py`](../../../tests/integration/test_library_sources.py).
The expected values are hand-calculated from the
[library catalogue](../../../tests/fixtures/libraries/library_catalog.json).

### FR-4 known totals

| Quantity | Hand calculation | Observed |
| --- | --- | --- |
| Likes | libVid00001 (600 s) and libVid00003 (1,200 s) | 2. Mean and median 900 s. Timestamp basis `like_event_timestamps_unavailable`. |
| Playlists | First 3 of 4 owned playlists. pli-101, pli-102 (deleted), pli-201 and pli-301 | 3 selected, 4 occurrences, 3 unique, 1 inaccessible. The 4th playlist is reported as truncated. |
| Playlist runtime bands | 600 → [300,900). 900 and 1,200 → [900,1800). | `[300,900)=1`, `[900,1800)=2`, others 0 |
| Combined videos | {1,3} ∪ {1,2,3} | 3 unique, overlap 2, likes-only 0, playlists-only 1. Subscription-sample video libVid00004 excluded (1). |
| Channels and categories | One video each from channels UCaaa, UCbbb and UCccc. Categories counted from the catalogue. | Match |
| Subscriptions | UCbbb… created 2026-09-20T10:00Z | 1 channel |
| Period A Sep vs period B Nov | Subscription in A. All 4 playlist additions in B. | Subscriptions 1 → 0, −100%. Additions 0 → 4, change undefined (zero baseline). Likes trend unavailable, and publication dates are not substituted. |

### UTC boundaries `[start, end)`

| Period | Observed |
| --- | --- |
| A ends exactly at the subscription instant, 09-20T10:00Z | 0 subscriptions. The end is excluded. |
| B runs from 11-01T10:00Z (pli-101) to 11-04T10:00Z (pli-301) | 3 additions. The start is included and the end excluded. |
| One-second periods starting exactly at each instant | 1 and 1. The start is included. |
| Empty periods in 2025 | 0 and 0, with a "no events" note and percent change undefined |

### Denied and sparse sources

| Case | Observed |
| --- | --- |
| `subscriptions.list` returns 403 `insufficientPermissions` | Subscriptions show as `denied` with no coverage, plus a library warning. Analysis warns that the source was denied. The period comparison covers only `likes` and `playlists`, and subscription creations are `null`. |
| `get_library {"sources": ["likes"]}` | The other two sources are `not_requested`. Analysis gives two "not requested" warnings. Playlist additions and subscription creations are `null`. Combined videos are 2, all from likes. |

**Defect found and fixed in this task.** Before the fix,
`compare_periods` reported a denied or unrequested source as `0 → 0`
with the note "No supported timestamped events fell inside either
comparison period". That presented missing evidence as zero activity.
The fix compares only sources the snapshot actually retrieved, and warns
about not-requested sources as well as denied ones. A regression test
fails on the old code and passes on the fix. A unit test covers denied,
unavailable and not-requested states.

### Read failures, retries and accounting

| Fault on `videos.list` | Error | Attempts recorded |
| --- | --- | --- |
| HTTP 503 three times | `PROVIDER_UNAVAILABLE`, retryable | 3, the ceiling |
| Timeout three times | `WORKFLOW_TIMEOUT` | 3 |
| 403 `quotaExceeded` | `QUOTA_EXHAUSTED`, not retried | 1. The next call is refused with zero new attempts. |
| One 503, then success | Video returned | 2 |

A full `get_library` recorded exactly 11 accounted attempts:
- `videos.list` ×4: two likes pages plus two hydrations
- `playlistItems.list` ×4
- `subscriptions.list` ×1
- `playlists.list` ×1
- `channels.list` ×1

Each later `analyse_library` on the stored snapshot added zero attempts.

### Retention and disconnect

| Case | Observed |
| --- | --- |
| Snapshot past `retained_until` | `analyse_library` returns `CONTENT_UNAVAILABLE` |
| `disconnect_account` | `local_data_removed=true` and `tokens_removed=true`. `revoked=false`, because the fixture account has no remote token. |
| After disconnect | `get_account_status` returns no account. `get_library`, `analyse_library` and a second disconnect return `AUTH_REQUIRED`. The `snapshots` and `accounts` tables are empty. |
| Quota after disconnect | Every recorded attempt is kept. Disconnect does not refund quota. |

The live `yt-intel disconnect` command, with revocation, vault deletion and
the failed-revocation report, is covered in
[`test_live_read_check.py`](../../../tests/integration/test_live_read_check.py)
(J2-07).

## Cached-read performance (NFR-08)

The cached-read target is p95 ≤ 2 s. Two stdio targets measure it:
`analyse_library` on a stored snapshot, and re-reading a saved proposal
preview resource. The benchmark asserts that no provider attempt happens
during the samples. Results are in the
[performance report](../performance/report.md).

## Not covered

- **Live reads.** No live read or analysis was run. Live-derived analytics
  is refused with `POLICY_BLOCKED` until D-02 is resolved.
- **Personal records.** Jeswin's own reflection for his merged J2-01–J2-06
  work is his to write.
- **Owner review.** Aadyant's human owner review of this change is pending.

Prepared with AI assistance.
