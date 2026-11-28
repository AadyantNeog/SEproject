# Policy, consent and live-read readiness

28 November 2026 · J2-07 · Implementer: Aadyant (transferred from Jeswin, [ADR-0010](../../adr/0010-solo-completion-ownership-transfer.md)) · Issue pending · PR pending

## Summary

**Live reads are prepared but blocked.** The scheduled workflow, the check
and the runbooks exist and pass offline tests. No live request has been
sent. D-02 is unresolved, and no protected runner or test account has been
recorded. A blocked prerequisite is not a passed acceptance case.

## Readiness

| Prerequisite | Owner | State | Observable evidence needed |
| --- | --- | --- | --- |
| D-02 policy applicability | Aadyant, with the instructor or provider | **Unresolved** | The instructor's or provider's written direction, linked from [d02-status.json](d02-status.json) by a human in a reviewed PR |
| Authorised test account and channel | Aadyant | **In use (28 November 2026)** | Aadyant authorised his own YouTube account, added as an OAuth test user. The address and channel ID stay out of the repository. See the [live read evidence](../live/README.md). |
| Google Cloud project and Desktop OAuth client | Aadyant | **Created (28 November 2026)** | One project with YouTube Data API v3 enabled. The consent screen is in Testing mode. The Desktop client JSON is stored outside the checkout. |
| OS-protected vault | Aadyant | **Backend detected on the development workstation** | `KeyringTokenVault()` found `keyring.backends.Windows.WinVaultKeyring` on 28 November 2026. Nothing was stored. The runner needs its own check. |
| Protected self-hosted runner | Aadyant | **Not provisioned** | A runner with labels `self-hosted, windows, yt-intel-live-read`. A `live-read-only` environment with required reviewers. Repository variables `YT_INTEL_LIVE_READ_ENABLED=true` and `YT_INTEL_LIVE_CHECK_VIDEO=<authorised public video ID>`. On the runner, `YT_INTEL_OAUTH_CLIENT_SECRETS` points outside the checkout, and `yt-intel auth --read` has been completed. |
| Fixed quota budget | Aadyant | **Configured** | [live-read-check-2026-11-28.json](../../../config/quota-profiles/live-read-check-2026-11-28.json) sets a daily budget of 10 general units for project `live-read-check`. Each run reserves 6 units and spends at most 2. |

## What the check does

[`live_read_check.py`](../../../src/yt_intel/live_read_check.py) runs from
[`live-read-only.yml`](../../../.github/workflows/live-read-only.yml). The
workflow runs weekly on Mondays at 03:17 UTC, or on manual dispatch. It
never runs on pull requests and holds no repository secrets.

1. **Readiness job.** It runs on a GitHub-hosted runner. It reads the D-02
   record and the two repository variables, writes a prerequisite table to
   the job summary, and marks the run **Blocked** unless all three are met.
2. **Live job.** It runs only when the readiness job reports ready, on the
   protected runner and behind the `live-read-only` environment. Before it
   touches the vault, the network or the ledger, it checks five gates:
   - the explicit enable flag
   - a recorded D-02 resolution with an `https` evidence link
   - a valid video ID
   - the OAuth client file
   - a saved account with `youtube.readonly` that is not pending disconnect

   Next it reserves the full worst case, 2 calls × 3 attempts, from the
   fixed budget. It then sends `channels.list?mine=true` to check that the
   saved binding still matches, and `videos.list` for the test video.
3. **Report.** It holds gate results, the attempt count, budget figures,
   whether the binding matched, and the video's availability and
   language-evidence type. It never holds tokens, titles or descriptions.
   Exit codes are 0 for ok, 3 for blocked and 1 for a failed read.

## Offline verification

[`tests/integration/test_live_read_check.py`](../../../tests/integration/test_live_read_check.py)
uses mocked Google transports and an in-memory vault. It shows that:

- every gate blocks with zero requests and no database
- the repository D-02 record is unresolved, so it blocks
- three runs succeed with exactly 2 reads each
- the fourth run on the same quota day is refused with `QUOTA_INSUFFICIENT`
  and zero requests
- a wrong channel is a failed check
- `yt-intel disconnect` revokes the token, empties the vault, removes the
  saved record and makes the check block again
- a failed revocation is reported as a warning while local deletion still
  completes

## Running it locally

On a provisioned runner, after the prerequisites are met:

```powershell
$env:YT_INTEL_LIVE_READ_CHECK = '1'
$env:YT_INTEL_LIVE_CHECK_VIDEO = '<authorised public video ID>'
& '.venv/Scripts/python.exe' scripts/live_read_check.py --output live-read-report.json
```

Without the prerequisites, the command prints a `blocked` report and exits 3.

## Related

- **Runbook.** [Setup, consent, disconnect and recovery](../../user/setup-and-consent.md)
- **Privacy notice.** [privacy.md](../../user/privacy.md)
- **Policy dependency.** [policy dependency note](../../../brain/resources/13-api-policy-dependency.md)

Prepared with AI assistance. Aadyant's human owner review is pending.
