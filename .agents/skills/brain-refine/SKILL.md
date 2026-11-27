---
name: brain-refine
description: Organise Second Brain notes into PARA, merge duplicate notes while preserving sources and authorship, and repair or report broken links with an auditable history.
metadata:
  version: "0.1.0"
---

# Brain refine

Maintain structural integrity in the repository's PARA Second Brain (`brain/`) by resolving duplicates, misplaced notes, and broken links without losing provenance or authorship.

## Invocation conditions

Use this skill when:
- Notes in `brain/inbox/` are ready to be distilled or moved into `brain/resources/`, `brain/projects/`, `brain/areas/`, or `brain/archive/`.
- Duplicate notes, duplicate filename stems, or duplicate frontmatter `id` values are found.
- `python scripts/validate_knowledge.py` reports broken `[[wikilinks]]`, unindexed notes, or schema issues.

Do not use this skill to rewrite historical outcomes, erase human authorship, or silently delete unresolved evidence.

## Inputs

- Target vault root (default: repository `brain/`) and the current output of `python scripts/validate_knowledge.py` (or a specific list of duplicate/broken-link findings).

## Workflow

1. Run `python scripts/validate_knowledge.py` to establish the exact baseline of schema errors, duplicate stems/IDs, unindexed notes, and broken links.
2. Organise misplaced notes into the correct PARA folder (`inbox/`, `projects/`, `areas/`, `resources/`, `archive/`) while keeping unique filename stems across `brain/`.
3. Merge duplicate notes carefully:
   - Combine findings into one canonical note and preserve every original entry in `sources`, `requirements`, and `author` (record multiple authors honestly rather than overwriting).
   - Preserve historical dates and append a brief refinement/supersession note explaining what was merged, rather than erasing prior history.
   - Update all incoming `[[wikilinks]]`, `brain/index.md`, and traceability references to point to the surviving stem, or retain a clearly marked archive redirect when required.
4. Repair unambiguous broken `[[wikilinks]]` and relative markdown links; report ambiguous or missing targets explicitly instead of guessing.
5. Update `brain/index.md` so every substantive note in `brain/resources/` and `brain/projects/` is listed, and append a factual summary of all changes to `brain/log.md`.
6. Re-run `python scripts/validate_knowledge.py` and confirm zero errors (or report remaining blocked items honestly).

## Output

- Exact list of notes moved, merged, or updated, links repaired or reported as unresolved, updated `brain/index.md` and `brain/log.md`, and before/after `validate_knowledge.py` results.
- Changes committed cleanly on a task branch for normal human-reviewed PR history.

## Failure and boundary behaviour

- Never drop original source citations, dates, or human authorship during a merge.
- Never invent a note or target file to silence a broken link.
- If a broken link refers to an uncreated external Issue/PR or missing deliverable, keep it explicitly marked `pending` and report it.
- Never store credentials or private user data in the vault, and never mark local refinements as human-approved.

Distilled basis: [[12-engineering-and-knowledge-workflow]] and [[11-mcp-and-agent-skill-contracts]].
