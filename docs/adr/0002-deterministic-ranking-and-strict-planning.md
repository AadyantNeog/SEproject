# ADR-0002: Explainable ranking and strict playlist constraints

Date: 16 November 2026 · Author: Codex · Status: proposed for human review

Task/ownership references amended 19 November 2026 under [ADR-0006](0006-equal-team-workload-and-shared-integration.md); algorithms/constraints unchanged.

## Context

FR-1/FR-2 require computed similarity, FR-3 authorised preference signals, and FR-5 verifiable topic/duration/language constraints. API metadata can be incomplete. No official related-content endpoint, watched-content claim or exact-fill promise is available to bridge missing evidence.

Distilled basis: [02-metadata-based-similarity](../../brain/resources/02-metadata-based-similarity.md), [03-authorised-preference-signals](../../brain/resources/03-authorised-preference-signals.md), [04-duration-and-language-constraints](../../brain/resources/04-duration-and-language-constraints.md), [16-official-api-design-check-2026-11-16](../../brain/resources/16-official-api-design-check-2026-11-16.md).

## Decision

Use versioned bounded TF-IDF/cosine, documented title/description/tag/category weights, stable ID ties and evidence-bearing reasons. Channel comparisons use a fixed disclosed uploads sample. Recommendation profiles retain likes/playlists/subscriptions as separate weighted families and exclude already-profiled videos by default. No popularity override, remote embedding service or model-generated score is required.

Planning filters eligible candidates before deterministic relevance-first greedy packing in exact seconds. Require known positive duration, availability, non-live status, versioned topic overlap and matching default-audio-language evidence. The text metadata language field does not prove spoken language. Unknown audio language is excluded from strict spoken-language proposals; underfill is reported. Algorithm formulas, threshold and language matching are specified in the master plan, including version-change rules.

## Consequences

Scores are explainable and fixture-repeatable, but metadata relevance is approximate and strict audio evidence reduces the usable pool. Greedy packing does not maximise total runtime or global educational quality, which the SRS does not require. Language cannot be guaranteed beyond API evidence. Changing weights/thresholds requires new fixture evidence and a versioned design update. D-02 still gates affected live-derived processing.

## Verification and links

Requirements: FR-1.1–FR-3.3, FR-5.1–FR-5.3. Tasks: A2-02/A2-03/A2-04, J2-01/J2-02/J2-04; each owner supplies their fixtures/tests. Acceptance: AT-02/03/04/07/10/15. Real Issue/PR/test links and measured ranking results: pending. [Full algorithm specification](../implementation/MASTER_PLAN.md).
