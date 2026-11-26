# A2-02 Metadata ranking and bounded discovery

[Issue #10](https://github.com/AadyantNeog/SEproject/issues/10) tracks FR-1 and FR-2. The versioned rules follow [ADR-0002](../adr/0002-deterministic-ranking-and-strict-planning.md) and the [master plan](../implementation/MASTER_PLAN.md).

## Scoring

- Normalize with Unicode NFKC and casefolding. Keep Unicode word tokens, `C++`, `C#`, and dotted versions. Remove the small stop-word set in `domain/ranking.py` and discard tokens longer than 64 characters. Use up to 256 title characters, 2,000 description characters, and the first 32 tags capped at 128 characters each.
- Count video title terms three times, description terms once, and tag terms twice. Fit TF-IDF on the seed and the deduplicated candidate pool. Use `1 + ln(count)` for TF and `1 + ln((1 + N)/(1 + df))` for IDF. Normalize each vector to unit length and compute its cosine with the seed. Zero text overlap excludes a candidate even when the categories match.
- `ranking-v1` combines 90% text cosine and 10% exact category match when both categories are known. It uses text alone when either category is unknown. Reasons identify terms with the strongest contribution, and warnings disclose missing seed and candidate evidence.
- `channel-ranking-v1` counts channel title terms three times and adds the description and the weighted documents for usable sample videos. A channel needs supporting description or sample text. Compute one cosine per channel without a category adjustment. Rank both result types by descending unrounded score and ascending stable ID.

## Discovery and integration

`DiscoveryService` takes the existing `YouTubeReadProvider` and a server-issued `RequestContext`. The default discovery limits are four search pages of up to 50 hits, 200 unique video candidates, 10 unique channel candidates, and one uploads page of up to five entries per sampled channel. Queries use up to eight distinct normalized terms. Duplicate candidates and the seed are filtered before hydration. An uploads sample uses accessible entries in returned order, with omitted and unknown evidence tracked in coverage. Search coverage describes the bounded discovery loop. Raw continuation tokens stay inside the service.

The fixture slice accepts normalized IDs and channel references. Jeswin's shared parser will supply those values at the tool boundary. J2-02 will supply the real fixture/read adapter and P2-02 will supply the composed reservation before the first read. Tool registration and the account-bound candidate-set handoff remain open for that integrated route. The service currently rejects live mode before calling the provider because D-02 remains unresolved.

The tests use synthetic protocol dependencies. [Ranking tests](../../tests/unit/test_metadata_ranking.py) check topical mismatches, ties, exact term weights, missing evidence, and a hand-calculated cosine. [Discovery tests](../../tests/integration/test_ranking_discovery.py) check caps, provider call order, one-page channel sampling, and typed preflight refusals. These tests provide fixture evidence for part of AT-02, AT-03, and AT-10.
