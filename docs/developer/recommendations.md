# A2-03 Preference profiles and recommendations

[Issue #14](https://github.com/AadyantNeog/SEproject/issues/14) tracks FR-3. The fixture slice consumes an account-bound `LibrarySnapshot` and a bounded `CandidateSet` from the shared contracts.

## Preference evidence and ranking

- `profile-v1` weights liked videos at 0.50, playlist items at 0.30 and subscribed channel topics at 0.20. Use only retrieved sources with usable text and renormalize their weights. Expose every source's original state and coverage, including denied and empty sources.
- A video shared between likes and playlists contributes one TF-IDF document with both memberships. Repeated playlist occurrences contribute once within that family. Each usable subscribed channel contributes an aggregate document from its description, title and available sampled uploads. Subscription samples supply channel-topic evidence.
- Fit one TF-IDF corpus over the profile and eligible candidates. An explicit topic vector also lives in that corpus. Normalize family centroids and the combined weighted centroid before cosine scoring. Each result names the families and terms that support it. Ties use the video ID.
- Exclude the seed and videos already represented by the retrieved preference evidence. Apply the explicit `topic-v1` threshold, audio-language evidence, and individual duration bounds when requested. With a total-duration budget, take each remaining result in rank order if it fits and report exact selected and unused seconds. A duration filter requires known duration.

## Fixture service

`RecommendationService.search_query` generates up to eight terms from a profile-only fit to prepare bounded discovery. Ranking refits with the actual pool, keeping all vectors for each score in one space. `recommend` checks the current binding and snapshot/candidate expiry, then ranks the supplied pool. Use J2-01's language normalizer through the existing `NormalizeLanguageTag` interface. The service declines to personalize when evidence is empty and asks for a seed or topic. Live execution remains gated by D-02.

Call `get_library` and pass its `snapshot_id` to `recommend_videos`. The recommendation tool resolves the snapshot for the active synthetic account, preflights search and hydration against the same SQLite quota ledger as library reads, and ranks the bounded candidate pool from the fixture provider. Missing, foreign, or expired references are rejected before search. Disconnect clears the saved account data and blocks further use of that snapshot.

Omit `snapshot_id` to run the bundled example at its recorded fixture time. With either input, the response includes the ranked results, preference reasons, source and candidate coverage, and exact total and unused seconds for a duration budget. [Stdio tests](../../tests/system/test_recommendation_stdio.py) · [Ranking tests](../../tests/unit/test_recommendations.py)
