# NFR-08 performance report

28 November 2026 · AT-17 · A2-08 feature targets and J2-08 cached reads · Issue pending · PR pending

## Result

**All twelve NFR-08 targets passed on fixtures** at release-candidate commit
`283a330` (`283a330148618e31280f016e8598b59ac52f4a81`, branch
`codex/release-candidate-evidence`, not yet on GitHub). An earlier run at
`4c98b2c` also passed every target it measured.
The working tree had no tracked changes. Every target had one warm-up and 30
measured runs, and every sample checked its own result. The runs used only
synthetic data and spent zero live quota. The raw report holds every sample:
[2026-11-28-a2-08-features.json](2026-11-28-a2-08-features.json).

| Target | NFR-08 bound | Median | p95 | Result |
| --- | --- | ---: | ---: | --- |
| Input validation of FR-1–FR-5 fields, in process | p95 ≤ 100 ms | 0.03 ms | 0.03 ms | Pass |
| Similar-video ranking, 200 candidates | ≤ 2 s | 9.52 ms | 12.39 ms | Pass |
| Similar-channel ranking, 200 videos in 20 channels | ≤ 2 s | 9.05 ms | 9.62 ms | Pass |
| Recommendation ranking, 200 candidates, three sources | ≤ 2 s | 11.50 ms | 12.10 ms | Pass |
| Proposal construction from 200 candidates | ≤ 2 s | 4.19 ms | 4.44 ms | Pass |

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
| `find_similar_videos` `{"video": "https://youtu.be/vidIndex001", "limit": 1}` | Ranked `vidIndex002` | 41.12 ms | 47.38 ms | ≤ 2 s |
| `find_similar_channels` `{"channel": "https://www.youtube.com/@SystemsStudyLab"}` | Ranked `UCbbbbbbbbbbbbbbbbbbbbbb` | 56.10 ms | 68.13 ms | ≤ 2 s |
| `recommend_videos` on a saved likes snapshot, `en`, 1,300 s | Ranked `vidIndex001` | 31.74 ms | 37.18 ms | ≤ 2 s |
| `propose_playlist` on `fixture-recommendations`, 720 s total, 600 s per video, `en` | `fixture0301`, 600 s | 10.04 ms | 11.75 ms | ≤ 2 s |
| `find_similar_videos` `{"video": "https://example.com/watch?v=vidIndex001"}` | `UNSUPPORTED_IDENTIFIER` | 0.86 ms | 1.06 ms | p95 ≤ 100 ms |

### Cached reads (J2-08)

| Tool and input | Checked output | Median | p95 | Bound |
| --- | --- | ---: | ---: | --- |
| `analyse_library` on a stored full-library snapshot | 3 combined videos. **0 provider attempts during the 30 samples.** | 9.43 ms | 12.44 ms | p95 ≤ 2 s |
| `read_resource` of a saved `yt-intel://proposals/{id}/1` preview | Text identical to the original preview | 6.08 ms | 6.97 ms | p95 ≤ 2 s |

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
