# ADR-0001: Python modular monolith with local stdio MCP

Date: 16 November 2026 · Author: Codex · Status: proposed for human review

## Context

The SRS requires local Windows operation, stdio tools/resources, interchangeable official/fixture providers, independently testable algorithms and one supported client. Aadyant owns difficult integration; teammates need stable interfaces and smaller product/workflow contributions. A custom web service, trained model or GPU is outside the required baseline.

Distilled basis: [11-mcp-and-agent-skill-contracts](../../brain/resources/11-mcp-and-agent-skill-contracts.md), [12-engineering-and-knowledge-workflow](../../brain/resources/12-engineering-and-knowledge-workflow.md), [15-implementation-boundaries-and-contracts](../../brain/resources/15-implementation-boundaries-and-contracts.md).

## Decision

Use Python 3.13, the official MCP Python SDK, Pydantic contracts, HTTPX for explicit official REST calls, SQLite repositories, Google OAuth libraries, protected keyring storage and a native human approval adapter. Separate domain, services, provider/infrastructure, MCP and presentation modules within one installable package.

Keep analytics pure and let Jeswin implement it against immutable LibrarySnapshot models. Paul supplies independent synthetic fixture data, CI, skills and docs. Aadyant owns shared contracts and composition. A01 proves and locks compatible SDK/dependency versions; A02 proves the actual Windows client/skill/approval setup before dependent live claims. The verified planning MCP selection is 2.3.0; no untested runtime manifest is implied.

## Alternatives and consequences

TypeScript is viable but adds no requirement advantage over the existing Python environment. A REST/web application adds deployment and auth scope. ML frameworks/embeddings add dependencies and opaque scoring without a baseline need. A modular monolith makes deployment and debugging manageable, at the cost of Aadyant being the primary integrator. Interfaces, task/path ownership and frequent reviewed slices reduce that bottleneck.

## Verification and links

Requirements: NFR-01, NFR-07, NFR-11, GOV-02, GOV-04. Tasks: A01/A02/A11, J01, P02. Acceptance: AT-01/18/19/20. Real Issue/PR links and runtime verification: pending. Full design: [MASTER_PLAN](../implementation/MASTER_PLAN.md), [CONTRACTS](../implementation/CONTRACTS.md).
