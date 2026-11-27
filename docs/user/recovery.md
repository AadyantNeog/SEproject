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

## Observe the native resume dialog in Codex

The shipped fixture server never produces a partial result on its own.
To see the real resume dialog, seed one half-finished operation into the
fixture database your MCP client uses:

```powershell
& '.venv/Scripts/python.exe' scripts/seed_resume_fixture.py
```

The script writes to the standard fixture database, which is the one
Codex's `yt-intel-fixture` server uses when no `--fixture-db` is set. Add
`--fixture-db <path>` to target another database. It refuses the live
database.

The script does the following:
1. Creates a private synthetic playlist named "Resume dialog demo".
2. Inserts `vidIndex001` (1,200 s).
3. Records the operation as interrupted before `vidIndex005` (300 s).
4. Prints the operation ID and a prompt for Codex.

It creates no approval.

In Codex, ask the following, using the printed ID:

> Using yt-intel-fixture, reconcile operation `<operation_id>`, show me the resume preview, and resume it if it is ready.

Expected results:
- **Reconciliation.** `reconcile_operation` returns `resume_ready`. The
  verified item is `vidIndex001`, and the missing suffix is `vidIndex005`.
- **Dialog.** `resume_operation` opens the native dialog. Check that it
  shows the resume of exactly that one missing item into the recorded
  playlist.
- **Approve.** The operation becomes `completed` with 2 items and 1,500 s.
- **Reject or close.** The result is `APPROVAL_REJECTED`, nothing is
  written, and the preview is cleared.

Run the script again to get a fresh operation for the other decision.
Before seeding, restart the MCP server in your client so it loads the
current fixture catalogue.

Observed on 28 November 2026 in Codex Desktop, approving and rejecting
once each. See the
[native approval record](../evidence/native-approval/README.md#native-resume-dialog-in-codex-desktop-28-november-2026). The
automated version of this check is
[`test_resume_dialog_setup.py`](../../tests/system/test_resume_dialog_setup.py).

Live playlist recovery remains pending.
