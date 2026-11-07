---
id: "RN-08"
type: "research"
title: "OAuth and secret handling"
created: "2026-11-07"
author: "Codex"
status: "distilled"
sources: ["https://developers.google.com/identity/protocols/oauth2/native-app", "https://developers.google.com/identity/protocols/oauth2", "Project_1_YouTube_MCP.pdf p. 2"]
requirements: ["FR-6", "NFR-02", "NFR-04", "NFR-05", "NFR-07"]
---

# OAuth and secret handling

## Finding

Google documents installed-app authorisation using a browser, PKCE and loopback redirects. Refresh tokens can stop working, and external apps in Testing with YouTube scopes normally receive seven-day refresh tokens.

## Project implication

Request read capability separately from write capability when possible. Store tokens through OS protection, never in chat or the repository. Handle failed refresh with re-authorisation, and provide disconnect and local deletion. OAuth capability does not replace proposal-specific approval.

## Sources

- https://developers.google.com/identity/protocols/oauth2/native-app (accessed 7 November 2026)
- https://developers.google.com/identity/protocols/oauth2 (accessed 7 November 2026)
- Project_1_YouTube_MCP.pdf p. 2 (supplied brief)

## Related notes

[[06-preview-and-human-approval]]; [[13-api-policy-dependency]].

Issues and PRs: pending; no external work item is claimed.
