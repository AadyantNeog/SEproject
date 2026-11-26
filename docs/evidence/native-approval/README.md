# P2-03 native approval evidence

Status: **Windows desktop/client proof pending** (26 November 2026).

The checked-out environment has WSL Python 3.13 for offline tests, but no
Windows Python 3.13 interpreter or `claude` command on PATH. The fixture stdio
server and both previews are covered by offline MCP integration tests.

## Windows fixture steps

1. In Windows PowerShell at the repository root, set up the locked Python
   3.13 environment and register `yt-intel-fixture` with Claude Code using the
   [fixture shell setup](../../developer/claude-code-fixture.md). Run
   `claude --version` and `& '.venv/Scripts/python.exe' --version` for the record.
2. Start `claude` from that root. Ask Claude Code to read
   `yt-intel://fixture/previews/create` from `yt-intel-fixture` and show the
   synthetic creation preview. Look for **Database indexing practice**.
3. In that Claude Code session, ask it to run
   `.venv/Scripts/python.exe scripts/show_fixture_approval.py` through its
   Windows shell and wait for the result. Tell it that you will operate the
   dialog yourself. If Claude Code asks for shell permission, review the
   command and allow it for this run. If Claude Code cannot start the script,
   record its error and use this command in a second Windows PowerShell at the
   same root to check the desktop helper separately:

   ```powershell
   & '.venv/Scripts/python.exe' scripts/show_fixture_approval.py
   ```

   The script loads the same fixture, refreshes its expiry, and opens
   **YouTube playlist approval** through the production adapter and a temporary
   SQLite database. Verify the account and playlist details against the preview.
   Record which shell launched the helper. A PowerShell launch checks the
   desktop helper. A Claude Code launch also checks the selected client path.
4. Close the dialog with the window's **X**. Record whether it disappears and
   whether the command prints `Dialog rejected or closed. No grant issued.`.
5. Run the same command again, click **Reject**, and record the result
   separately. Both actions are expected to exit with code 0
   (`$LASTEXITCODE` in PowerShell). Record the Windows, Python and Claude versions, and any
   launch failure. Paul performs both dismissal actions manually.

## Observed offline

| Action | Result |
| --- | --- |
| Window close callback | The helper returned `reject`. |
| Reject button callback | The helper returned `reject`. |
| Rejection at the service | The service raised `ApprovalRejected` and did not issue a grant. |
| Valid approval response after a revision was saved | The service refused the old proposal and asked for a new preview. |

Both callback results came from isolated Tk test doubles. The Windows close and
Reject observations remain pending.

Issue: [#16](https://github.com/AadyantNeog/SEproject/issues/16).
Draft PR: [#17](https://github.com/AadyantNeog/SEproject/pull/17), opened
under Paul's GitHub account. Aadyant's human review is pending.
