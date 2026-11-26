# A2-04 Strict playlist planning

[Issue #12](https://github.com/AadyantNeog/SEproject/issues/12) tracks the planner. [ADR-0003](../adr/0003-native-human-approval.md#creation-proposal-digest) specifies the digest for creation proposals.

## Fixture planner

1. Pass structured request fields through `parse_playlist_request`. Missing fields and requests for an exact total return a typed clarification. Durations and the item count are handled in exact seconds. Privacy defaults to private.
2. Resolve the official account binding and stored `CandidateSet` in the application. The planner accepts this server context and checks account ownership and candidate expiry. The current fixture slice rejects live mode under D-02.
3. Inject J2-01's language normalizer using a `str -> str | None` adapter once available. The offline tests use a small synthetic adapter. Only validated `defaultAudioLanguage` evidence can satisfy the request. A base language matches compatible regional or script forms. Explicit qualifiers must appear in order before extensions, so `en-GB-x-US` cannot satisfy `en-US`. The proposal keeps the raw audio evidence that passed validation.
4. The planner requires available, recorded videos with known positive durations that fit the individual bound. It fits TF-IDF on the topic and the candidates that passed those checks, then requires a cosine of at least `0.10` and an actual token match. It chooses in descending score order with an ascending video-ID tie-break, skipping items that exceed remaining time. The default excludes the seed. Explicit `include_seed` permits the seed only when it is present in the resolved candidate set and passes the same checks.
5. A nonempty proposal lists up to 50 unique videos and includes exact total and unused time, exclusions, coverage warnings and a ten-minute expiry. An empty plan returns `NO_FEASIBLE_PLAYLIST`. A new version uses the prior proposal ID and a fresh digest. `revise` returns the superseded and replacement versions for the future atomic repository call.

The planner has no network or storage calls. J2-01 parsing, J2-03 account binding, P2-01 persistence, P2-02 reservation and MCP handler integration remain open. Use the A2-06 renderer for the complete preview, and check the proposal's version, digest and expiry in the approval path.

## Tests

[Playlist planner tests](../../tests/unit/test_playlist_planner.py) cover the SRS example of 6,420 seconds selected and 780 seconds unused under a 7,200-second maximum, rejection at 1,201 seconds, language and topic evidence, a 50-item limit, foreign accounts, expiry, digest changes and deterministic packing across generated inputs. These are fixture checks for part of AT-06, AT-07 and AT-10.
