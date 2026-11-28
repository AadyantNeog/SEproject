# Setup, consent, disconnect and recovery

28 November 2026 · J2-07 · Requirements FR-6, NFR-02, NFR-04, NFR-05, NFR-07 · Implementer: Aadyant (transferred from Jeswin, [ADR-0010](../adr/0010-solo-completion-ownership-transfer.md))

This runbook takes a clean checkout to a connected live account, and back
out again. Read [privacy.md](privacy.md) first. It says what is stored,
where, and for how long.

> **Live use is gated.** D-02, which covers the API policy for
> live-derived processing, is unresolved. Until a human records its
> resolution in [d02-status.json](../evidence/policy-and-consent/d02-status.json),
> use live sign-in only to check the account and token lifecycle with an
> authorised test account. The MCP `serve` command still accepts only the
> fixture provider.

## 1. Clean checkout

On Windows, from an empty folder:

```powershell
git clone https://github.com/AadyantNeog/SEproject.git
```

```powershell
cd SEproject
```

```powershell
& 'C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe' -m venv .venv
```

```powershell
& '.venv/Scripts/python.exe' -m pip install --require-hashes -r requirements-dev.lock
```

```powershell
& '.venv/Scripts/python.exe' -m pip install --no-deps --no-build-isolation -e .
```

```powershell
& '.venv/Scripts/python.exe' scripts/check_local.py
```

The last command builds the wheel, runs the offline suite and starts the
fixture server. It spends no live quota. Fixture use needs no Google
account. See the [dependency notes](../developer/dependencies.md) and the
[local-check runbook](../developer/local-check.md).

## 2. Before you consent

You need the following:

- **A test account.** Use an authorised Google test account with a YouTube
  channel, not a personal account.
- **An OAuth client.** Create a Google Cloud *Desktop* OAuth client for a
  project you control. Enable the YouTube Data API v3 on that project.
  Save the client JSON **outside the checkout**, for example in
  `%USERPROFILE%\.config\yt-intel\client_secret.json`. Never commit it,
  paste it into chat, or put it in an MCP client configuration.
- **A protected vault.** The CLI refuses plaintext, file, null or memory
  keyrings. On Windows it uses Windows Credential Manager. Check it with:

  ```powershell
  & '.venv/Scripts/python.exe' -c "from yt_intel.auth.vault import KeyringTokenVault; KeyringTokenVault(); print('protected vault available')"
  ```

## 3. Consent

Read-only consent requests `youtube.readonly` only:

```powershell
& '.venv/Scripts/python.exe' -m yt_intel auth --read --client-secrets "$env:USERPROFILE\.config\yt-intel\client_secret.json"
```

Your browser opens Google's consent page. The callback goes to a loopback
address on this machine, with PKCE and a state check. On success the CLI
prints the bound channel and the granted scopes. Tokens go to the vault,
and the non-secret account record goes to `account-live.json` in your local
application data folder.

To create playlists, request write consent separately with
`--enable-writes`. It must be the same channel, or the CLI rejects it with
`ACCOUNT_MISMATCH`. Write scope only makes a write *possible*. Every
playlist still needs your approval of the exact preview in the native
dialog. Chat text, `confirmed=true` and CLI flags never count as approval.

## 4. What the AI client sees

When you use the server through Codex, Claude Code or another MCP client,
that client receives the tool results you ask for. These include metadata,
rankings, analysis and previews. The client may send them to its model
provider under that client's own terms. Credentials, OAuth tokens and page
tokens are never put in tool results. Retrieved titles, descriptions and
tags are treated as untrusted text. They cannot change approval, quota or
which account is used. Do not ask a client to read your vault or your
client JSON.

## 5. Disconnect

```powershell
& '.venv/Scripts/python.exe' -m yt_intel disconnect --client-secrets "$env:USERPROFILE\.config\yt-intel\client_secret.json"
```

The command does four things:

1. Stops access for the saved account immediately.
2. Asks Google to revoke the token.
3. Deletes the tokens from the vault.
4. Deletes the account's local cached data, snapshots, proposals and
   operation details.

It prints `revoked`, `tokens_removed` and `local_data_removed`. It exits
nonzero unless both deletions succeeded. A failed revocation is reported as
a warning and never hidden.

If a step fails, the saved account stays disabled across restarts. Run the
command again to retry. If revocation failed, also remove the app under
**Google Account → Security → Third-party access**. Disconnect never
deletes playlists on YouTube. It also keeps project quota accounting and
replay tombstones, so a disconnect cannot be used to restore quota or
replay old operations.

## 6. Token recovery

| Symptom | Meaning | Recovery |
| --- | --- | --- |
| `AUTH_REQUIRED` | No saved account, or the account is disconnected | Run `yt-intel auth --read` again |
| `SCOPE_REQUIRED` | The tool needs a scope you did not grant | Run the command it names (`--read` or `--enable-writes`) |
| Refresh fails, or the token was revoked at Google | The saved tokens no longer work | Run `yt-intel disconnect`, then `yt-intel auth --read` |
| `ACCOUNT_MISMATCH` on `--enable-writes` | A different channel signed in | Sign in to the channel you bound first, or disconnect and start again |
| Vault error when reading tokens | The vault entry is missing or corrupt | Run `yt-intel disconnect`, then sign in again. Never copy tokens into a file. |
| Lost or shared machine | Tokens may be exposed | Revoke the app in Google Account settings now, then disconnect on any machine you still control |

## 7. Retention

Cached metadata expires after 24 hours by default. Every API-derived local
record is refreshed or deleted within 30 days. Runtime data lives in your
local application data folder, never in the checkout. See
[privacy.md §5](privacy.md#5-retention-limits).

## 8. Run the live MCP server

After `yt-intel auth --read`, you can connect an MCP client to your real
account. In Codex Desktop, add a second STDIO server, for example
`yt-intel-live`. Use the same command and working directory as the fixture
server, and these arguments:

```text
-m
yt_intel
serve
--provider
live
--project-root
C:\Users\<you>\Desktop\SEproject
```

Add one environment variable: `YT_INTEL_OAUTH_CLIENT_SECRETS`, set to the
path of your client JSON outside the checkout. The server refuses to start
without it.

**Live mode tools.**
- **Live now.** `live_status`, `get_account_status`, `disconnect_account`,
  `get_video` and `get_library`. These are official API reads with bearer
  auth and quota accounting.
- **Gated on D-02.** Similarity, recommendations, analysis and the
  playlist proposal return `POLICY_BLOCKED` with zero API calls until
  D-02 has a recorded resolution in
  `docs/evidence/policy-and-consent/d02-status.json`. Once a reviewed PR
  records it, they run live. Pass the `snapshot_id` from `get_library` to
  `recommend_videos`, and the `candidate_set_id` from
  `find_similar_videos` to `propose_playlist`.
- **No writes.** No live tool can create or change anything on YouTube.
  `propose_playlist` stores a preview only, and `begin_workflow` stays
  unavailable.

Ask the client to call `live_status` to see the current state. See
[ADR-0011](../adr/0011-staged-live-serve-mode.md).

## 9. Scheduled live read-only check

An operator can schedule a fixed-budget read-only check on a protected
runner. See the [readiness record](../evidence/policy-and-consent/README.md).
It sends at most two read requests per run, both within a daily budget of
10 units. It never writes and has no approval path.
