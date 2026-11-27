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
The MCP server uses the same fixture database as standalone tools. Set
`--fixture-db` to choose a separate database for a fixture run. Session IDs
are local to the server process, while SQLite retains quota spend across
restarts. The standalone workflow-start test checks reservation and refusal
with no provider calls.

## Handler integration

The MCP server composes one `FixtureWorkflowRuntime` for workflow start,
discovery and preview. `begin_workflow` uses `runtime.service` and discovery
debits `runtime.ledger`. Keep the account binding and cancellation token
server owned. Use the standalone path when no workflow ID is supplied.

| Owner | Handler | Use of the shared session |
| --- | --- | --- |
| Jeswin | `get_video` | Production handler wiring is pending. Normalize the video with `parse_video_id`, enter the `get_video` stage with `video=seed`, then fetch using `access.context`. |
| Aadyant | `find_similar_videos` | Enter the discovery stage with the same normalized seed. Use `access.context` for provider calls. After storing the candidate set, assign its server-issued ID to `access.candidate_set_id`. |
| Aadyant | `propose_playlist` | Enter the preview stage with the returned candidate set ID. Load the account-bound candidate set and build the preview inside the stage. |

For example, the seed handler wraps its existing service call this way:

```python
async with runtime.service.stage(
    workflow_id,
    "get_video",
    binding=active_binding,
    request_id=request_id,
    cancellation=cancellation,
    video=seed,
) as access:
    result = await fetch_seed(access.context, seed)
```

Let service errors propagate out of the context manager before rendering the
MCP error response. A successful stage advances the workflow. A failed stage
closes it and releases unused quota. Cancelling the next valid stage also
releases the reservation immediately, including when cancellation arrives
before the handler starts. An invalid account, stage, seed or candidate
reference is refused before the handler runs. The reservation
retains its original expiry and remains available for the future creation
stages after a successful preview.

The stdio integration test uses a test-only seed adapter with the real
fixture provider and ledger. It calls the registered discovery and preview
tools, checks order and candidate ownership, and verifies that one SQLite
reservation recorded the complete fixture spend. A full MCP walkthrough
still needs `get_video` wired to the seed stage. Creation and recovery have
their own handler integration tasks.

Tracking: [issue #26](https://github.com/AadyantNeog/SEproject/issues/26) and
[quota ledger PR #27](https://github.com/AadyantNeog/SEproject/pull/27).
