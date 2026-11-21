---
id: "RN-18"
type: "research"
title: "Team lead review governance"
created: "2026-11-21"
author: "Codex"
status: "distilled"
sources: ["User team-lead review instruction in this chat, 2026-11-21", "docs/requirements/SRS.md GOV-02, GOV-03 and GOV-05", "https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request", "https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners"]
requirements: ["GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05"]
---

# Team lead review governance

## Finding

On 21 November the user identified himself, Aadyant, as team lead and directed that he review all teammate PRs and deliverables. This replaces review rotation; the equal implementation assignment itself was not revoked. GOV-03 still requires real human review, and project history/evidence cannot manufacture human approval.

Official GitHub documentation says a PR author cannot approve their own PR. Its code-owner documentation also explains that any one listed matching code owner's approval can satisfy the code-owner requirement; a list of owners alone is not proof Aadyant must approve teammate work. Both sources accessed 21 November 2026. No repository settings/account identities were verified by reading those documents.

## Project implication

Require Aadyant's actual current-version review for every Jeswin/Paul PR and deliverable. Affected-owner technical input, automated checks and AI feedback remain distinct. Retain independent non-author review for Aadyant-authored/materially coauthored work, with another teammate or eligible independent human. Authors fix findings and resubmit materially changed work; no agent may substitute a model flag for human approval.

Keep the eight-task/56–80-hour implementation baseline per member, but record centralized lead review/coordination and independent review time separately. Do not imply equal total effort after adding this role. Record actual review versions/decisions and verify eventual repository enforcement with real accounts. The detailed local policy is `docs/implementation/REVIEW_POLICY.md` and ADR-0007 outside the vault.

Related: [[12-engineering-and-knowledge-workflow]], [[17-equal-team-allocation]], [[2026-11-21-team-lead-review-update]]. Actual human reviews, Issue/PR links, enforcement and review hours: pending. The user's role instruction is not itself evidence a PR was reviewed or merged.
