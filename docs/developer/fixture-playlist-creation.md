# Simulated guarded playlist creation

P2-04 prepares a server-issued operation for an exact stored preview. It
reserves the full standalone write workflow and claims the operation while
consuming its one-use grant under the SQLite write lock. A consumed grant
cannot be reused if the transaction later rolls back. The service checks
the destination account and current video evidence before dispatch.

One accounted executor sends the approved title, description, and privacy,
then inserts the approved items serially at their exact positions. Each
attempt's planned cost and intent are journaled before dispatch. The
executor debits quota before sending the request. The service saves each
returned remote ID before starting the next write and verifies the full
ordered list at the end.

The simulator runs without YouTube credentials or network access. A definite
refusal after one insertion leaves the operation partial. A timeout after a
simulated insertion leaves it unknown. Both stop further writes and retain
the playlist ID and confirmed prefix. Neither replay starts another write.
The service currently gates live mode.

## Fixture MCP flow

From a fixture server with a project root, start `begin_workflow` with kind
`video_to_playlist`. Pass the returned workflow ID to `get_video`,
`find_similar_videos`, `propose_playlist`, `prepare_creation`, and
`create_playlist`. Use the candidate set and proposal reference returned by
the previous tools. Creation also requires the operation ID returned by
preparation. `get_operation` reads the recorded status with that ID.

All stages use the original reservation. The stage guard binds the exact
proposal and operation to the workflow, then releases unused quota when
creation finishes. A rejected or closed native approval dialog records the
operation as rejected. The stdio regression injects a synthetic decision
only in its test process and checks zero POST dispatches and zero write debits
on rejection and replay. Separate cases check completion and refusal on the
second insertion.

Creation and operation status return the playlist link when an ID is known,
the count and duration in seconds of confirmed insertions, and the ordered
unconfirmed items after partial or uncertain results. An item marked
`unknown` may already exist and requires reconciliation before another
write. The saved operation supplies these details during replay, even after
the original preview expires. The link in fixture mode uses a synthetic ID.
Recovery and supervised resume belong to P2-05.

The wire fields follow the official [playlist creation API](https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert)
and [playlist item insertion API](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert).
Task tracking is in [issue #37](https://github.com/AadyantNeog/SEproject/issues/37).
