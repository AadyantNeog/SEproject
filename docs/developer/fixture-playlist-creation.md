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

The next integration connects the MCP execution handlers to the application
service and uses the original composed reservation for operations started
from a workflow. That depends on the shared workflow and fixture provider
composition. Recovery and supervised resume belong to P2-05.

The wire fields follow the official [playlist creation API](https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert)
and [playlist item insertion API](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert).
Task tracking is in [issue #37](https://github.com/AadyantNeog/SEproject/issues/37).
