# Changelog

All notable changes to the YouTube Video Intelligence MCP Server. Entries
name the task ID and the actual author of the work. Fixture evidence and
live evidence are reported separately. There is no tagged release yet.

## Unreleased: merged to `main` at `061932d`, 28 November 2026 (PRs #57 to #63, not tagged)

Implemented by Aadyant with AI assistance (Claude Code). Owner review is
pending. J2-07, J2-08 and P2-08 were transferred from Jeswin and Paul by
team decision ([ADR-0010](docs/adr/0010-solo-completion-ownership-transfer.md)).

### Added

- **Live evidence.** Live FR-1 to FR-4 and the FR-5 preview ran in Codex
  Desktop against the real API. The record includes quota totals and
  three ranking-quality observations.
- **D-02 (ADR-0012).** D-02 is resolved by Aadyant's team-lead
  decision, recorded in `d02-status.json` with
  `basis: "team-lead-decision"`. It is not instructor or provider
  evidence. Live derived tools now run for the team's own authorised
  accounts. Live writes are not covered.
- **Release (ADR-0011 step two).** Live derived handlers for
  `find_similar_videos`, `find_similar_channels`, `recommend_videos`,
  `analyse_library` and a preview-only `propose_playlist`, in
  `mcp/live_derived.py`. They run only while the reviewed D-02 record is
  resolved. The shared services take an injected `DerivedProcessingCheck`
  whose default stays fixture-only. D-02 itself is still unresolved, so
  nothing changes in practice until a human records it.
- **A2-08.** An NFR-08 feature benchmark (`scripts/benchmark_features.py`)
  with a deterministic 200-candidate workload and MCP stdio targets. Also a
  feature evidence record and the now-automated video-to-playlist
  end-to-end fixture cases.
- **J2-07.** The `yt-intel disconnect` command, a fixed-budget live
  read-only check (`scripts/live_read_check.py`) and a weekly
  `live-read-only.yml` workflow gated on recorded prerequisites. Also a
  setup, consent, disconnect and recovery runbook, and the policy and
  consent readiness record.
- **J2-08.** Stdio read-path tests: exact FR-4 totals, UTC boundaries,
  denied and sparse sources, typed read failures, retention and disconnect.
  Also cached-read benchmark targets.
- **P2-08.** Stdio write, authority and quota acceptance tests, using a
  shared launcher with isolated test seams. Also the write, quota and
  recovery evidence.
- **Release.** Knowledge validation in offline CI, an as-built architecture
  and ER page, the release requirement trace and the release-candidate
  record.

### Changed

- Planning version 2.3 records the ownership transfer. The validator checks
  review rules by implementer and accepts real issue and PR links.
- `coverage.csv` now links real issues and PRs for merged tasks.

### Fixed

- Period comparison no longer reports denied, unavailable or unrequested
  library sources as zero activity (J2-08).

## Merged to `main` before 28 November 2026

- **Aadyant.** A2-01 to A2-07: contracts, ranking, recommendations,
  planning, MCP composition, presentation and the product skill.
  PRs #2, #3, #7, #9, #11, #13, #15, #20, #24, #25, #30–#35, #44, #47, #48.
- **Jeswin.** J2-01 to J2-06: parsing and accounted HTTP, the read
  provider, OAuth and the vault, library collection, analytics and the
  knowledge skills. PRs #19, #23, #29, #41, #46, #50.
- **Paul.** P2-01 to P2-07: SQLite storage, quota, native approval, guarded
  creation, recovery, offline CI and the local check. PRs #5, #17, #27,
  #38, #39, #43, #52.
