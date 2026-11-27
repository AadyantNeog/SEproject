# Local check and performance harness

Set up the [locked Python environment](dependencies.md) and run from the
repository root. On Windows:

```powershell
& '.venv/Scripts/python.exe' scripts/check_local.py
& '.venv/Scripts/python.exe' scripts/benchmark_local.py --runs 30
```

On Linux, use `.venv/bin/python` with the same scripts. The local check builds
one wheel in a temporary directory, launches that artifact in a separate MCP
stdio process, calls `get_video` for the bundled synthetic seed, and cleans
up the process and temporary state. The JSON report gives each stage its own
status and the command exits nonzero if any stage fails.

The benchmark records MCP startup separately, then measures one fixture
`get_video` call 30 or more times on the same initialized connection and
fresh temporary fixture database. It performs one warm-up and reports all
samples, their median, and the nearest-rank p95. Both commands use fixture
data and spend zero live quota. Reports exclude response payloads and
server logs.

Feature owners can call `yt_intel.local_checks.measure` with an async
operation that verifies one successful result. Establish the fixture state
before timing, and record the commit, target, software versions, reference
machine including RAM and CPU, and relevant data size alongside the output.
Use an operation that measures the specific NFR-08 acceptance target.
The fixture metadata fetch is a harness smoke check. Input validation,
ranking, proposal construction, and cached reads need their own measurements.
Where live checks are separately authorized, report their provider quota
and network and OAuth time separately.
