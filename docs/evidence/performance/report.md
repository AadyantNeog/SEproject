# NFR-08 performance report

28 November 2026 · AT-17 · A2-08 feature targets · Issue pending · PR pending

## Result

**All five NFR-08 feature targets passed on fixtures** at commit
[`4c98b2c`](https://github.com/AadyantNeog/SEproject/commit/4c98b2c865893323707fb7d33e0c778e3d039778).
The working tree had no tracked changes. Every target had one warm-up and 30
measured runs, and every sample checked its own result. The runs used only
synthetic data and spent zero live quota. The raw report holds every sample:
[2026-11-28-a2-08-features.json](2026-11-28-a2-08-features.json).

| Target | NFR-08 bound | Median | p95 | Result |
| --- | --- | ---: | ---: | --- |
| Input validation of FR-1–FR-5 fields, in process | p95 ≤ 100 ms | 0.02 ms | 0.03 ms | Pass |
| Similar-video ranking, 200 candidates | ≤ 2 s | 8.90 ms | 9.09 ms | Pass |
| Similar-channel ranking, 200 videos in 20 channels | ≤ 2 s | 8.77 ms | 9.05 ms | Pass |
| Recommendation ranking, 200 candidates, three sources | ≤ 2 s | 10.82 ms | 11.45 ms | Pass |
| Proposal construction from 200 candidates | ≤ 2 s | 4.25 ms | 4.48 ms | Pass |

The SRS gives a single bound for ranking and proposal construction. This
report checks the p95 against that bound, which is stricter than checking
the median.

### Fixture tools through MCP stdio

These calls ran through a real `yt_intel serve --provider fixture`
subprocess. Each tool had its own temporary fixture database and quota
ledger. The times include JSON-RPC transport, fixture provider reads and
SQLite quota accounting. They use the shipped fixture catalogue, so they
are smaller than the 200-candidate workload above. They are held to the same
bounds as an end-to-end check.

| Tool and input | Checked output | Median | p95 | Bound |
| --- | --- | ---: | ---: | --- |
| `find_similar_videos` `{"video": "https://youtu.be/vidIndex001", "limit": 1}` | Ranked `vidIndex002` | 38.51 ms | 45.14 ms | ≤ 2 s |
| `find_similar_channels` `{"channel": "https://www.youtube.com/@SystemsStudyLab"}` | Ranked `UCbbbbbbbbbbbbbbbbbbbbbb` | 52.28 ms | 58.12 ms | ≤ 2 s |
| `recommend_videos` on a saved likes snapshot, `en`, 1,300 s | Ranked `vidIndex001` | 29.19 ms | 30.37 ms | ≤ 2 s |
| `propose_playlist` on `fixture-recommendations`, 720 s total, 600 s per video, `en` | `fixture0301`, 600 s | 9.24 ms | 10.68 ms | ≤ 2 s |
| `find_similar_videos` `{"video": "https://example.com/watch?v=vidIndex001"}` | `UNSUPPORTED_IDENTIFIER` | 0.71 ms | 0.88 ms | p95 ≤ 100 ms |

## Reference machine

| Item | Value |
| --- | --- |
| OS | Windows 11 Home Single Language, build 10.0.26300, AMD64 |
| CPU | Intel64 Family 6 Model 186 Stepping 2 (as Python reports it), 16 logical CPUs |
| Memory | 15.6 GiB |
| Python | 3.13.1, locked `.venv` |
| NFR-08 minimum of 4 cores and 8 GB | Met |

The benchmark records its own environment. It reports logical CPUs, not
physical cores. The machine also ran its normal desktop load during the run.

## Workload

The in-process workload is deterministic and generated in
[`feature_benchmarks.py`](../../../src/yt_intel/feature_benchmarks.py).

- **Candidates.** There are 200 synthetic videos over eight vocabulary
  topics. They mix audio languages (`en`, `en-US`, `en-GB`, `fr` and
  unknown), category IDs (two known and one missing), durations from 120 to
  1,499 s, and unknown durations. Some have no tags.
- **Channels.** The same 200 videos are split across 20 channels. A separate
  seed channel has 10 videos.
- **Preferences.** A snapshot holds 40 likes, a 30-item playlist and 10
  subscriptions, each with a 5-video sample. That is 120 profile videos
  across all three sources.
- **Proposal.** The request asks for `database indexing` with up to 7,200 s
  total and 1,200 s per video, in English. It produced 14 items totalling
  6,994 s.
- **Validation.** One pass parses two video URLs, two channel references, a
  result limit, a language tag and a playlist request. It also checks that
  an off-host URL, a limit of 51 and a string `total_seconds` are refused.

## Not covered here

- **Cached reads.** The cached-read target (p95 ≤ 2 s) is part of J2-08 read
  evidence and is still pending.
- **Live latency.** Live network and OAuth latency were not measured. Live
  checks remain gated on D-02 and the live prerequisites. A fixture run is
  not live evidence.
- **Benchmark harness.** The `get_video` smoke benchmark in
  [local-check.md](../../developer/local-check.md) is P2-07's harness check.
  It is a separate measurement.

## Reproduce

From the repository root on Windows:

```powershell
& '.venv/Scripts/python.exe' scripts/benchmark_features.py --runs 30 --output docs/evidence/performance/2026-11-28-a2-08-features.json
```

The command exits nonzero if any target misses its bound. It also exits
nonzero if any sample returns an unexpected result. The
[performance test](../../../tests/performance/test_local_targets.py) runs
the same report in offline CI and checks every target.

Human owner review is pending. This report was prepared with AI assistance
and is not a review record.
