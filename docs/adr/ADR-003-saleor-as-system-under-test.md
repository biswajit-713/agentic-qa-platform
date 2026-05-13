# ADR-003: Use Saleor as the System Under Test

**Date**: 2026-05-01
**Status**: Accepted

---

## Context

The platform needs a realistic, production-grade application to test against. The SUT must:
- Expose a rich GraphQL API (many operations, complex types, nested inputs)
- Be runnable locally via Docker/Podman without external dependencies
- Be open source (no licensing costs)
- Be representative of real-world systems QA engineers face

Choosing a toy API would undermine the portfolio argument: if the agent can only handle simple schemas, it's not demonstrating real capability.

Options considered:

| Option | GraphQL | Complexity | Local setup | Real-world credibility |
|---|---|---|---|---|
| **Saleor** (e-commerce) | Yes (rich) | High | docker-compose | High — production-grade, used in real deployments |
| Hasura (auto-generated) | Yes | Medium | docker-compose | Moderate — schema is auto-generated, not hand-crafted |
| Shopify (hosted) | Yes | High | No (hosted) | High — but requires remote access, not reproducible |
| A custom toy API | Configurable | Low | Easy | Low — obviously artificial |
| GitHub GraphQL API | Yes | High | No (hosted) | High — but requires auth, not self-contained |

---

## Decision

Use **Saleor** (https://github.com/saleor/saleor) as the system under test. Saleor is a production-grade Python/Django e-commerce platform with:
- 150+ GraphQL operations (queries + mutations)
- Deeply nested input types (`CheckoutCreate`, `AddressInput`, etc.)
- Authentication-gated mutations (demonstrates auth test generation)
- A companion React storefront (enables Playwright UI testing)
- An active open-source community (realistic schema evolution over time)

The combination of a rich API and a real storefront makes it the ideal target for demonstrating all three layers of test generation: API, UI, and integration.

---

## Consequences

**Positive:**
- Schema complexity challenges the LLM in realistic ways (nested inputs, union types, enums)
- The storefront enables Playwright UI test generation — a second test layer beyond API
- Schema changes in Saleor upstream can simulate real-world TEST_STALE scenarios
- e-commerce domain (checkout, payment, orders) maps directly to high-risk operations — good for demonstrating risk scoring
- Self-contained via docker-compose; reproducible on any machine

**Negative:**
- Saleor's docker-compose stack (Django + PostgreSQL + Redis) is heavier than a minimal API
- Some Saleor mutations require authenticated sessions (token management needed in generated tests)
- Schema evolves with upstream releases, which can break generated tests (this is actually a feature — it exercises the self-healing pipeline)

**Mitigations:**
- All platform unit tests mock Saleor (httpx mocking); no running instance required for testing the platform itself
- `scripts/health_check.py` verifies Saleor is reachable before running the agent
- Auth token handling is abstracted in `conftest.py` for generated tests
