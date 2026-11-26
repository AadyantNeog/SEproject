# A2-05 Claude Code fixture shell

This is the record of the early A2-05 client experiment. The selected demo client now uses the [Codex fixture setup](codex-fixture.md).

[Issue #8](https://github.com/AadyantNeog/SEproject/issues/8) tracks the shared shell and later integration. The fixture server exposes read-only tools and resources. It uses the A2-06 renderer for the two synthetic proposal previews.

## Start from a checkout

Install the locked project and editable package using the [Python setup](dependencies.md). From the repository root on Windows, run:

```powershell
$repoPath = (Get-Location).Path
$pythonExe = (Resolve-Path -LiteralPath '.venv/Scripts/python.exe').Path
claude mcp add --transport stdio --scope local yt-intel-fixture -- $pythonExe -m yt_intel serve --provider fixture --project-root $repoPath
claude mcp get yt-intel-fixture
```

`mcp get` reports the connection status for this local entry. The explicit checkout path lets the process find resource files regardless of its working directory. The packaged fixture server can also start without `--project-root`, where it serves `fixture_status` and help alone. [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp#option-3-add-a-local-stdio-server).

| Tool or resource | Purpose |
| --- | --- |
| `fixture_status` | Check fixture availability with an empty argument object. |
| `yt-intel://help` | Explain fixture availability and where to find resources. |
| `yt-intel://fixture/previews/create` | Read the exact synthetic creation preview. |
| `yt-intel://fixture/previews/resume` | Read the exact synthetic recovery preview and insertion order. |
| `yt-intel://skills/brain-ingest` | Read the canonical skill currently available in the checkout. |

With `--project-root`, the two preview resources read the existing JSON examples under `tests/fixtures/contracts`. The server registers only the named preview files and the available canonical skills on its allowlist. Resources are read-only. The native prompt and authority proof belong to P2-03. Product proposal, report and operation routes wait for their account-scoped service handlers.

## Make skills available to Claude Code

Generate the local skill copies from the repository root:

```powershell
& '.venv/Scripts/python.exe' -m yt_intel sync-claude-skills
& '.venv/Scripts/python.exe' -m yt_intel sync-claude-skills --check
```

The command copies the available allowlisted `.agents/skills/<name>/SKILL.md` files to `.claude/skills/<name>/SKILL.md` and prints each verified SHA-256. `--check` compares the copies without writing. Edit the canonical source and sync again when it changes. [Claude Code project skills](https://code.claude.com/docs/en/skills).

## Observed verification

- Claude Code 2.1.143 returned `Connected` for the stdio entry on Windows from an isolated local configuration.
- The offline Python MCP tests invoked `fixture_status`, read both previews and the canonical skill, and checked rejection of unknown resource and tool requests. They also exercised the original fixture-only launch with no project root.
- The Claude Code health check verified the connection. Tool and resource operations were verified with the Python MCP client. Feature routing, real account checks and cancellation integration remain part of the later composition work.
