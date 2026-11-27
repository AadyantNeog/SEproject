# Knowledge skills evaluation record (`SK-01`, `SK-02`, `SK-03`, `SK-06`)

Date: 2026-11-27 · Owner: Jeswin Jose (BT2024142) · Task: J2-06 · Mode: offline synthetic & repository check · Review status: pending Aadyant lead review

## Environment

- Runtime: `.venv` Python 3.13.17 on Windows (locked `requirements-dev.lock`)
- Validator: `scripts/validate_knowledge.py`
- Automated test suite: `tests/skills/test_brain_workflows.py`

## Evaluation matrix

| Case | Skill / Requirement | Inputs | Expected behaviour | Observed behaviour | Status |
| --- | --- | --- | --- | --- | --- |
| Live repository baseline | `SK-01`, `GOV-01`, `GOV-02`, `GOV-05` | Repository `brain/`, `.agents/skills/*/SKILL.md`, `docs/adr/*.md`, `AGENTS.md`, `traceability.csv`, `coverage.csv` | At least 10 source-linked research notes, valid YAML frontmatter, unique stems/IDs, all wikilinks and traceability links resolved, all skills and ADRs cite distilled notes | Initial run caught 1 real broken wikilink in `brain/projects/youtube-mcp/2026-11-26-p2-01-storage.md` (`[[05-operation-journal-retention-and-live-gates]]` -> ADR-0005). After `brain-refine` repair, `validate_knowledge.py` passed with 60 notes (19 research), 4 skills, 9 ADRs, 339 wikilinks, 0 issues | PASS |
| `brain-ingest` positive, negative & secret hygiene | `SK-01`, `NFR-02` | Temporary PARA vault with valid new source-linked research note, then unindexed note with empty `sources: []` and synthetic `ya29.` token pattern | Valid ingested & indexed note passes; unindexed note with missing sources and secret pattern fails with `frontmatter`, `unindexed-note`, and `secret-hygiene` issues | `test_sk01_brain_ingest_positive_negative_and_secret_hygiene` passed | PASS |
| `brain-refine` duplicate & broken-link fixture | `SK-02` | Temporary PARA vault containing duplicate stem `01-seed.md` + duplicate `id: RN-01` + broken `[[nonexistent-note]]`, followed by merged canonical note preserving both sources and authors | Validator reports `duplicate-stem`, `duplicate-id`, and `broken-wikilink` before refine; merged note preserving original sources/authors passes after refine | `test_sk02_brain_refine_detects_and_verifies_duplicate_and_broken_link_fixes` passed | PASS |
| `brain-query` requirement trace & unsupported query | `SK-03` | `FR-5.5` traced via `traceability.csv` -> `brain/resources/06-preview-and-human-approval.md` -> `docs/adr/0003-native-human-approval.md`; unsupported query `FR-99.9` | `FR-5.5` resolves to real distilled note and ADR; `FR-99.9` is absent and must be disclosed as unsupported | `test_sk03_brain_query_traces_requirement_to_decision_and_detects_unsupported` passed | PASS |
| MCP resource discoverability | `SK-01`, `SK-02`, `SK-03`, `NFR-01` | Fixture stdio MCP server (`yt-intel serve --provider fixture`) | `yt-intel://skills/brain-ingest`, `yt-intel://skills/brain-refine`, and `yt-intel://skills/brain-query` return exact canonical `SKILL.md` markdown | `test_brain_skills_are_discoverable_as_mcp_resources` passed | PASS |

## Limitations and pending items

- Paul's `P2-06` offline CI workflow (`.github/workflows/ci.yml`) can now invoke `python scripts/validate_knowledge.py` directly once J2-06 merges; this PR does not modify Paul's workflow file without coordination.
- Aadyant's required human lead review remains pending.

Distilled basis: [11-mcp-and-agent-skill-contracts](../../../brain/resources/11-mcp-and-agent-skill-contracts.md), [12-engineering-and-knowledge-workflow](../../../brain/resources/12-engineering-and-knowledge-workflow.md).
