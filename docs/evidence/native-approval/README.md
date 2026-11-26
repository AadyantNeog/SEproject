# P2-03 native approval evidence

Status: **Windows PowerShell dismissal verified by Paul. Windows Codex fixture dismissal also passed.**

The Windows checkout uses Python 3.13.0 and Tcl/Tk 8.6.14. The fixture stdio
server and both previews are covered by offline MCP integration tests.

## Windows PowerShell fixture steps

From the repository root, run:

```powershell
& '.venv/Scripts/python.exe' scripts/show_fixture_approval.py
$LASTEXITCODE
```

The helper uses the bundled synthetic creation preview and displays
**YouTube playlist approval**. On the first run, close it with **X**. On the
second run, click **Reject**. For each run, record whether the dialog
disappeared, the terminal output, and the exit code. The expected output is
`Dialog rejected or closed. No grant issued.` with exit code 0.

| Manual Windows action | Observed result |
| --- | --- |
| Window close (X) | Paul reported `Dialog rejected or closed. No grant issued.` and exit code 0 after setting the Tcl/Tk paths. |
| Reject button | Paul reported `Dialog rejected or closed. No grant issued.` and exit code 0 on the corrected rerun. |

Paul's first launch returned `Approval unavailable. native approval helper
failed` with exit code 1, before either dismissal could be observed.
A separate diagnostic reproduced Tcl's failure to find `init.tcl`, although
the Tcl/Tk library files were present under the base Python installation.
Set these paths in the current PowerShell session before retrying:

```powershell
$pythonRoot = & '.venv/Scripts/python.exe' -c 'import sys; print(sys.base_prefix)'
$env:TCL_LIBRARY = Join-Path $pythonRoot 'tcl/tcl8.6'
$env:TK_LIBRARY = Join-Path $pythonRoot 'tcl/tk8.6'
```

With these paths, the headless Tcl initialization check passed and both manual
dismissal runs returned the expected output. An intermediate Reject attempt
used `venv` instead of `.venv` and returned `CommandNotFoundException` before
launching Python. Paul corrected the path and reran the check.

## Selected-client verification

The team selected Codex Desktop for the Windows demo. The [Codex fixture runbook and results](../../developer/codex-fixture.md#observed-on-windows) record the successful stdio preview read and both manual dismissal outcomes. The product write workflow still requires separate verification.

## Earlier Claude Code integration steps

A teammate with Windows Claude Code access can run this separate check.

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
| Consumption after a revision was saved following grant issuance | The service raised `InvalidGrant` for the original proposal and grant. |

Both offline callback results came from isolated Tk test doubles. Paul's
Windows PowerShell results are recorded separately above.

Issue: [#16](https://github.com/AadyantNeog/SEproject/issues/16).
Draft PR: [#17](https://github.com/AadyantNeog/SEproject/pull/17), opened
under Paul's GitHub account. Aadyant's human review is pending.
