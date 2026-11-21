# Python dependencies

A2-01 targets CPython 3.13. The Windows development interpreter is 3.13.1. The [project manifest](../../pyproject.toml) declares dependency ranges and the exact MCP SDK and build backend versions. Install the published locks for reproducible runs.

| Dependency | Use |
| --- | --- |
| `mcp==2.3.0`, `mcp-types==2.3.0`, `anyio==4.16.0`, `pydantic==2.14.4` | Stdio SDK, protocol types, asynchronous tests and strict DTOs |
| HTTPX, Google Auth and Google Auth OAuthlib | Official YouTube transport and operator OAuth for the assigned provider tasks |
| `keyring` and `tzdata` on Windows, `platformdirs`, Pydantic Settings | Protected vault integration, Pacific timezone data and local settings for the assigned infrastructure tasks |
| Hatchling, `editables`, `build`, pip-tools | Build and resolve the Windows reference environment |
| pytest, pytest-cov, Hypothesis, Ruff, mypy, PyYAML | Project checks and the existing implementation-plan validator |

The locked SDK exposes `MCPServer`, `CallToolResult` with structured and text content, and the `ClientSession.initialize()` handshake. The stdio smoke uses the `2025-11-25` handshake required by the SRS. The manifest preserves the SDK's Windows-only `pywin32` marker through pip-tools generation. [Versioned SDK source](https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0) · [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25).

## Windows setup and fixture checks

Create a local environment with your Python 3.13 interpreter. In PowerShell, using that environment:

```powershell
& '.venv/Scripts/python.exe' -m pip install --require-hashes -r requirements-dev.lock
& '.venv/Scripts/python.exe' -m pip install --no-deps --no-build-isolation -e .
& '.venv/Scripts/python.exe' -m pytest -m 'not live'
& '.venv/Scripts/python.exe' -m ruff check src tests
& '.venv/Scripts/python.exe' -m ruff format --check src tests
& '.venv/Scripts/python.exe' -m mypy src
& '.venv/Scripts/python.exe' -m build --wheel --no-isolation
```

For a wheel install, install `requirements.lock` with `--require-hashes` in a separate Python 3.13 environment, then install the resulting wheel with `--no-deps`. Start stdio with `python -m yt_intel serve --provider fixture` or `yt-intel serve --provider fixture` from that environment. Connect an MCP client over stdin and stdout.

Repository-wide Ruff checks currently flag the existing SRS and planning scripts. The A2-01 lint and format results cover `src` and `tests`.

## Regenerating locks

Refresh both locks together in a coordinated dependency change. With the dev environment active, run:

```powershell
pip-compile --generate-hashes --strip-extras --allow-unsafe --no-emit-index-url --no-emit-trusted-host --pip-args '--only-binary=:all:' --output-file requirements.lock pyproject.toml
pip-compile --generate-hashes --strip-extras --allow-unsafe --no-emit-index-url --no-emit-trusted-host --pip-args '--only-binary=:all:' --constraint requirements.lock --extra dev --output-file requirements-dev.lock pyproject.toml
```
