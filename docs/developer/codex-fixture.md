# A2-05 Codex Desktop fixture setup

[Issue #8](https://github.com/AadyantNeog/SEproject/issues/8) tracks the MCP shell and client setup. Run from a Windows checkout with the [locked Python 3.13 environment](dependencies.md). The fixture server exposes synthetic previews, canonical skill text and the read-only `fixture_status` tool.

## Connect Codex Desktop

In **Settings → MCP servers**, add a local **STDIO** server named `yt-intel-fixture`. Set the command to the absolute path to the checkout's `.venv\Scripts\python.exe`. Add these as separate arguments, replacing the last line with the absolute checkout path:

```text
-m
yt_intel
serve
--provider
fixture
--project-root
C:\path\to\SEproject
```

Save and restart as prompted. In the project chat, ask Codex to read `yt-intel://fixture/previews/create` from `yt-intel-fixture`. It should show the synthetic **Database indexing practice** playlist. Codex also discovers project skills from `.agents/skills/` in the checkout. [Local MCP configuration](https://developers.openai.com/codex/mcp) · [Codex skills](https://developers.openai.com/codex/skills)

## Reproduce the fixture check

Run the probe against the installed Windows Codex executable. It starts a separate app server, discovers tools, reads the creation preview and skill resource, and exits. It uses an isolated SQLite state directory and runs without a model turn.

```powershell
$codexExe = (Get-Command codex.exe).Source
& '.venv/Scripts/python.exe' scripts/check_codex_fixture.py --codex $codexExe
```

For the manual Windows dialog check, use a checkout containing Paul's [P2-03 launcher](https://github.com/AadyantNeog/SEproject/pull/17), and add `--dialog` to that command. In this mode the same local fixture server temporarily exposes a diagnostic tool that calls the bundled synthetic launcher. Codex's shell and computer-use tools are disabled. Verify the displayed playlist and destination on each run, then close the first window with **X** and choose **Reject** on the second. Each run should report `No grant issued` and exit code 0. The diagnostic works entirely with fixture data and a temporary database.

## Observed on Windows

On 26 November 2026, Codex Desktop `0.171.0-alpha.13.2` on Windows build `26300` read the creation preview and canonical `brain-ingest` resource from Paul's PR #17 at `d583793`, using Python 3.13.1 and Tcl 8.6.15. The fixture launcher returned exit code 0 and `No grant issued` for both Close and Reject. This is fixture evidence. Live permissions and the product write workflow require their own verification.
