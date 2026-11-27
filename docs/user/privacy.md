# Privacy, Consent, and Local Account Management

Version 1.0 · Owner: Jeswin Jose (J2-03) · Requirements: FR-6, NFR-02, NFR-04, NFR-05, NFR-07

This notice explains how the local **YouTube Video Intelligence MCP Server** (`yt-intel`) handles Google OAuth consent, credential storage, YouTube metadata, AI-client disclosure, retention, and account disconnect.

## 1. Local-Only Architecture and Network Destinations

- The server runs locally on your machine over MCP stdio (`stdout` protocol only; diagnostics on `stderr`) and does not expose a public network listener.
- Outbound HTTPS traffic is restricted by an exact route/method allowlist to:
  - Official YouTube Data API v3 routes on `https://www.googleapis.com/youtube/v3/...`
  - Official Google OAuth token and revocation endpoints on `https://oauth2.googleapis.com/token` and `https://oauth2.googleapis.com/revoke`
- The OAuth browser callback binds strictly to local loopback (`http://127.0.0.1:<ephemeral-port>/oauth2callback`) with PKCE (S256) and CSRF `state` verification. Out-of-band token copy/paste into chat is disabled.

## 2. Least-Privilege OAuth Scopes

| Mode | Command | Requested Scope | Purpose |
| --- | --- | --- | --- |
| Read-only | `yt-intel auth --read` | `https://www.googleapis.com/auth/youtube.readonly` | Read accessible video/channel metadata, liked videos, subscriptions, and owned playlists |
| Playlist creation | `yt-intel auth --enable-writes` | `https://www.googleapis.com/auth/youtube.force-ssl` | Create an explicitly human-approved private/unlisted/public playlist and insert approved items |

- Write scope is requested only when needed and verifies that you sign into the **same bound YouTube channel**; signing into a different channel is rejected with `ACCOUNT_MISMATCH` without overwriting your active credentials.
- Google OAuth sign-in grants API capability only; it **never** authorizes playlist creation. Every playlist write still requires native human approval of the exact stored proposal.

## 3. Protected Credential Storage

- OAuth access and refresh tokens are stored exclusively in a **verified OS-protected credential vault** (such as Windows Credential Manager via `keyring`).
- Plaintext, null, fail, or unverified keyring backends are rejected—the server never silently falls back to plaintext token files.
- Tokens, authorization codes, and client secrets are never stored in SQLite, git repositories, fixtures, brain notes, logs, MCP resources, or tool outputs.

## 4. Data Minimization and AI-Client Disclosure

- Only metadata needed for the requested workflow is retrieved from the official YouTube Data API v3. Watch history, scraping, and unofficial transcript services are excluded.
- When you invoke tools through an MCP client (such as Claude Code), the non-secret tool results you requested (video/channel metadata, rankings, analysis summaries, and playlist previews) are sent to your configured AI client so it can display and discuss them. Credentials and raw OAuth/page tokens are never sent to the AI client.

## 5. Retention Limits

- Cached API metadata expires after **24 hours** by default.
- All locally stored API-derived records (caches, library snapshots, proposals, and detailed operation records) are subject to an absolute **30-day** refresh/deletion ceiling.
- Runtime data is stored in your per-user application data directory (e.g. `%LOCALAPPDATA%\RandomStuff\YouTubeIntelligence\`), partitioned by `fixture` and `live` modes, and never inside the repository checkout.

## 6. Disconnect and Local Deletion

Running `disconnect_account` (or the local disconnect workflow):
1. Stops new workflows for the active account.
2. Attempts best-effort token revocation with Google (`https://oauth2.googleapis.com/revoke`).
3. Deletes stored tokens from the protected OS credential vault.
4. Deletes account-bound local SQLite data (snapshots, proposals, caches, and operation details) while preserving minimal non-secret replay tombstones and project-level quota accounting.

- If revocation or local deletion partially fails, the server reports each status explicitly (`revoked`, `tokens_removed`, `local_data_removed`, `warnings`) and never marks failed local deletion as complete.
- If credential or account-data cleanup remains pending, the saved account stays disabled across restarts. A successful cleanup retry removes the saved account record.
- Disconnecting removes local access and local data only; it **does not** delete any playlists or content on your YouTube account.

Distilled basis: [[08-oauth-and-secret-handling]], [[13-api-policy-dependency]], [[15-implementation-boundaries-and-contracts]].
