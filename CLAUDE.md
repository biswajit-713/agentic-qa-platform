# Agentic QA Platform — Context for Claude Code

## Project
AI-driven QA platform that autonomously generates, executes, and self-heals tests
for Saleor (Python/Django e-commerce). Portfolio project for Agentic QA Architect roles.

## Stack
- Python 3.12, Pydantic v2, pytest, Playwright, httpx
- LLM API: OpenRouter (see [LLM_MODELS.md](LLM_MODELS.md))
- Saleor GraphQL at localhost:8000/graphql/
- Saleor storefront at localhost:3000
- Jenkins at localhost:8080

## Conventions
- All models use Pydantic v2 with type hints on all public functions
- No print() — use the logging module
- Generated tests → generated_tests/{layer}/
- Reports → reports/

## Module Responsibilities (do not mix concerns)
- src/analyzers/: read-only analysis, no side effects
- src/generators/: produce test code strings, do not execute them
- src/runners/: execute tests, do not generate
- src/healers/: modify existing tests, never generate new ones
- src/agent/: orchestrate only, no business logic

## Built So Far

- [2026-05-03] Day 5: Test runner with structured results. Built `src/runners/pytest_runner.py` with custom pytest plugin, `PytestRunResult` and `SingleTestResult` Pydantic models, test filtering/pattern support, full exception capture. All 27 tests passing (18 existing + 9 new)
- [2026-05-02] Day 4: Enhanced API test generator with type introspection and recursive destructuring. Added `get_type_definition()` and `inputFields` introspection for INPUT_OBJECT types. Recursive destructuring of nested types (AddressInput, CheckoutValidationRules, MetadataInput, etc). All 18 tests passing
- [2026-05-02] Day 3: LLM-powered API test generator using OpenRouter, `TestCase` Pydantic model with structured output, 5 unit tests passing (18 total)
- [2026-05-01] Day 2: GraphQL schema analyzer with introspection, 13 unit tests passing
- [2026-05-01] Day 1: docker-compose.yml (Saleor + PostgreSQL + Redis), src/config/settings.py (pydantic-settings configuration), scripts/health_check.py (GraphQL + Anthropic API health check), .env.example template
