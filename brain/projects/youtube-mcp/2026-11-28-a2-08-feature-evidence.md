---
id: 2026-11-28-a2-08-feature-evidence
type: ai-session
title: A2-08 feature performance and integration evidence
created: 2026-11-28
author: Claude Code (AI-assisted, for Aadyant Neog)
status: pending-review
sources:
  - docs/implementation/PROJECT_STATUS.md
  - docs/implementation/tasks.json
  - docs/evidence/performance/report.md
  - docs/evidence/features/README.md
requirements:
  - FR-1
  - FR-2
  - FR-3
  - FR-5
  - NFR-08
---

## Goal and outcome

The goal was to continue the solo handoff at A2-08, which is Aadyant's own
dependency-ready task. The session started from `main` at `05d929a` on
branch `codex/a2-08-feature-evidence`.

- **Benchmark.** The session added a deterministic 200-candidate NFR-08
  benchmark (`yt_intel.feature_benchmarks`, `scripts/benchmark_features.py`)
  built on P2-07's `measure` harness. A performance test runs it in offline
  CI.
- **Evidence.** The session recorded the feature evidence for FR-1, FR-2,
  FR-3 and FR-5 planning. It updated the video-to-playlist evaluation now
  that the P2-04 and P2-05 handlers are merged.
- **Not taken over.** J2-07, J2-08 and P2-08 were not started. The ownership
  transfer for them still needs a recorded team decision.

## What worked

- **Targets.** All ten measured targets passed with one warm-up and 30
  runs. The highest in-process p95 was 11.45 ms, for recommendation ranking
  over 200 candidates. The highest stdio p95 was 58.12 ms, for
  `find_similar_channels`.
- **Fresh databases.** Each stdio target got its own fixture database. This
  keeps 30 discovery calls inside the fixture search budget, which allows
  about 44 calls a day.

## What failed

- **Sandbox temp folder.** The first `check_local.py` run failed its pytest
  stage. The sandbox denied access to pytest's shared temp folder. Setting
  `TEMP`/`TMP` and `--basetemp` to a scratch folder fixed it. All five local
  check stages then passed.
- **Timeout type.** The first stdio run passed a `timedelta` as
  `read_timeout_seconds`. The installed SDK expects a number.
- **Ruff scope.** `ruff check .` flags older SRS build scripts. CI lints only
  `src`, `tests` and named scripts, so the session used that scope.

## Verification

All checks ran on Windows 11 (16 logical CPUs, 15.6 GiB) with Python
3.13.1.

- **Tests.** The offline suite passed 330 tests at `4c98b2c`.
- **Lint and types.** Scoped Ruff check and format passed. Strict mypy
  passed for both the Windows and Linux platforms.
- **Validators.** `validate_knowledge.py` and
  `validate_implementation_plan.py` passed.
- **Not run.** No live quota was used. No Codex walkthrough, native dialog
  run or human review took place in this session.

Links: [[17-equal-team-allocation]], [[19-owner-ai-assisted-review-and-submitted-srs]].
Issue and PR are pending.
