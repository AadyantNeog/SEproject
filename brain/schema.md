# Brain note schema

Each substantive note has YAML frontmatter with `id`, `type`, `title`, `created`, `author`, `status`, `sources`, and `requirements`. Allowed types are `research`, `decision`, `ai-session`, and `review`. Status describes evidence maturity, not approval: use `distilled`, `recorded`, or `pending-review`.

Research notes explain the finding, its implication, and related notes. Cite a supplied PDF by repository-relative path and verified page, or use an exact external URL with access date. Session notes also include goal, outcome, what worked, what failed, and verification. Never store credentials or real private YouTube account data.

Use unique filename stems for `[[wikilinks]]`. Requirement IDs match the SRS. Issues and PRs are pending until real URLs exist. Folder purposes: inbox is unprocessed; projects is active work; areas is ongoing responsibilities; resources is distilled reference; archive is inactive work.
