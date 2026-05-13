# Agentic QA Platform

> An AI-driven quality engineering platform that autonomously generates, executes, self-heals, and audits tests for a production-grade e-commerce GraphQL API — with zero human steps between a code change and a quality gate decision.

---

## The Problem This Solves

As AI-generated code accelerates development velocity, hand-written test suites become the bottleneck: they lag behind schema changes, go stale overnight, and require manual triage when they fail. Traditional QA processes assume a human is in the loop at every decision point — but at the pace modern teams ship, that assumption breaks down. This platform closes the gap by treating test generation, execution, failure analysis, and repair as a fully autonomous pipeline that reacts to code changes in real time.

---

## Agentic Levels

| Level | What the Human Does | What the System Does |
|---|---|---|
| **Level 1** | Invoke one command | Analyze schema → generate tests → run → report coverage |
| **Level 2** | Push a commit | Detect diff → score risk → generate targeted tests → quality gate |
| **Level 3** | Review escalations | Classify failures → auto-patch stale tests → audit every change |

**This project demonstrates Level 2 fully and Level 3 on the API layer.**

---

## Architecture

```
  git diff / schema
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Analyzers                               │
  │  DiffAnalyzer → affected operations                         │
  │  RiskScorer   → CRITICAL / HIGH / MEDIUM / LOW per-op       │
  │  SchemaAnalyzer → all queries & mutations                   │
  │  CoverageAnalyzer → coverage gaps + priority queue          │
  └──────────────────────────┬──────────────────────────────────┘
                             │ HIGH / CRITICAL ops
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Generators                              │
  │  ApiTestGenerator  → pytest (httpx, GraphQL)                │
  │  UITestGenerator   → Playwright async tests                 │
  │  IntegrationTestGenerator → API + UI cross-layer tests      │
  └──────────────────────────┬──────────────────────────────────┘
                             │ generated_tests/{api,ui,integration}/
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                      Runners                                │
  │  PytestRunner → PytestRunResult (per-test status + errors)  │
  └──────────────────────────┬──────────────────────────────────┘
                             │ failures
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                      Healers                                │
  │  FailureClassifier → APP_BUG | TEST_STALE | FLAKY | …       │
  │  SelfHealer        → patch TEST_STALE, verify, commit       │
  │  EscalationManager → needs_review.json queue + CLI review   │
  └──────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Reporters                               │
  │  ReportGenerator → reports/latest.json + reports/latest.html│
  └─────────────────────────────────────────────────────────────┘
                             │
                             ▼
              Quality Gate (pass / fail → exit code)
```

See [docs/architecture.md](docs/architecture.md) for full module descriptions and data models.

---

## Modules

| Module | File | What It Does |
|---|---|---|
| **SchemaAnalyzer** | `src/analyzers/schema_analyzer.py` | GraphQL introspection → structured operations |
| **DiffAnalyzer** | `src/analyzers/diff_analyzer.py` | Parse git diff → affected GraphQL operations |
| **RiskScorer** | `src/analyzers/risk_scorer.py` | LLM-powered risk level per changed operation |
| **CoverageAnalyzer** | `src/analyzers/coverage_analyzer.py` | Schema coverage gaps + priority scoring |
| **ApiTestGenerator** | `src/generators/api_test_generator.py` | LLM → pytest + httpx test code |
| **UITestGenerator** | `src/generators/ui_test_generator.py` | LLM → async Playwright test code |
| **IntegrationTestGenerator** | `src/generators/integration_test_generator.py` | LLM → cross-layer API + UI tests |
| **PytestRunner** | `src/runners/pytest_runner.py` | Execute tests, capture structured results |
| **FailureClassifier** | `src/healers/failure_classifier.py` | LLM classifies root cause of failing tests |
| **SelfHealer** | `src/healers/self_healer.py` | Patch TEST_STALE failures, verify, write heals.jsonl |
| **EscalationManager** | `src/healers/escalation_manager.py` | Queue APP_BUG / low-confidence for human review |
| **ReportGenerator** | `src/reporters/report_generator.py` | JSON + HTML quality reports |
| **AgentCore** | `src/agent/core.py` | Full autonomous loop + CLI |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/yourusername/agentic-qa-platform
cd agentic-qa-platform
uv sync

# 2. Set up environment
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY and SALEOR_GRAPHQL_URL

# 3. Start Saleor
podman compose up -d

# 4. Run the autonomous agent against a git diff
uv run python -m src.agent run --diff HEAD~3..HEAD

# 5. View the HTML report
open reports/latest.html
```

---

## Demo

### Level 2 — Autonomous Agent Loop

```bash
# Simulate a change, then let the agent react
git commit --allow-empty -m "chore: simulate change"
uv run python -m src.agent run --diff HEAD~1..HEAD
```

Expected output:
```
=======================================================================
AGENT RUN REPORT
=======================================================================
Timestamp:           2026-05-12T10:30:00+00:00
Diff Range:          HEAD~1..HEAD
Overall Risk:        HIGH
Recommended Tests:   3
New Tests Generated: 2
Generation Failures: 0

