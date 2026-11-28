# ADR-0012 Resolve D-02 by team-lead decision

Date: 28 November 2026 · Decided by: Aadyant Neog (team lead) · Prepared by: Claude Code, at his direction · Status: pending human owner review

## Context

D-02 asks whether the YouTube developer policy's limits on derived metrics
and data apply to this project's live use. The SRS recorded it as an
external dependency. Research note RN-13 recommended getting instructor or
provider clarification before live derived use.

- **The brief requires the derived features.** It says teams compute
  similarity themselves with simple techniques such as TF-IDF and cosine
  similarity, and it requires recommendations and engagement analysis.
- **YouTube does not block the calls.** The official API serves the
  metadata. The block was only the project's own gate.
- **The live derived handlers exist.** ADR-0011 step two built them behind
  that gate.

On 28 November 2026 Aadyant decided, as team lead, not to seek instructor
confirmation and to resolve D-02 for the project's own use.

Distilled basis: [API policy dependency](../../brain/resources/13-api-policy-dependency.md).

## Decision

D-02 is resolved for this project by a **team-lead decision**, recorded in
[d02-status.json](../evidence/policy-and-consent/d02-status.json) with
`basis: "team-lead-decision"`.

This is not instructor or provider evidence, and no document may describe
it as instructor approval.

The resolution covers only the following:
- **Accounts.** The team's own authorised test accounts, signed in through
  the project's OAuth client.
- **Processing.** Derived processing is computed locally for the person who
  asked for it: similarity, recommendations, analysis and playlist planning.
  Nothing is published, shared or sold.
- **Data rules.** The existing rules stay in force:
  - official API v3 only
  - the 24-hour cache and 30-day refresh or deletion
  - disconnect deletes the account's local data
  - the quota ledger
  - no plaintext tokens
- **Writes.** It does not cover live writes. Live playlist creation still
  needs the native human approval path, and that path is not built in live
  mode.

## Consequences

- **What changes.** The live server now runs FR-1 to FR-4 and the FR-5
  preview for the signed-in account.
- **Known deviation.**
  - The submitted SRS (§13.2) and RN-13 name the instructor or the provider
    as who resolves D-02.
  - This decision departs from that, and the release record says so.
  - Graders may question it.
  - Compliance with YouTube's developer policies is the team's own
    responsibility.
- **Reversible.** If the instructor or provider objects, set the record back
  to `unresolved` in a PR. The gate re-reads the record on every call, so
  live derived tools stop at once with zero API calls.

Requirements FR-1 to FR-5, NFR-05. Issue #56.
