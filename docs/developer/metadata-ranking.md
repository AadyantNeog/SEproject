# A2-02 Metadata ranking and bounded discovery

[Issue #10](https://github.com/AadyantNeog/SEproject/issues/10) tracks FR-1 and FR-2. The versioned rules follow [ADR-0002](../adr/0002-deterministic-ranking-and-strict-planning.md) and the [master plan](../implementation/MASTER_PLAN.md).

## Scoring

- Normalize with Unicode NFKC and casefolding. Keep Unicode word tokens, `C++`, `C#`, and dotted versions. Remove the small stop-word set in `domain/ranking.py` and discard tokens longer than 64 characters. Use up to 256 title characters, 2,000 description characters, and the first 32 tags capped at 128 characters each.
- Count video title terms three times, description terms once, and tag terms twice. Fit TF-IDF on the seed and the deduplicated candidate pool. Use `1 + ln(count)` for TF and `1 + ln((1 + N)/(1 + df))` for IDF. Normalize each vector to unit length and compute its cosine with the seed. Zero text overlap excludes a candidate even when the categories match.
- **Links (v2).** Before tokenising, `ranking-v2` and `channel-ranking-v2` remove every `http://`, `https://` or `www.` link, so URL fragments are never matched terms. Otherwise they keep the v1 rules below.
- `ranking-v2` combines 90% text cosine and 10% exact category match when both categories are known. It uses text alone when either category is unknown. Reasons identify terms with the strongest contribution, and warnings disclose missing seed and candidate evidence.
- `channel-ranking-v2` counts channel title terms three times and adds the description and the weighted documents for usable sample videos. A channel needs supporting description or sample text. Compute one cosine per channel without a category adjustment. Rank both result types by descending unrounded score and ascending stable ID.

## Discovery and integration

`DiscoveryService` takes the existing `YouTubeReadProvider` and a server-issued `RequestContext`. The default discovery limits are four search pages of up to 50 hits, 200 unique video candidates, 10 unique channel candidates, and one uploads page of up to five entries per sampled channel. Queries use up to eight distinct normalized terms. Duplicate candidates and the seed are filtered before hydration. An uploads sample uses accessible entries in returned order, with omitted and unknown evidence tracked in coverage. Search coverage describes the bounded discovery loop. Raw continuation tokens stay inside the service.

With a checkout supplied as `--project-root`, the [Codex fixture server](codex-fixture.md) registers `find_similar_videos` and `find_similar_channels`. Both use Jeswin's identifier parser and API-shaped fixture provider. The SDK exposes an output schema for the structured ranking and coverage, and the server also returns rendered text.

| Tool | Example arguments | Expected first result |
| --- | --- | --- |
| `find_similar_videos` | `{"video": "https://youtu.be/vidIndex001", "limit": 1}` | PostgreSQL B-Tree Index Scan Tuning, 1,201 seconds, audio language unknown |
| `find_similar_channels` | `{"channel": "@SystemsStudyLab", "limit": 1}` | Query Craft, with one usable video from its returned uploads page |

`find_similar_videos` also returns `candidate_set_id` beside the ranked results. The fixture SQLite cache keeps the full usable discovery pool for 24 hours under the synthetic account. The display limit still controls how many ranked results are shown. The stored pool keeps the seed when there is room under the candidate cap, so planning can consider it on explicit request. The ranking still excludes the seed.

Standalone fixture discovery reserves the full search, seed, hydration and applicable sampling costs through the SQLite quota ledger before its first provider call. Both tools price their endpoint ceilings from the configured profile. The fixture transport stays synthetic. Cancelling an in-flight provider read releases unused quota and skips candidate publication. The [playlist planning walkthrough](playlist-planning.md#preview-from-discovery) shows how to pass the saved reference. The composed playlist session is tracked in [issue #26](https://github.com/AadyantNeog/SEproject/issues/26). Live ranking stays blocked pending D-02.

### Progress and cancellation

Clients that request MCP progress receive three updates as discovery loads the seed, collects candidate metadata and completes ranking. Video discovery reports completion after the candidate reference is saved. For a request cancelled before that save, the server stops the in-flight read and closes the fixture provider. The same MCP session remains available for another request. [Stdio checks](../../tests/system/test_discovery_stdio.py)

[Ranking tests](../../tests/unit/test_metadata_ranking.py) check topical mismatches, ties, exact term weights, missing evidence, and a hand-calculated cosine. [Discovery tests](../../tests/integration/test_ranking_discovery.py) check caps, provider call order, one-page channel sampling, and typed preflight refusals. [Stdio tests](../../tests/system/test_discovery_stdio.py) exercise both published tools and check coverage, sampling, and typed errors. These tests provide fixture evidence for part of AT-02, AT-03, and AT-10.

The [fixture MCP session note](../../brain/projects/youtube-mcp/2026-11-27-a2-02-discovery-stdio.md) records the Windows Codex probe and links to the distilled ranking and client references.
