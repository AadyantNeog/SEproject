---
name: local-check
description: Build this checkout, verify a read-only fixture get_video call over MCP, or measure an offline target for project performance evidence.
---

# Local project checks

Use the locked Python 3.13 environment from the checkout. On Windows run
`& '.venv/Scripts/python.exe' scripts/check_local.py` in PowerShell. Report
the JSON statuses separately for build, start, fetch and cleanup. A skipped
stage provides no verification of that stage.

For a timed fixture MCP fetch, run
`& '.venv/Scripts/python.exe' scripts/benchmark_local.py --runs 30`. Keep
startup separate from warm fetch latency. Use the shared timing function
with a target-specific operation when measuring another feature.

Both commands use synthetic fixtures and spend zero live quota. Record
the target, exact commit, reference machine, warm-up and sample counts,
and p95. Compare only the corresponding target to NFR-08. See the
[developer runbook](../../../docs/developer/local-check.md) for the
evidence requirements.

Distilled basis: [engineering and knowledge workflow](../../../brain/resources/12-engineering-and-knowledge-workflow.md)
and [fixture and error cases](../../../brain/resources/10-test-fixtures-and-error-cases.md).
