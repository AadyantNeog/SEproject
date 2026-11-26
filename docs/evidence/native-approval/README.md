# P2-03 native approval evidence

Status: **pending Windows desktop/client proof** (26 November 2026).

The checked-out environment has WSL Python 3.13 for offline tests, but no
Windows Python 3.13 interpreter or `claude` command on PATH. The fixture stdio
server and synthetic creation/recovery preview are covered by offline MCP
integration tests. The native Tk helper's close path is tested with an isolated
test double; the native confirmation control was not clicked.

To complete the proof on Paul's Windows checkout after installing the project's
locked environment and making Claude Code available in that shell, follow
[`claude-code-fixture.md`](../../developer/claude-code-fixture.md), invoke the
fixture preview resource, then request the P2-03 native dialog through the
application adapter. Paul must verify the complete preview and manually handle
the dialog. Record the Windows version, Python/Claude versions, fixture
resource observed, helper process/dialog outcome and any failure here. Do not
claim proof from `claude mcp get` alone; it establishes only the MCP connection.

Issue: [#16](https://github.com/AadyantNeog/SEproject/issues/16).
Draft PR: [#17](https://github.com/AadyantNeog/SEproject/pull/17), opened
under Paul's GitHub account. Aadyant's human review is pending.
