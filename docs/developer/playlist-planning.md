# A2-04 Strict playlist planning

[Issue #12](https://github.com/AadyantNeog/SEproject/issues/12) tracks the planner. [ADR-0003](../adr/0003-native-human-approval.md#creation-proposal-digest) specifies the digest for creation proposals.

## Fixture planner

1. Pass structured request fields through `parse_playlist_request`. Missing fields and requests for an exact total return a typed clarification. Durations and the item count are handled in exact seconds. Privacy defaults to private.
2. Resolve the account binding and candidate set in the application. The fixture server can use a saved discovery reference or the bundled synthetic set. The planner checks account ownership and candidate expiry. The current slice rejects live mode under D-02.
3. Use J2-01's language normalizer. Only validated `defaultAudioLanguage` evidence can satisfy the request. A base language matches compatible regional or script forms. Explicit qualifiers must appear in order before extensions, so `en-GB-x-US` cannot satisfy `en-US`. The proposal keeps the raw audio evidence that passed validation.
4. The planner requires available, recorded videos with known positive durations that fit the individual bound. It fits TF-IDF on the topic and the candidates that passed those checks, then requires a cosine of at least `0.10` and an actual token match. It chooses in descending score order with an ascending video-ID tie-break, skipping items that exceed remaining time. The default excludes the seed. Explicit `include_seed` permits the seed only when it is present in the resolved candidate set and passes the same checks.
5. A nonempty proposal lists up to 50 unique videos and includes exact total and unused time, exclusions, coverage warnings and a ten-minute expiry. An empty plan returns `NO_FEASIBLE_PLAYLIST`. A new version uses the prior proposal ID and a fresh digest. `revise` returns the superseded and replacement versions for the future atomic repository call.

## Try the fixture preview

Launch the [fixture server](codex-fixture.md) with `--project-root`, then call `propose_playlist` with the following arguments.

```json
{
  "title": "Indexing for beginners",
  "topic": "database indexing",
  "total_seconds": 720,
  "max_video_seconds": 600,
  "language": "en"
}
```

The tool stores one private proposal in the fixture SQLite database and returns its exact ID, version, digest and rendered preview. The expected video is **Database indexing with B-trees** with 600 seconds selected and 120 seconds unused. The stored proposal expires ten minutes after issuance. To keep a smoke check isolated, add `--fixture-db` with a separate SQLite path when launching the server.

## Preview from discovery

Call `find_similar_videos` with `{"video": "vidIndex002", "limit": 1}`. Pass its returned `candidate_set_id` to `propose_playlist` with topic `database indexing`, `total_seconds` 1800, `max_video_seconds` 1200, and language `en`. The expected video is **B-Tree Database Indexing Deep Dive**, with 1,200 seconds selected and 600 seconds unused. Both calls must use the same fixture database. An unknown or expired explicit reference returns `CONTENT_UNAVAILABLE`. Omitting the reference still selects the bundled fixture set.

The atomic revision and approval-invalidation transaction and the shared workflow reservation still need integration. This tool only saves a local preview. Playlist creation belongs to P2-04.

## Tests

[Playlist planner tests](../../tests/unit/test_playlist_planner.py) cover the SRS example of 6,420 seconds selected and 780 seconds unused under a 7,200-second maximum, rejection at 1,201 seconds, language and topic evidence, a 50-item limit, foreign accounts, expiry, digest changes and deterministic packing across generated inputs. These are fixture checks for part of AT-06, AT-07 and AT-10.

The [stdio test](../../tests/system/test_playlist_planning_stdio.py) checks the exact returned and stored proposal, strict input errors, and zero recorded playlist operations. The [fixture MCP session note](../../brain/projects/youtube-mcp/2026-11-27-a2-04-playlist-preview-stdio.md) records the Codex probe and links to supporting evidence.

The [discovery stdio test](../../tests/system/test_discovery_stdio.py) verifies the handoff across a server restart and rejects foreign or expired references. The [candidate handoff session note](../../brain/projects/youtube-mcp/2026-11-27-a2-02-discovery-candidates.md) records the Codex probe.
