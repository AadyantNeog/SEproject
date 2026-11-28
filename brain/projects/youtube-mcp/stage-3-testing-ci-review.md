---
id: "REVIEW-STAGE-3-TESTING-CI"
type: "review"
title: "Stage 3 testing and CI review"
created: "2026-11-28"
author: "Aadyant, Paul and Jeswin"
status: "pending-review"
sources: ["SDLC_and_Workflow.pdf p. 3, section 7", ".github/workflows/ci.yml", "docs/evidence/release/README.md", "docs/evidence/skills/video-to-playlist.md"]
requirements: ["NFR-08", "SK-05", "SK-06", "GOV-03"]
---

# Stage 3 testing and CI review

## Deliverables and where they are

| Stage 3 deliverable (brief §7) | Evidence |
| --- | --- |
| Continuous testing and CI plan and results | [ci.yml](../../../.github/workflows/ci.yml) runs Ruff, mypy, the offline pytest suite, the wheel build and both validators on Linux and Windows, with a separate Gitleaks job (P2-06, #38; knowledge validation added in #63). [PR #70](https://github.com/AadyantNeog/SEproject/pull/70) recorded 358 passing offline tests. |
| Product skill with test results | [video-to-playlist evaluation](../../../docs/evidence/skills/video-to-playlist.md). It has automated stdio cases plus Codex Desktop runs with the real native dialog (#66, #68). |
| Defect log with regression tests | The defect table in the [release record](../../../docs/evidence/release/README.md#defects-and-regressions-found-in-this-cycle) |
| Review note for each stage | This note and [[stage-2-design-review]]. The Stage 1 note is [[requirements-preparation-review]]. |

## What worked

The stdio tests caught a period comparison that showed zero activity
for sources the server couldn't read.
The fix now has a regression test that fails on the old code. CI could also
exercise the missing-prerequisite paths without any live credentials.
The manual Codex walkthrough caught a mistake in the FR-3 demo notes. The
request was supposed to come back empty because none of the saved videos
met every constraint. [Feature walkthrough](../../../docs/evidence/features/README.md#observed-in-codex-desktop-on-windows)

## What did not work

An NFR-08 timing check failed on a shared Windows runner and passed when
it was rerun. That makes a single run hard to interpret. Gitleaks also
flagged a realistic-looking dummy token, and the replacement PR used an
obviously fake value. Locally, pytest needed a scratch directory the
sandbox could write to before the checks would run. [Timing rerun](https://github.com/AadyantNeog/SEproject/pull/67) · [Secret scan fix](https://github.com/AadyantNeog/SEproject/pull/70)

## What to change next

Decide how timing results from shared runners should affect merges. For
fixtures, use values that are clearly dummy credentials. When a PR fixes a
bug, record it in the defect log and link the regression test in the
same PR.


