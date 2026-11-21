# A2-01 Foundation handoff

[GitHub issue #1](https://github.com/AadyantNeog/SEproject/issues/1) tracks the foundation. The shared schema is version `1`. Its MCP protocol baseline is `2025-11-25`. The [shared contracts](../implementation/CONTRACTS.md) describe the full product, including feature-owned stages.

| Consumer | Shared interfaces |
| --- | --- |
| Provider, library and account | [`provider.py`](../../src/yt_intel/contracts/provider.py), [`account.py`](../../src/yt_intel/contracts/account.py), [`LibrarySnapshot`](../../src/yt_intel/contracts/models.py), [`RequestContext`](../../src/yt_intel/contracts/workflow.py) |
| Quota and repositories | [`WorkflowPlan` and `QuotaLedger`](../../src/yt_intel/contracts/workflow.py), [repository and expiry protocols](../../src/yt_intel/contracts/repositories.py) |
| Approval and writes | [`PlaylistProposal` and `ResumeProposal`](../../src/yt_intel/contracts/proposals.py), [`ApprovalAdapter` and `ApprovedWriteContext`](../../src/yt_intel/contracts/approval.py) |
| Tools and client | [`ResultEnvelope` and `ErrorDetail`](../../src/yt_intel/contracts/errors.py), [fixture stdio smoke](../../tests/system/test_stdio_protocol.py) |

The [synthetic JSON examples](../../tests/fixtures/contracts/) cover a video, library snapshot, creation proposal, recovery proposal and typed quota refusal. Use `model_validate_json` for serialized data. Python constructors expect typed values, including tuples for ordered collections. Maps are copied and exposed as immutable views. UTC timestamps use explicit offsets and durations use integer seconds. The example digests are synthetic. A2-04 owns canonical proposal digest generation and topic/language eligibility, and P2-03/P2-04 own trusted approval and guarded writes.

Jeswin's interface input covers provider normalization, source coverage and account/vault lifecycle. Paul's covers reservation and debit semantics, expiry, operation claims and the native decision boundary. Record their input against the foundation PR and coordinate any shared changes before consumers merge. The [review policy](../implementation/REVIEW_POLICY.md) describes Aadyant's exact-version human owner review.

The initial server exposes the read-only `fixture_status` tool and `yt-intel://help`. It starts in fixture mode and uses no credentials or YouTube requests. The `get_video` handler, selected-client demonstration, native approval and live behavior belong to the later tasks in the [team workplan](../implementation/TEAM_WORKPLAN.md).

## Windows verification

- Python 3.13.1 installed the hash-pinned development lock and the editable package.
- All 19 offline tests passed, including a separate MCP stdio subprocess using the `2025-11-25` handshake. This supplies fixture evidence for AT-01.
- Ruff lint and format checks passed for `src` and `tests`. The repository-wide check flags the pre-existing SRS and planning scripts. Strict mypy passed for all 14 source files.
- The no-isolation wheel build succeeded. A second environment installed the runtime lock offline and passed `pip check` and the packaged `yt-intel` console entry point stdio smoke.
- The planning validator passed 34 checks, including the protected SRS artefact hashes. Linux execution, CI and live acceptance remain pending.
