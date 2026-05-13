# ADR-001: Use OpenRouter with gpt-oss-120b:free for Test Generation

**Date**: 2026-05-01
**Status**: Accepted

---

## Context

The platform requires an LLM API for three distinct tasks:
1. **Test generation** — high-volume, called once per operation; needs code output
2. **Risk scoring** — reasoning-heavy, called once per diff; needs structured JSON
3. **Failure classification + self-healing** — also reasoning-heavy, called on each failing test

A direct API choice (Anthropic, OpenAI, Google) locks the platform to a single provider and billing relationship. Cost matters: at scale, test generation can fire hundreds of LLM calls per CI run.

Options considered:

| Option | Cost | Quality | Notes |
|---|---|---|---|
| OpenAI GPT-4o direct | Paid (~$0.005/call) | High | Per-call cost accumulates quickly |
| Anthropic Claude Sonnet direct | Paid (~$0.003/call) | High | No free tier |
| OpenRouter + gpt-oss-120b:free | Free | Good for code gen | Rate-limited; acceptable for generation |
| OpenRouter + gpt-4o-mini | Very low | Good | Suitable fallback for reasoning |
| Local model (Ollama) | Free | Inconsistent | Requires GPU setup; not portable |

---

## Decision

Use **OpenRouter** as the API gateway, with:
- `openai/gpt-oss-120b:free` for high-volume test generation (free tier)
- `openai/gpt-4o-mini` for reasoning tasks (failure classification, risk scoring) where quality matters more than cost

OpenRouter exposes an OpenAI-compatible API so the `openai` Python SDK works without modification. Swapping models or adding fallback logic requires only a string change.

---

## Consequences

**Positive:**
- Zero marginal cost for the majority of LLM calls (generation uses free tier)
- Single SDK (`openai`) regardless of which underlying model is used
- Model can be swapped per task without changing application code
- Free tier rate limits are handled gracefully via `score_risk_with_fallback()`

**Negative:**
- Free tier has rate limits; rapid CI pipelines may hit them
- OpenRouter adds a network hop vs. direct provider API
- Model availability depends on OpenRouter's routing (models can go offline)

**Mitigations:**
- `score_risk_with_fallback()` returns a MEDIUM-risk result if the LLM call fails
- Generation failures are per-operation: one failure doesn't abort the whole pipeline
- Model string is config-driven; switching is a one-line change in `settings.py`
