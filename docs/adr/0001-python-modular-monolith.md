# ADR-0001: Python modular monolith with local stdio MCP

Date: 16 November 2026 · Author: Codex · Status: proposed for human review

Ownership amended 19 November 2026 under [ADR-0006](0006-equal-team-workload-and-shared-integration.md); technical scope unchanged.

## Context

The SRS requires local Windows operation, stdio tools/resources, interchangeable official/fixture providers, independently testable algorithms and one supported client. All three members need stable interfaces and equal substantial engineering responsibility, including integration/tests/docs/reviews. A custom web service, trained model or GPU is outside the required baseline.

Distilled basis: [11-mcp-and-agent-skill-contracts](../../brain/resources/11-mcp-and-agent-skill-contracts.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Use Python 3.13, the official MCP Python SDK, Pydantic contracts, HTTPX for explicit official REST calls, SQLite repositories, Google OAuth libraries, protected keyring storage and a native human approval adapter. Separate domain, services, provider/infrastructure, MCP and presentation modules within one installable package.

Keep domain/analytics pure. Aadyant owns common bootstrap/MCP, ranking/recommendations/planning/presentation; Jeswin owns accounted HTTP/read/fixture provider, OAuth/library/analytics; Paul owns storage/quota/approval/writes/recovery/CI. Each supplies their own fixtures/tests/docs/handler integration and skill/evidence handoff; Aadyant reviews all teammate outputs and his own work receives independent non-author review under ADR-0007. A2-01 locks compatible dependencies with affected-owner technical input and independent review of Aadyant's foundation; A2-05/P2-03 prove client/native approval before live claims. The original 16 November technical research selected MCP 2.3.0; no new version check or runtime manifest is implied by this allocation amendment.

## Alternatives and consequences

TypeScript is viable but adds no requirement advantage over the existing Python environment. A REST/web application adds deployment and auth scope. ML frameworks/embeddings add dependencies and opaque scoring without a baseline need. A modular monolith makes deployment/debugging manageable; shared integration creates cross-owner handoffs requiring early executable contracts, named editors, Aadyant-led teammate review, independent review of his own work and actual-effort checkpoints with review overhead separate. No member is the default integrator for everyone else's work.

## Verification and links

Requirements: NFR-01, NFR-07, NFR-11, GOV-02, GOV-04. Tasks: A2-01/A2-05/A2-08, J2-02/J2-06/J2-08, P2-03/P2-06/P2-08. Acceptance: AT-01/18/19/20. Real Issue/PR links and runtime verification: pending. Full design: [MASTER_PLAN](../implementation/MASTER_PLAN.md), [CONTRACTS](../implementation/CONTRACTS.md). Current distilled allocation: [17-equal-team-allocation](../../brain/resources/17-equal-team-allocation.md).
