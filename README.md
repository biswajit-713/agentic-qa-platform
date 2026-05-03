# Agentic QA Platform

An AI-driven quality engineering platform that autonomously generates, executes, and reports on tests for Saleor (Python/Django e-commerce GraphQL API).

## What It Does

This platform uses LLMs to analyze a GraphQL schema, identify untested operations, generate realistic pytest test cases, execute them against Saleor, and report coverage gaps. Week 1 (Days 1-7) demonstrates Level 1 autonomy: LLM-powered test generation from a schema. Weeks 2-4 add autonomous decision-making (analyze code changes → prioritize → generate → run → report) and self-healing (auto-patch stale tests).

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/yourusername/agentic-qa-platform
cd agentic-qa-platform
uv sync

# 2. Set up environment
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY and SALEOR_GRAPHQL_URL

# 3. Start Saleor (if not already running)
docker-compose up -d

# 4. Generate 10 tests from uncovered operations
uv run python -m src.agent.generate_command --count 10

# 5. View report
cat reports/generation_report.json
```

## Week 1: LLM Test Generation

**Goal**: Single command generates 50+ tests, runs them, reports coverage.

**Modules**:
- `SchemaAnalyzer` — introspects Saleor's GraphQL schema
- `CoverageAnalyzer` — compares operations vs. test files, prioritizes gaps
- `ApiTestGenerator` — uses OpenRouter (gpt-oss-120b:free) to generate pytest code
- `PytestRunner` — executes tests, captures structured results
- `GenerateCommand` — orchestrates the full pipeline

**Example Run**:
```bash
$ uv run python -m src.agent.generate_command --count 5
Starting test generation: count=5, test_dir=generated_tests/api
Coverage before: 0.0% (0/150 operations)
[1/5] Generating test for productCreate...
✓ Generated productCreate → generated_tests/api/test_product_create.py
[2/5] Generating test for checkoutCreate...
✓ Generated checkoutCreate → generated_tests/api/test_checkout_create.py
...
Test run complete: 5 passed, 0 failed, 0 errors (12.34s)
Coverage after: 3.3% (5/150 operations)
Report saved to reports/generation_report.json
```

**Report** (`reports/generation_report.json`):
```json
{
  "timestamp": "2026-05-03T10:30:00.123456",
  "count_requested": 5,
  "generated": ["test_product_create", "test_checkout_create"],
  "failed_generations": [],
  "coverage_before": 0.0,
  "coverage_after": 3.3,
  "total_operations": 150,
  "run_result": {
    "total": 5,
    "passed": 5,
    "failed": 0,
    "errors": 0,
    "duration_seconds": 12.34,
    "test_results": [...]
  }
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Agentic QA Platform                        │
│                                                         │
│  Analyzers          Generators      Runners      Agent  │
│  ──────────         ──────────      ───────      ─────  │
│  SchemaAnalyzer  ──→ ApiTestGen  → PytestRunner         │
│     ↓               ↓                                    │
│  CoverageAnalyzer                                       │
│     ↓                                                   │
│  GenerateCommand ────────────────────────→ Report      │
└─────────────────────────────────────────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for detailed module descriptions.

## Testing

```bash
# Run all tests
uv run pytest --tb=short

# Run specific test module
uv run pytest tests/test_generate_command.py -v

# Run with coverage
uv run pytest --cov=src
```

All tests use mocking and temporary directories — no external services required.

## Stack

- **Language**: Python 3.12
- **Data**: Pydantic v2 (strict validation)
- **API**: OpenRouter (gpt-oss-120b:free for generation)
- **Testing**: pytest with custom pytest plugin for result capture
- **CLI**: typer (for Week 1 command)
- **SUT**: Saleor GraphQL (Docker-compose)

## Roadmap

- **Week 1** ✅ LLM test generation from schema
- **Week 2** 🔄 Autonomous agent (analyze diffs → risk score → generate → run)
- **Week 3** 🔄 Self-healing tests + Jenkins CI + performance testing
- **Week 4** 🔄 Security testing + extensibility + portfolio docs

Full roadmap: [ROADMAP.md](ROADMAP.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT
