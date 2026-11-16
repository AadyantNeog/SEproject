# Jeswin: analytics and presentation brief

Owner: Jeswin Jose (BT2024142). These are instructions for his coding agent; the owner must inspect and understand all contributed work.

Read root AGENTS.md, the SRS, brain index, master plan, contracts and team workplan. Work on J01–J04. Own `src/yt_intel/analytics/`, `src/yt_intel/presentation/`, their unit tests, analytics examples and your own notes. Get merged A01 contracts before coding imports. You can draft arithmetic oracles and user examples while the package is being prepared.

J01: implement pure per-source/unique collection summaries, channel/category counts, runtime count/mean/median/bands, unknown buckets and subscription-channel counts. Keep playlist occurrences and unique videos distinct. J02: compare allowed playlist-addition/subscription-creation events over two non-overlapping start-inclusive/end-exclusive UTC periods. Zero baseline percentage change is undefined; unsupported like dates and watch-time claims are never inferred.

J03: format the public DTOs into readable ranked results, complete previews, reports and actionable errors. The native approval dialog uses the same proposal renderer. Display all videos, exact and human-readable durations, destination account/channel, privacy, language evidence, constraints, totals, unused time and expiry. Escape untrusted text; do not recalculate authoritative totals or fabricate missing fields. Mark fixture output clearly.

Keep calculations independently testable with immutable synthetic snapshots. Use the oracle `[240,600,600,1200]`: count 4, mean 660, median 600, bands `[1,2,1,0,0]`. Add unknown metadata, duplicates, equal-count ties, empty sources, adjacent/overlapping periods and boundary event cases. Assert semantics rather than hundreds of spaces in a text snapshot. Verify output DTOs are not mutated.

Do not add YouTube calls, OAuth, persistence, ranking algorithms, quota logic or approval state to your modules. Do not change shared models or manifests to fix an import without coordinating a contract PR. If retrieval lacks a needed field, give Aadyant the failing synthetic input and required contract change. Keep live credentials out of your agent's prompts and outputs.

J04: document FR-4 examples/limits and demonstrate your report, its denominators and timestamp basis. Run actual checks and add real test/Issue/PR links as they exist. AI-session notes name your agent; personally author your human reflection and perform real human reviews under your own identity. Never manufacture passed tests or approval records.

Distilled basis: [05-time-based-analysis](../../../brain/resources/05-time-based-analysis.md), [03-authorised-preference-signals](../../../brain/resources/03-authorised-preference-signals.md), [15-implementation-boundaries-and-contracts](../../../brain/resources/15-implementation-boundaries-and-contracts.md).
