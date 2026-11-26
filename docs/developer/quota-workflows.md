# Quota reservations and workflow start

The dated YouTube quota profile defines endpoint costs in the general and
search buckets. SQLite keeps reservations and debits scoped to the project
and Pacific quota day. Each logical HTTP call uses one call slot. Its retry
attempts share that slot and stop at the plan's per-call ceiling.

When YouTube reports `QUOTA_EXHAUSTED`, the executor records the buckets
charged by that response. New reservations and subsequent debits touching
those buckets fail until Pacific midnight. The marker survives release and
process restart. A request already dispatched when the error arrives can
still finish. Buckets outside the failed endpoint's cost stay available.

The fixture MCP checkout exposes `begin_workflow` with
`{"kind":"video_to_playlist","video":"dQw4w9WgXcQ"}`. It builds the plan on
the server and returns an opaque workflow ID, reserved amounts, and expiry.
Its temporary database is scoped to the fixture server process. The stdio
test checks actual reservation and refusal. It makes no provider calls.

The next MCP integration requires the seed, discovery and proposal handlers
to use the same session and enforce the server's stage and input bounds.
The current fixture proof covers workflow start. Creation and recovery
remain gated by their respective tasks.

Tracking: [issue #26](https://github.com/AadyantNeog/SEproject/issues/26) and
[draft PR #27](https://github.com/AadyantNeog/SEproject/pull/27).