TEST EXECUTION
  Passed:  282
  Failed:  0
  Errors:  0
  Total:   282
  Time:    4.21s

Regressions:         0
Quality Gate:        PASS
=======================================================================
```

### Level 3 — Self-Healing Review Queue

```bash
# View tests awaiting human decision
uv run python -m src.agent review

# Accept or reject a specific escalation
uv run python -m src.agent resolve \
  --test "generated_tests/api/test_checkout.py::test_checkout_create" \
  --action accept \
  --note "Verified: schema field rename was intentional"
```

Full walkthrough: [docs/demo_level2.md](docs/demo_level2.md)

---

## Capabilities

- [x] Autonomous API test generation from GraphQL schema (Level 1)
- [x] Risk-based test prioritization from git diffs (Level 2)
- [x] Cross-layer test generation: API + Playwright UI + integration
- [x] Autonomous agent loop: diff → risk → generate → run → quality gate
- [x] Regression detection across runs (.agent_state.json)
- [x] LLM-powered failure root-cause classification (APP_BUG / TEST_STALE / FLAKY / ENVIRONMENT / UNKNOWN)
- [x] Self-healing for TEST_STALE failures with dry-run mode
- [x] Governance: every heal logged to heals.jsonl, every escalation to needs_review.json
- [x] Human escalation queue with CLI review + accept/reject workflow (Level 3)
- [x] HTML + JSON quality reports with dark-theme visual output
- [ ] Jenkins CI pipeline (Day 18)
- [ ] Configurable quality gate engine (Day 19)
- [ ] Performance testing with k6 (Day 20)
- [ ] OWASP ZAP security scanning (Day 22)

---

## Edge Cases Handled

| Scenario | Behavior |
|---|---|
| Empty diff | Logs "no changes detected", produces LOW-risk report |
| Saleor unreachable | Schema fetch silently skipped; failures recorded in report |
| LLM rate limit (risk scoring) | Falls back to MEDIUM risk; loop continues |
| LLM rate limit (generation) | Per-operation failure logged; other ops continue |
| Regression detected | Quality gate fails, exit code 1 |
| Low-confidence classification | Escalated regardless of category |
| APP_BUG or UNKNOWN classification | Always escalated; never auto-healed |
| UI test fails | Rejected by SelfHealer (no DOM signal available) |
| Corrupt needs_review.json | EscalationManager returns empty queue, logs warning |

---

## Testing

```bash
# Run all 282 tests (no external services required)
uv run pytest --tb=short

# Run a specific module
uv run pytest tests/test_failure_classifier.py -v

# Run with coverage
uv run pytest --cov=src
```

All tests use mocks and temporary directories — no Saleor, no LLM calls, no filesystem side effects.

**Test breakdown by module:**

| Test File | Tests | What's Covered |
|---|---|---|
| `test_schema_analyzer.py` | 13 | Introspection parsing, type resolution |
| `test_api_test_generator.py` | 5 | LLM prompt construction, code writing |
| `test_pytest_runner.py` | 9 | Plugin collection, result capture |
| `test_coverage_analyzer.py` | 8 | Priority scoring, coverage calculation |
| `test_generate_command.py` | 5 | Week 1 orchestration |
| `test_diff_analyzer.py` | 23 | Diff parsing, operation mapping |
| `test_risk_scorer.py` | 15 | LLM response parsing, fallback |
| `test_agent_core.py` | 24 | Full loop, regression detection, quality gate |
| `test_ui_test_generator.py` | 16 | Playwright code generation |
| `test_integration_test_generator.py` | 20 | Cross-layer scenario generation |
| `test_report_generator.py` | 19 | JSON/HTML output |
| `test_page_context_extractor.py` | varies | Storefront context extraction |
| `test_failure_classifier.py` | 26 | LLM classification, escalation logic |
| `test_self_healer.py` | 40 | Patch generation, temp-file verification |
| `test_escalation_manager.py` | 24 | Queue CRUD, idempotency, disk persistence |
| `test_e2e_agent.py` | 6 | End-to-end agent scenarios |
| **Total** | **282** | |

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Data models | Pydantic v2 |
| LLM API | OpenRouter (gpt-oss-120b:free for generation; gpt-4o-mini for reasoning) |
| API testing | httpx + pytest |
| UI testing | Playwright (async) |
| CLI | typer |
| System Under Test | Saleor (GraphQL, Django, Docker) |
| Container runtime | Podman / podman-compose |

---

## Roadmap

- **Week 1** ✅ LLM test generation from schema
- **Week 2** ✅ Autonomous agent loop (Level 2)
- **Week 3** ✅ Self-healing + failure classification + audit trail (Level 3 on API layer)
- **Week 4** 🔄 Jenkins CI + quality gate engine + k6 perf + ZAP security + portfolio polish

Full roadmap: [ROADMAP.md](ROADMAP.md)

Architecture decisions: [docs/adr/](docs/adr/)
