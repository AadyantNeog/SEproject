---
name: brain-ingest
description: Capture supplied project material, verified research, and significant AI sessions as linked notes in this repository's Second Brain.
metadata:
  version: "0.2.0"
---

# Brain ingest

Capture project material, verified research, and significant AI work into the repository's PARA Second Brain (`brain/`) while preserving source provenance and honest authorship.

## Invocation conditions

Use this skill when:
- Supplied course material, specifications, or verified external documentation need to be distilled into `brain/resources/`.
- Raw unprocessed inputs are added to `brain/inbox/`.
- Significant AI-assisted implementation, review, or verification work needs an `ai-session` note in `brain/projects/youtube-mcp/`.

Do not use this skill to fabricate sources, invent human authorship, or claim PR review/approval.

## Inputs

- Source material (repository-relative path + verified page, or exact external URL + access date) or an observed AI work session with actual commands and results.
- Applicable SRS requirement IDs (e.g. `FR-4.1`, `SK-01`, `GOV-01`) and real Issue/PR URLs when they exist (otherwise `pending-url`).

## Workflow

1. Read `brain/schema.md` and `brain/index.md` before writing. Preserve all existing human authorship and historical records.
2. Choose the right PARA destination:
   - Unprocessed inputs -> `brain/inbox/`
   - Distilled reference findings (one useful finding per note) -> `brain/resources/`
   - Active project session, baseline, or review records -> `brain/projects/youtube-mcp/`
3. Add valid YAML frontmatter with `id`, `type` (`research`, `decision`, `ai-session`, or `review`), `title`, `created`, `author`, `status` (`distilled`, `recorded`, or `pending-review`), `sources`, and `requirements`.
   - Attribute AI-authored notes to the actual AI tool/model used, never to a human team member.
   - Distinguish verified source facts, project decisions, and unverified/pending risks.
   - Never store credentials, OAuth tokens, or private user YouTube data.
4. For `ai-session` notes, record Goal, Outcome, What worked, What failed or remains unverified, Verification (actual commands and observed outputs only), and Links.
5. Link related notes with unique-stem `[[wikilinks]]`, add the new note stem to `brain/index.md`, and append the actual operation and result to `brain/log.md`.
6. Run `python scripts/validate_knowledge.py` to verify schema compliance, unique stems, wikilinks, and index coverage.

## Output

- The created or updated note(s) under `brain/`, updated `brain/index.md` and `brain/log.md`, and the actual `validate_knowledge.py` output.
- A concise handoff noting any pending Issue/PR/review links.

## Failure and boundary behaviour

- If a source cannot be verified, label it explicitly as unverified rather than treating it as established fact.
- If `validate_knowledge.py` reports broken links, duplicate stems, or schema errors, fix them before committing.
- Keep changes on a task branch until the reviewed PR workflow completes; never label a local edit reviewed, approved, submitted, or merged.

Distilled basis: [[12-engineering-and-knowledge-workflow]], [[11-mcp-and-agent-skill-contracts]], and [[01-project-problem-and-scope]].
