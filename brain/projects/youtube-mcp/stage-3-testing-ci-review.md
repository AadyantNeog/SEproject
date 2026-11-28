---
id: "REVIEW-STAGE-3-TESTING-CI"
type: "review"
title: "Stage 3 testing and CI review"
created: "2026-11-28"
author: "Claude Code draft for the team; human authors pending"
status: "pending-review"
sources: ["SDLC_and_Workflow.pdf p. 3, section 7", ".github/workflows/ci.yml", "docs/evidence/release/README.md", "docs/evidence/skills/video-to-playlist.md"]
requirements: ["NFR-08", "SK-05", "SK-06", "GOV-03"]
---

# Stage 3 testing and CI review

> **Draft.** This lists facts recorded in the repository. The team should
> rewrite the judgements in their own words and sign them. It is not a
> human review.

## Deliverables and where they are

| Stage 3 deliverable (brief §7) | Evidence |
| --- | --- |
| Continuous testing and CI plan and results | [ci.yml](../../../.github/workflows/ci.yml) runs Ruff, mypy, the offline pytest suite, the wheel build, both validators and Gitleaks, on Linux and Windows (P2-06, #38; knowledge validation added in #63). The offline suite has 358 tests on `main`. |
| Product skill with test results | [video-to-playlist evaluation](../../../docs/evidence/skills/video-to-playlist.md). It has automated stdio cases plus Codex Desktop runs with the real native dialog (#66, #68). |
| Defect log with regression tests | The defect table in the [release record](../../../docs/evidence/release/README.md#defects-and-regressions-found-in-this-cycle) |
| Review note for each stage | This note and [[stage-2-design-review]]. The Stage 1 note is [[requirements-preparation-review]]. |

## What worked (facts to reflect on)

- **Tests caught a real defect.** The denied-source period comparison bug
  (D-2026-11-28-1) was found by a stdio test and fixed. The regression test
  fails on the old code.
- **Prerequisites fail closed.** Live and policy prerequisites block
  cleanly, so CI never needed credentials.
- **Real-client runs agreed with the tests.** The manual Codex runs matched
  the automated expectations. One mismatch, FR-3, was a wrong expectation,
  not a product fault.

## What did not work (facts to reflect on)

- **Timing test on shared runners.** The NFR-08 timing test failed once on
  GitHub's shared Windows runner (PR #67), then passed on a re-run. A
  decision on how CI should treat timing bounds is still open.
- **Secret scan scope.** Gitleaks flagged a random-looking fake token in a
  test (PR #69). Because CI scans all branches, the superseded branch had
  to be deleted before the replacement PR (#70) passed.
- **Sandbox temp folder.** Local checks failed in the agent sandbox until
  pytest's temp folder was redirected. This was an environment problem,
  not a product one.

## What to change (for the team to decide)

- Choose how CI treats NFR-08 timing: advisory on shared runners, a
  separate job, or strict.
- Use plainly fake, low-entropy placeholders for test credentials.
- Record each new defect in the defect log in the PR that fixes it.

Related: [[2026-11-28-release-candidate-assembly]], [[10-test-fixtures-and-error-cases]].
