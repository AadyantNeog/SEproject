# Aadyant: core engineering brief

Owner: Aadyant Neog (BT2024186). These are instructions for his coding agent; they do not claim he authored the planning files.

Read root AGENTS.md, the SRS, brain index, master plan, contracts and team workplan. Own A01–A12 in dependency order. You implement most of the code and all difficult authority, quota and recovery boundaries. Jeswin owns analytics/presentation; Paul owns fixture data, CI, workflow skills and documentation. Do not replace their contribution with code attributed to them.

Start with A01: inspect existing environments, use the canonical Python 3.13 interpreter, verify/install compatible locked dependencies, define strict DTOs/provider interfaces and a working fixture stdio smoke. Next run A02 early: actual selected-client connection, skill loading and native human confirmation on Windows. A failed trusted-confirmation proof blocks live writes but not fixture/read development.

Then implement durable quota/storage, official HTTP provider, OAuth/account isolation, deterministic discovery, library/profile retrieval, strict planner, trusted approval and journalled serial writes. Pair each safety-critical slice with behaviour/fault tests. Follow the exact state/expiry/retention rules in CONTRACTS and MASTER_PLAN. Do not depend on hidden retries or a fictional remote idempotency key.

Your owned paths are `src/yt_intel/` except Jeswin's analytics/presentation, shared manifests/config/locks, core integration/security/system tests and ADR/contract integration. Paul authors datasets and independent expected results; you implement the fixture provider mechanics. Request missing fixtures as a concrete schema/example, not a live account dump.

Expose only the documented tool/resource surface. Model text cannot provide account authority, language evidence, duration evidence, quota approval or human approval. Native helper grants are not exported. No automation may click a live confirmation control. Policy D-02 remains an explicit live-derived gate until evidence resolves it; source labelling alone does not resolve it.

Maintain reviewed contract changes so J01/J02 can proceed on synthetic snapshots before A07 finishes. Keep DTOs immutable for consumers. For every task include actual checks, requirement/test links, current limitations and an AI-session note when significant. Never claim human review or a live acceptance result from local fixture success. Before release collect genuine team reviews, individual contributions and applicable live evidence.

First handoff: give Jeswin a valid LibrarySnapshot/AnalysisReport/PlaylistProposal fixture and Paul API-shaped fixtures plus failure-script schema. Merged A01 is the compatibility baseline. A task is done only by its workplan exit conditions.

Distilled basis: [15-implementation-boundaries-and-contracts](../../../brain/resources/15-implementation-boundaries-and-contracts.md), [06-preview-and-human-approval](../../../brain/resources/06-preview-and-human-approval.md), [09-quota-buckets-and-budgeting](../../../brain/resources/09-quota-buckets-and-budgeting.md).
