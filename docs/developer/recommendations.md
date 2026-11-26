# A2-03 Preference profiles and recommendations

[Issue #14](https://github.com/AadyantNeog/SEproject/issues/14) tracks FR-3. The fixture slice consumes an account-bound `LibrarySnapshot` and a bounded `CandidateSet` from the shared contracts.

## Preference evidence and ranking

- `profile-v1` weights liked videos at 0.50, playlist items at 0.30 and subscribed channel topics at 0.20. Use only retrieved sources with usable text and renormalize their weights. Expose every source's original state and coverage, including denied and empty sources.
- A video shared between likes and playlists contributes one TF-IDF document with both memberships. Repeated playlist occurrences contribute once within that family. Each usable subscribed channel contributes an aggregate document from its description, title and available sampled uploads. Subscription samples supply channel-topic evidence.
- Fit one TF-IDF corpus over the profile and eligible candidates. An explicit topic vector also lives in that corpus. Normalize family centroids and the combined weighted centroid before cosine scoring. Each result names the families and terms that support it. Ties use the video ID.
- Exclude the seed and videos already represented by the retrieved preference evidence. Apply the explicit `topic-v1` threshold, audio-language evidence, and individual duration bounds when requested. With a total-duration budget, take each remaining result in rank order if it fits and report exact selected and unused seconds. A duration filter requires known duration.

## Fixture service and remaining integration

`RecommendationService.search_query` generates up to eight terms from a profile-only fit to prepare bounded discovery. Ranking refits with the actual pool, keeping all vectors for each score in one space. `recommend` checks the current binding and snapshot/candidate expiry, then ranks the supplied pool. Use J2-01's language normalizer through the existing `NormalizeLanguageTag` interface. The service declines to personalize when evidence is empty and asks for a seed or topic. Live execution remains gated by D-02.

The fixture MCP server exposes `recommend_videos` when launched with the checkout root and both bundled inputs. The tool reads a synthetic library snapshot and a bounded synthetic candidate set at their recorded fixture time. For example, send `{"topic":"database indexing","language":"en","total_seconds":720,"max_video_seconds":600}`. The response returns the ordered result, preference reasons, source and candidate coverage, and exact total and unused seconds. Omit `snapshot_id` to use the fixture snapshot. An unknown snapshot, an account override, or a supplied workflow identifier is refused. [Stdio tests](../../tests/system/test_recommendation_stdio.py)

J2-04 supplies the real authorized snapshot, J2-02 supplies candidate hydration, and P2-02 supplies the upstream workflow reservation. Those runtime integrations remain pending. The fixture tests verify source weights, duplicate membership, shared IDF, optional filters, unavailable sources, and account scope. [Recommendation tests](../../tests/unit/test_recommendations.py)
