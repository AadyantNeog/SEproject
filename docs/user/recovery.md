# Recover an interrupted playlist

These steps use the synthetic fixture MCP server. Keep the operation ID returned by `prepare_creation` or `create_playlist`. To inspect a result across a restart, reconnect using the same fixture database.

1. Call `get_operation` with the original operation ID. A completed result gives you the existing playlist URL, item count, and duration. For a partial or unknown result, check the recorded playlist ID and pending items.
2. Call `reconcile_operation` with the original operation ID. It checks the destination channel, ownership, privacy, and exact order of the recorded playlist using bounded reads. If a write may still be running, wait for its deadline and check the operation again. If the playlist differs or cannot be verified within the read limits, inspect it before proceeding.
3. If you get `resume_ready`, review the full preview, including the verified existing items, exact items still missing, destination, privacy, and expiry. Call `resume_operation` with the operation ID and both fields from the preview's `ref`. Approve in the native dialog only if it shows the exact resume you want. The server rechecks privacy before inserting anything and stops if it changed or is unavailable. Rejecting or closing the dialog makes zero writes and clears that preview. Reconcile again for a fresh preview.
4. Review the returned result. If another write is interrupted, reconcile again. Repeating a completed resume returns the stored result. The resume tool can insert missing items only into the recorded playlist.

## When playlist creation itself is uncertain

If there is no recorded playlist ID, identify the exact playlist in the destination account. You can supply its ID as `remote_playlist_id` to `reconcile_operation` for a bounded ownership and contents check. A matching title and candidate ID cannot establish that the original operation created the playlist, so the operation still requires manual resolution. Inspect it directly before deciding what to keep. Avoid starting a separate create while the result is unknown.

Operation details and the original proposal have a retention limit. Once the required detail expires or is purged, recovery cannot continue. Inspect the playlist directly. A replay never starts a new create after expiry.

## Offline verification

The [MCP recovery tests](../../tests/system/test_operation_replay.py) restart the fixture server over stdio with the same SQLite database and use a test approval adapter.

| Fixture case | Expected result | New write attempts |
| --- | --- | --- |
| Interrupted insert is absent and the resume is approved | Add only the missing item and return the same result on replay | One item insert |
| Interrupted insert is absent and the resume is rejected | Keep the playlist unchanged and invalidate the preview | Zero |
| Interrupted insert already landed | Verify both items and complete during reconciliation | Zero |
| The recorded playlist contents differ | Report that the playlist changed | Zero |
| Playlist privacy changed or became unavailable after preview | Refuse to resume even after synthetic approval | Zero |
| Creation is uncertain and the playlist ID is missing | Report that manual resolution is required | Zero |
| Operation details have expired | Report that the operation result expired | Zero |

Live playlist recovery and manual native resume verification remain pending.
