# Agentic QA Platform — Context for Claude Code

## Project
AI-driven QA platform that autonomously generates, executes, and self-heals tests
for Saleor (Python/Django e-commerce). Portfolio project for Agentic QA Architect roles.

## Stack
- Python 3.12, Pydantic v2, pytest, Playwright, httpx
- LLM API: OpenRouter
   - Generation model: openai/gpt-oss-120b:free
   - Reasoning model: openai/gpt-oss-120b:free with high-reasoning prompt mode
   - Fallback reasoning model: anthropic/claude-sonnet-4.6 when paid fallback is enabled
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

- [2026-05-01 12:41] Day 2: GraphQL schema analyzer with introspection, 13 unit tests passing
- Day 1: docker-compose.yml (Saleor + PostgreSQL + Redis), src/config/settings.py (pydantic-settings configuration), scripts/health_check.py (GraphQL + Anthropic API health check), .env.example template
