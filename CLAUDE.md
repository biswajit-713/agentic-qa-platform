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

- [2026-05-10] Day 15: Failure Classifier complete. src/healers/failure_classifier.py uses OpenRouter to classify failing test root causes into APP_BUG | TEST_STALE | ENVIRONMENT | FLAKY | UNKNOWN. APP_BUG and UNKNOWN always escalate to human; confidence < 0.7 escalates regardless of category. should_auto_heal() gates the healer pipeline — only TEST_STALE and FLAKY with high confidence proceed. 26 new tests, 218 total passing.
- [2026-05-09] Day 14: Week 2 integration and polish complete. score_risk_with_fallback handles LLM rate limits at the risk-scoring step. 6 new e2e tests covering empty diff, Saleor unreachable, LLM rate limit fallback, full HIGH-risk pipeline, and regression-across-runs. README updated with Level 2 demo section and edge-case table. docs/demo_level2.md added with step-by-step walkthrough. 192 tests passing.
- [2026-05-09] Day 13: Smart Reporter complete. src/reporters/report_generator.py generates reports/latest.json (machine-readable, CI-consumable) and reports/latest.html (dark-theme visual report) from a RunReport. HTML covers: run header + quality gate badge, stat grid, risk table with per-op risk levels, test results with layer detection (api/ui/integration), coverage bar with delta, and agent reasoning block. Jinja2 inline template, no external CSS. Agent core auto-calls generate_reports after each loop. 19 new tests, all 186 passing.
- [2026-05-08] Day 12 (refinement): Replaced data-dependent UI flows (search, add-to-cart, checkout) with pure frontend scenarios (homepage structure, 404 page, keyboard accessibility, mobile nav, empty cart state). Data-dependent flows absorbed into integration tests where they have proper API setup/teardown and known state.
- [2026-05-08] Day 12: Cross-layer integration test generator complete. src/generators/integration_test_generator.py generates tests spanning GraphQL API (httpx) + Playwright UI with setup/action/assert/teardown phases. 3 scenarios: create-product→storefront, cart-via-UI→API, checkout→order-status. 20 new tests, all 139 passing.
- [2026-05-08] Day 11: Playwright UI test generator complete. src/generators/ui_test_generator.py generates async Playwright tests via OpenRouter for 3 Saleor storefront flows (search, add-to-cart, checkout). Tests land in generated_tests/ui/. UITestCase Pydantic model with structured LLM output. 16 new tests, all 119 passing.
- [2026-05-07] Day 10: Autonomous agent loop complete. src/agent/core.py wires diff → risk → generate (HIGH/CRITICAL only) → run → regression detection → quality gate → report. AgentState persists test history in .agent_state.json. Entry point: python -m src.agent run --diff HEAD~3..HEAD. 24 new tests, all 103 passing.
- [2026-05-07] Day 9: Risk scorer complete. LLM-powered RiskAssessment using OpenRouter, risk_config.yml rubric, RiskLevel (CRITICAL/HIGH/MEDIUM/LOW) per operation with rationale and suggested_test_focus. 15 new tests, all 79 passing.
- [2026-05-05] Day 8: Git diff analyzer complete. Parses unified diff into CodeChange objects, maps mutations/resolvers/models to GraphQL operations, handles added/deleted/renamed files. 23 new tests, all 64 passing.
- [2026-05-03] Day 7: Week 1 orchestrator complete. GenerateCommand (typer CLI) wires schema → coverage → generate → run → report. JSON reporting with before/after coverage deltas. 5 new tests, all 40 tests passing. docs/architecture.md + README.md complete.
- [2026-05-03] Day 6: Coverage analyzer with priority scoring for uncovered operations. All 35 tests passing (8 new)
- [2026-05-03] Day 5: Test runner with structured results. Built `src/runners/pytest_runner.py` with custom pytest plugin, `PytestRunResult` and `SingleTestResult` Pydantic models, test filtering/pattern support, full exception capture. All 27 tests passing (18 existing + 9 new)
- [2026-05-02] Day 4: Enhanced API test generator with type introspection and recursive destructuring. Added `get_type_definition()` and `inputFields` introspection for INPUT_OBJECT types. Recursive destructuring of nested types (AddressInput, CheckoutValidationRules, MetadataInput, etc). All 18 tests passing
- [2026-05-02] Day 3: LLM-powered API test generator using OpenRouter, `TestCase` Pydantic model with structured output, 5 unit tests passing (18 total)
- [2026-05-01] Day 2: GraphQL schema analyzer with introspection, 13 unit tests passing
- [2026-05-01] Day 1: docker-compose.yml (Saleor + PostgreSQL + Redis), src/config/settings.py (pydantic-settings configuration), scripts/health_check.py (GraphQL + Anthropic API health check), .env.example template
