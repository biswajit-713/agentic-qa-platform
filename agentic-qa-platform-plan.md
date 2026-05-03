# Agentic QA Platform — Project Plan

> **Goal**: A production-grade, AI-driven quality engineering platform that autonomously generates, executes, and maintains tests for a real e-commerce system — built as a portfolio project for Chief Agentic Quality Architect roles.
>
> **System Under Test**: [Saleor](https://github.com/saleor/saleor) (Python/Django, GraphQL API + React storefront)
> **Primary Language**: Python
> **Timeline**: 28 days · 3-4 hrs/day · ~100 hours total

---

## Table of Contents

1. [Repository Setup](#1-repository-setup)
2. [Architecture Overview](#2-architecture-overview)
3. [Day-by-Day Plan](#3-day-by-day-plan)
   - [Week 1: Foundation + LLM Test Generation](#week-1-foundation--llm-test-generation-days-1-7)
   - [Week 2: Autonomous Test Agent Level 2](#week-2-autonomous-test-agent-level-2-days-8-14)
   - [Week 3: Self-Healing + CI/CD + Performance](#week-3-self-healing--cicd--performance-days-15-21)
   - [Week 4: Security + Polish + Portfolio](#week-4-security--polish--portfolio-days-22-28)
4. [Level 3 Roadmap](#4-level-3-roadmap)
5. [JD Requirement Mapping](#5-jd-requirement-mapping)
6. [Claude Code Best Practices](#6-claude-code-best-practices)
7. [Daily Claude Code Session Template](#7-daily-claude-code-session-template)

---

## 1. Repository Setup

```
agentic-qa-platform/          ← your new public GitHub repo
├── src/
│   ├── agent/                ← core agent loop and orchestration
│   ├── analyzers/            ← schema analyzer, diff analyzer, risk scorer
│   ├── generators/           ← test generators (API, UI, integration, security)
│   ├── runners/              ← execution engines (pytest, playwright, k6)
│   ├── healers/              ← self-healing module
│   ├── gates/                ← quality gate engine
│   ├── reporters/            ← HTML and JSON report generation
│   └── config/               ← YAML config loader
├── tests/                    ← tests for the platform itself
├── generated_tests/          ← output: agent-generated test files
├── reports/                  ← output: quality reports
├── pipeline/                 ← Jenkinsfile, Docker configs
├── docs/
│   ├── architecture.md
│   └── adr/                  ← architecture decision records
├── saleor/                   ← git submodule or docker-compose reference
├── config.yaml               ← platform-wide configuration
├── ROADMAP.md
├── CLAUDE.md                 ← CRITICAL: context file for Claude Code sessions
└── README.md
```

**Before opening Claude Code — do these manually in order:**

```bash
# 1. Create and enter repo
mkdir agentic-qa-platform && cd agentic-qa-platform
git init
git remote add origin https://github.com/<your-handle>/agentic-qa-platform.git

# 2. Create CLAUDE.md NOW — before opening Claude Code
# (Claude Code auto-loads this file; it must exist before your first session)
cat > CLAUDE.md << 'EOF'
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
Nothing yet — Day 1 in progress.
EOF

# 3. Now open Claude Code — CLAUDE.md will be loaded automatically
# claude  (or open your IDE with Claude Code extension)

# 4. Install dependencies (can be done in Claude Code session or manually)
python -m venv .venv && source .venv/bin/activate
pip install httpx pytest playwright pydantic pyyaml python-dotenv openai
```

> **Rule**: Update the "Built So Far" section in `CLAUDE.md` at the end of every day.
> This is how Claude Code stays oriented across sessions.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Agentic QA Platform                   │
│                                                         │
│  ┌─────────────┐   ┌────────────────┐   ┌────────────┐ │
│  │  Schema &   │   │  Test Agent    │   │  Quality   │ │
│  │  Code       │──▶│  (Agent +      │──▶│  Gate      │ │
│  │  Analyzer   │   │  Tool Use)     │   │  Engine    │ │
│  └─────────────┘   └───────┬────────┘   └─────┬──────┘ │
│                            │                   │        │
│  ┌─────────────┐   ┌───────▼────────┐   ┌─────▼──────┐ │
│  │ Self-Heal   │◀──│  Test Runner   │   │  Reporter  │ │
│  │ Module      │──▶│  (pytest)      │   │  & Metrics │ │
│  └─────────────┘   └────────────────┘   └────────────┘ │
│                                                         │
│  ┌─────────────┐   ┌────────────────┐                   │
│  │ Perf Tests  │   │ Security Scan  │                   │
│  │ (k6)        │   │ (OWASP ZAP)    │                   │
│  └─────────────┘   └────────────────┘                   │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │               Jenkins CI/CD Pipeline              │  │
│  │  commit → analyze → generate → run → gate → report│  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Agentic Level definitions:**
- **Level 1** — LLM generates tests on demand; human triggers everything
- **Level 2** — Agent autonomously reacts to code changes; generates, runs, reports
- **Level 3** — Agent self-heals broken tests, adapts as app evolves, continuously learns

**Target for this project**: Level 2 solid, Level 3 demonstrated on the API layer, full Level 3 in the roadmap.

---

## 3. Day-by-Day Plan

---

### Week 1: Foundation + LLM Test Generation (Days 1-7)

**Week goal**: Saleor running locally. Agent generates API tests from GraphQL schema and runs them.

---

#### Day 1 — Environment & Repo Setup ✅ COMPLETED (2026-05-01)

**Outcome**: Saleor running on `localhost:8000`, repo scaffolded, OpenRouter API connected.

**Tasks**:
- [x] Create GitHub repo `agentic-qa-platform`, clone locally
- [x] Create `CLAUDE.md` manually — **before opening Claude Code** (see Section 1 setup)
- [x] Open Claude Code — now CLAUDE.md is loaded automatically into the session
- [x] Use the Day 1 Claude Code prompt below to scaffold the project structure
- [x] Create `.env` with `OPENROUTER_API_KEY`, `SALEOR_URL`
- [x] Start Saleor with Docker Compose (`docker compose up`)
- [x] Verify Saleor GraphQL playground at `localhost:8000/graphql/`
- [x] Update "Built So Far" in `CLAUDE.md` before closing the session
- [x] Initial commit: "chore: scaffold project structure"

**Completed**: docker-compose.yml (Saleor + PostgreSQL + Redis), src/config/settings.py (pydantic-settings), scripts/health_check.py

**Claude Code prompt for Day 1**:
```
I am building a production-grade agentic QA platform. Today I need to:
1. Set up the Python project structure in agentic-qa-platform/
2. Create a docker-compose.yml that runs Saleor (the open-source e-commerce platform)
   alongside its PostgreSQL and Redis dependencies
3. Create a src/config/settings.py that loads from .env using pydantic-settings
4. Verify the setup with a simple health check script

Use Python 3.12, pydantic v2, and the official Saleor docker-compose as reference.
The .env should contain: OPENROUTER_API_KEY, SALEOR_URL, SALEOR_GRAPHQL_URL
```

---

#### Day 2 — GraphQL Schema Analyzer ✅ COMPLETED (2026-05-01)

**Outcome**: Module that parses Saleor's full GraphQL schema into structured Python objects.

**Tasks**:
- [x] Build `src/analyzers/schema_analyzer.py`
- [x] Use GraphQL introspection query to fetch full schema from Saleor
- [x] Parse into Pydantic models: `GraphQLOperation`, `GraphQLField`, `GraphQLType`
- [x] Output: dict of all queries and mutations with their input/output types
- [x] Write 3-5 unit tests for the analyzer
- [x] Commit: "feat: GraphQL schema analyzer"

**Completed**: Full introspection support with 13 unit tests, extracting all queries/mutations/types

**Claude Code prompt for Day 2**:
```
I need to build src/analyzers/schema_analyzer.py for my agentic QA platform.

This module should:
1. Send a GraphQL introspection query to SALEOR_GRAPHQL_URL (from settings)
2. Parse the response into Pydantic v2 models representing operations (queries/mutations),
   their input types, required fields, and return types
3. Expose a SchemaAnalyzer class with methods:
   - get_all_queries() -> list[GraphQLOperation]
   - get_all_mutations() -> list[GraphQLOperation]
   - get_operation_by_name(name: str) -> GraphQLOperation
4. Include unit tests in tests/test_schema_analyzer.py using pytest with httpx mocking

Keep the models minimal — only extract what's needed for test generation later.
```

---

#### Day 3 — LLM Refresher + Test Generator v1 ✅ COMPLETED (2026-05-02)

**Outcome**: OpenRouter generates structured pytest test cases from a schema fragment using structured output.

**Tasks**:
- [x] Build `src/generators/api_test_generator.py`
- [x] Prompt OpenRouter with a GraphQL operation + schema → get back a `TestCase` Pydantic model
- [x] `TestCase` contains: test name, setup steps, GraphQL query/mutation body, assertions
- [x] Write generated test to a `.py` file in `generated_tests/api/`
- [x] Verify 3 generated tests run against live Saleor
- [x] Commit: "feat: LLM-powered API test generator v1"

**Completed**: ApiTestGenerator with structured output, 5 unit tests, integration with OpenRouter

**Claude Code prompt for Day 3**:
```
I need to build src/generators/api_test_generator.py.

This module takes a GraphQLOperation object (from the schema analyzer) and uses the
OpenRouter API (openai/gpt-oss-120b:free model for cost efficiency) to generate a pytest
test case.

Requirements:
1. Use structured output with Pydantic v2 — return a TestCase model containing:
   - test_name: str
   - description: str
   - graphql_query: str  (the actual GQL query/mutation to execute)
   - variables: dict     (example variables to use)
   - assertions: list[str]  (what to assert on the response)
   - test_code: str     (complete executable pytest function as a string)

2. The prompt to OpenRouter should include the operation schema, Saleor's base URL,
   and instructions to generate realistic test data (not placeholder values)

3. Write the test_code to generated_tests/api/{test_name}.py

4. The generated test should use httpx to call Saleor's GraphQL endpoint directly

Show me the full implementation including the OpenRouter API call with proper error handling.
```

---

#### Day 4 — Test Generator v2: Tool Use ✅ COMPLETED (2026-05-02)

**Outcome**: Generator uses OpenRouter tool use to introspect schema dynamically during generation.

**Tasks**:
- [x] Add tool definitions to the generator: `introspect_schema`, `get_related_type`, `check_existing_tests`
- [x] Agent calls tools during generation to resolve complex type dependencies
- [x] Test: generate tests for a mutation that has nested input types (e.g., `createOrder`)
- [x] Commit: "feat: tool-use-powered test generation"

**Completed**: Type introspection with `get_type_definition()`, recursive destructuring of nested InputObject types, 18 total tests passing

**Claude Code prompt for Day 4**:
```
I need to upgrade src/generators/api_test_generator.py to use OpenRouter tool use
(function calling).

Current state: the generator sends a single prompt and gets back a TestCase.
Problem: complex mutations have nested types that don't fit in one prompt.

Add these tools that OpenRouter can call during generation:
1. introspect_type(type_name: str) → returns the full type definition from the schema
2. list_existing_tests(operation_name: str) → returns names of already-generated tests
3. get_example_response(operation_name: str) → makes a real call to Saleor and returns
   the actual response structure for OpenRouter to learn from

Implement the tool-use loop: send message → if tool_use in response → execute tool →
send result back → continue until final response.

Target operation: CheckoutCreate mutation (which has complex nested input).
```

---

#### Day 5 — Test Runner ✅ COMPLETED (2026-05-03)

**Outcome**: Execution engine that runs generated tests, captures structured results.

**Tasks**:
- [x] Build `src/runners/pytest_runner.py`
- [x] Runs all tests in `generated_tests/` directory using pytest programmatic API
- [x] Captures results: test name, status (pass/fail/error), duration, error message, response data
- [x] Returns `PytestRunResult` Pydantic model
- [x] Commit: "feat: pytest test runner with structured results"

**Completed**: Custom pytest plugin (ResultCollector) with full exception capture, PytestRunResult and SingleTestResult models, test filtering and pattern support, 27 total tests passing (18 existing + 9 new)

**Claude Code prompt for Day 5**:
```
I need to build src/runners/pytest_runner.py.

This module runs pytest programmatically against all files in the generated_tests/
directory and returns structured results.

Requirements:
1. Use pytest's Python API (pytest.main with a custom plugin) to capture results
2. Return a PytestRunResult Pydantic v2 model containing:
   - total: int
   - passed: int
   - failed: int
   - errors: int
   - duration_seconds: float
   - test_results: list[SingleTestResult]
   where SingleTestResult has: test_name, status, duration, error_message, stdout
3. Support filtering: run only tests matching a pattern or in a specific directory
4. Do NOT use subprocess — use pytest's Python API directly

Show the full implementation. I will use this runner from other modules.
```

---

#### Day 6 — Coverage Analyzer ✅ COMPLETED (2026-05-03)

**Outcome**: Module that identifies schema coverage gaps and drives what the agent generates next.

**Tasks**:
- [x] Build `src/analyzers/coverage_analyzer.py`
- [x] Compares list of all schema operations vs. existing generated tests
- [x] Outputs coverage report: covered %, uncovered operations, priority order
- [x] Priority scoring: mutations > queries, auth-required > public, complex types > simple
- [x] Commit: "feat: test coverage analyzer"

**Completed**: CoverageAnalyzer with priority scoring (+20 mutations, +15 CRUD, +25 checkout/payment/order, -10 similar), CoverageReport Pydantic model, 8 new unit tests, all 35 tests passing

**Claude Code prompt for Day 6**:
```
I need to build src/analyzers/coverage_analyzer.py.

This module compares:
- All GraphQL operations discovered by SchemaAnalyzer
- All test files present in generated_tests/api/

And produces a CoverageReport Pydantic model containing:
- total_operations: int
- covered_operations: int
- coverage_percentage: float
- uncovered: list[GraphQLOperation]
- covered: list[str]  (operation names)
- priority_queue: list[GraphQLOperation]  (uncovered, sorted by priority)

Priority scoring logic (implement as a method):
- Mutations score higher than queries (+20)
- Operations with "create", "update", "delete" in name score higher (+15)
- Operations touching checkout, payment, order score highest (+25)
- Operations already tested by similar tests score lower (-10)

This module drives what the agent generates next.
```

---

#### Day 7 — Week 1 Integration + Polish

**Outcome**: Single command generates 50+ tests, runs them, and reports coverage.

**Tasks**:
- [ ] Build `src/agent/generate_command.py` — orchestrates: analyze schema → check coverage → generate for top uncovered → run → report
- [ ] Wire all Week 1 modules together
- [ ] Target: 50+ passing API tests generated
- [ ] Write `docs/architecture.md` Week 1 section
- [ ] Update README with Week 1 section: what it does, how to run it
- [ ] Commit: "feat: Week 1 complete — LLM-driven API test generation"

---

### Week 2: Autonomous Test Agent Level 2 (Days 8-14)

**Week goal**: Agent reacts to code changes autonomously — analyzes git diffs, decides what to test, generates targeted tests, runs them, and reports.

---

#### Day 8 — Git Diff Analyzer

**Outcome**: Module that parses a git diff and maps changed code to affected API operations.

**Tasks**:
- [ ] Build `src/analyzers/diff_analyzer.py`
- [ ] Parses `git diff <range>` output into structured `CodeChange` objects
- [ ] Maps changed Python files → affected Django views/resolvers → GraphQL operations
- [ ] Returns `DiffAnalysis` with changed files, affected operations, change types
- [ ] Commit: "feat: git diff analyzer"

**Claude Code prompt for Day 8**:
```
I need to build src/analyzers/diff_analyzer.py for my agentic QA platform.

Saleor is a Django/GraphQL app. When code changes, I need to know which GraphQL
operations are affected.

This module should:
1. Run `git diff <base>..<head>` (using Python subprocess) against the Saleor repo path
2. Parse the unified diff into CodeChange objects: file_path, change_type, added_lines, removed_lines
3. Map changed files to GraphQL operations using these heuristics:
   - saleor/graphql/**/mutations/*.py → extract mutation class names → map to operation names
   - saleor/graphql/**/resolvers.py → extract resolver names → map to query names
   - saleor/*/models.py → affects all operations touching that model's type name
4. Return DiffAnalysis: changed_files, affected_operations, untraced_changes

Use Pydantic v2 for all models. Include unit tests with sample diff fixtures.
```

---

#### Day 9 — Risk Scorer

**Outcome**: Agent uses OpenRouter to assess risk level of each code change and prioritize testing.

**Tasks**:
- [ ] Build `src/analyzers/risk_scorer.py`
- [ ] OpenRouter analyzes the diff + affected operations → assigns risk score + rationale
- [ ] Risk levels: CRITICAL, HIGH, MEDIUM, LOW with explanations
- [ ] Output informs which tests to generate first
- [ ] Commit: "feat: LLM-powered risk scorer"

**Claude Code prompt for Day 9**:
```
I need to build src/analyzers/risk_scorer.py.

Input: a DiffAnalysis object (from diff_analyzer.py) and the list of affected GraphQL operations.

This module sends the diff summary and affected operations to OpenRouter (openai/gpt-oss-120b:free)
and gets back a structured risk assessment.

Output — RiskAssessment Pydantic model:
- overall_risk: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
- rationale: str  (2-3 sentence explanation)
- operation_risks: list[OperationRisk]
  where OperationRisk = operation_name, risk_level, reason, suggested_test_focus: list[str]
- recommended_test_count: int  (how many tests to generate for this change)

The OpenRouter prompt should explain what each risk level means in context of an e-commerce
system (CRITICAL = payment/auth flows, HIGH = cart/checkout, etc.) so it can make
appropriate judgements.
```

---

#### Day 10 — Full Agent Loop

**Outcome**: Single entry point: detect change → analyze → generate → run → report. No human steps in between.

**Tasks**:
- [ ] Build `src/agent/core.py` — the main agent orchestrator
- [ ] Entry point: `python -m agent run --diff HEAD~3..HEAD`
- [ ] Full cycle: diff → risk score → targeted test generation → run → quality gate check → report
- [ ] Agent persists state between runs (what was generated, what passed last time)
- [ ] Commit: "feat: autonomous agent loop v1"

**Claude Code prompt for Day 10**:
```
I need to build the core agent loop in src/agent/core.py.

This is the main orchestrator that ties together all Week 1-2 modules.

The agent should:
1. Accept --diff <range> CLI argument (use argparse or typer)
2. Run DiffAnalyzer to get affected operations
3. Run RiskScorer to prioritize
4. For each HIGH/CRITICAL operation: run ApiTestGenerator to generate tests
5. Run PytestRunner on newly generated tests
6. Load previous run state from .agent_state.json (which tests passed last time)
7. Produce a RunReport: new tests generated, pass/fail counts, risk summary, regressions

The agent should be stateless between generations but stateful about test history.
Make the agent runnable as: python -m agent run --diff HEAD~3..HEAD

Use typer for the CLI. Keep the orchestration logic clean — each step should be
a separate function call, no nested business logic in the loop itself.
Use OpenRouter API for all LLM calls (generation and reasoning).
```

---

#### Day 11 — Playwright UI Test Generation

**Outcome**: Agent generates Playwright tests for Saleor's storefront for critical user flows.

**Tasks**:
- [ ] Build `src/generators/ui_test_generator.py`
- [ ] OpenRouter generates Playwright test code for flows: search, add-to-cart, checkout start
- [ ] Generated tests land in `generated_tests/ui/`
- [ ] Tests run headless against Saleor storefront
- [ ] Commit: "feat: Playwright UI test generator"

**Claude Code prompt for Day 11**:
```
I need to build src/generators/ui_test_generator.py.

This generates Playwright tests (using playwright-python) for Saleor's React storefront
running at localhost:3000.

The generator should:
1. Accept a flow_name: str describing the user flow (e.g. "search and add product to cart")
2. Use OpenRouter to generate a complete Playwright test in async Python
3. The generated test should use page fixtures, have clear step comments, and include
   realistic assertions (element visible, text content, URL changes)
4. Write output to generated_tests/ui/test_{flow_name}.py

Start with these 3 flows:
- "search for a product by name and verify results"
- "add a product to cart and verify cart count"
- "navigate through checkout steps to payment page"

The OpenRouter prompt should include the Saleor storefront URL and note it is a
React/Next.js app with standard e-commerce UI patterns.
```

---

#### Day 12 — Integration Test Generation

**Outcome**: Agent generates tests that span API + UI — create via API, verify on storefront.

**Tasks**:
- [ ] Build `src/generators/integration_test_generator.py`
- [ ] Cross-layer tests: API mutation → UI verification, or UI action → API state check
- [ ] Generate 3-5 integration scenarios covering product, cart, and order flows
- [ ] Commit: "feat: cross-layer integration test generator"

**Claude Code prompt for Day 12**:
```
I need to build src/generators/integration_test_generator.py.

Integration tests in this system span multiple layers — they use both the GraphQL API
and Playwright to verify behavior end-to-end.

Example scenario: "Create a product via GraphQL mutation, then verify it appears
on the storefront product listing page via Playwright."

The generator should:
1. Accept a scenario_description: str
2. Use OpenRouter to generate a pytest test that:
   - Uses httpx for GraphQL API calls (with auth token from env)
   - Uses Playwright for UI steps
   - Has clear setup/action/assertion phases
   - Cleans up created data after the test (teardown)
3. Output to generated_tests/integration/test_{scenario}.py

Generate these 3 scenarios:
1. Create product via API → verify on storefront
2. Add to cart via UI → verify cart via API
3. Complete checkout via API → verify order status via UI
```

---

#### Day 13 — Smart Reporter

**Outcome**: HTML + JSON reports that are professional enough to show in interviews.

**Tasks**:
- [ ] Build `src/reporters/report_generator.py`
- [ ] JSON report: full structured data for CI consumption
- [ ] HTML report: visual summary with risk assessment, coverage chart, pass/fail stats
- [ ] Include: tests generated this run, regression delta, agent's reasoning summary
- [ ] Commit: "feat: HTML and JSON quality reports"

**Claude Code prompt for Day 13**:
```
I need to build src/reporters/report_generator.py that produces professional quality reports.

Input: RunReport object from the agent core.

Output 1 — reports/latest.json: full machine-readable report
Output 2 — reports/latest.html: visual report with:
  - Header: run timestamp, git range tested, overall pass/fail
  - Risk summary section: what changed, risk levels assigned
  - Test results table: test name, layer (api/ui/integration), status, duration
  - Coverage section: % of API covered, delta from last run
  - Agent reasoning: what the agent decided and why (from risk scorer rationale)

Use Jinja2 for the HTML template. Keep it clean — no external CSS frameworks,
just inline styles. It should look professional when screenshot for a portfolio.

The JSON schema should be documented with field descriptions for README reference.
```

---

#### Day 14 — Week 2 Integration + Polish

**Outcome**: Full Level 2 demo works end-to-end. One command, zero manual steps.

**Tasks**:
- [ ] End-to-end test: simulate a Saleor code change, run the agent, verify report
- [ ] Handle all edge cases: empty diffs, Saleor unreachable, API rate limits
- [ ] Update README with Level 2 demo instructions
- [ ] Record or document the demo flow
- [ ] Commit: "feat: Week 2 complete — autonomous test agent Level 2"

---

### Week 3: Self-Healing + CI/CD + Performance (Days 15-21)

**Week goal**: Tests heal themselves when the app changes. Jenkins pipeline enforces quality gates. k6 performance baselines established.

---

#### Day 15 — Failure Classifier

**Outcome**: When tests fail, the agent classifies the root cause automatically.

**Tasks**:
- [ ] Build `src/healers/failure_classifier.py`
- [ ] Input: failed test + error message + test code + recent diff
- [ ] OpenRouter classifies: APP_BUG | TEST_STALE | ENVIRONMENT | FLAKY | UNKNOWN
- [ ] APP_BUG and UNKNOWN are escalated (not auto-healed)
- [ ] TEST_STALE and FLAKY proceed to healer
- [ ] Commit: "feat: AI-powered failure classifier"

**Claude Code prompt for Day 15**:
```
I need to build src/healers/failure_classifier.py.

When a generated test fails, this module uses OpenRouter to classify the root cause.

Input: FailedTest object containing:
- test_name, test_code (the full test source), error_message, stack_trace
- recent_diff (the git diff that preceded this failure, if any)
- last_passing_run (timestamp of last success)

OpenRouter should classify into one of:
- APP_BUG: the application code has a bug; test is correct
- TEST_STALE: the app changed (schema, URL, selector); test needs updating
- ENVIRONMENT: Saleor is down or misconfigured; retry will likely fix
- FLAKY: timing issue, intermittent; retry with backoff
- UNKNOWN: cannot determine; needs human review

Output: FailureClassification with: category, confidence (0.0-1.0), reasoning, suggested_fix_hint

Low confidence (<0.7) should always escalate to human regardless of category.
```

---

#### Day 16 — Self-Healing Engine

**Outcome**: Agent auto-patches TEST_STALE failures, re-runs, confirms green. This is the Level 3 moment.

**Tasks**:
- [ ] Build `src/healers/self_healer.py`
- [ ] For TEST_STALE: OpenRouter generates a patched version of the test
- [ ] Patching strategies: update GraphQL query fields, update assertions, update variables
- [ ] Apply patch, re-run the test, verify it passes before committing the fix
- [ ] If patched test still fails: escalate, do not commit
- [ ] Commit: "feat: self-healing engine for stale tests"

**Claude Code prompt for Day 16**:
```
I need to build src/healers/self_healer.py — this is the core "self-healing" capability.

Input: a FailedTest with category=TEST_STALE and a FailureClassification.

The healer should:
1. Call OpenRouter with: original test code, error message, current schema for the operation,
   and the fix_hint from the classifier
2. OpenRouter returns a patched test code (full replacement, not a diff)
3. Write the patched code to a temp file, run it with PytestRunner
4. If it passes: replace the original file, log the heal event to heals.jsonl
5. If it still fails: log as HEAL_FAILED, keep original, flag for human

HealEvent logged to heals.jsonl:
- timestamp, test_name, original_error, fix_applied, confidence, outcome (HEALED/FAILED)

This audit trail is important for the portfolio — it shows governance over autonomous changes.

Implement a --dry-run flag that shows what would be patched without applying.
```

---

#### Day 17 — Healing Audit Trail + Human Escalation

**Outcome**: Every auto-fix is logged and auditable. Low-confidence fixes are held for review.

**Tasks**:
- [ ] Build `src/healers/escalation_manager.py`
- [ ] Maintains a `needs_review.json` queue of tests that need human attention
- [ ] CLI command: `python -m agent review` — shows pending escalations with context
- [ ] Mark as resolved: `python -m agent resolve --test <name> --action accept|reject`
- [ ] Commit: "feat: human escalation manager for healing audit"

---

#### Day 18 — Jenkins Pipeline

**Outcome**: Local Jenkins runs the full agent pipeline on every simulated commit.

**Tasks**:
- [ ] Set up Jenkins in Docker (`docker run jenkins/jenkins:lts`)
- [ ] Write `pipeline/Jenkinsfile` with stages:
  1. Checkout
  2. Start Saleor (docker compose)
  3. Run Agent (`python -m agent run --diff HEAD~1..HEAD`)
  4. Quality Gate check
  5. Archive reports as Jenkins artifacts
  6. Notify (write to a log file, or send email if configured)
- [ ] Commit: "feat: Jenkins CI pipeline"

**Claude Code prompt for Day 18**:
```
I need to write a Jenkinsfile for my agentic QA platform.

The pipeline should:
1. Stage: Checkout — git checkout
2. Stage: Environment — start Saleor via docker compose up -d, wait for health check
3. Stage: Install Dependencies — pip install -r requirements.txt in virtualenv
4. Stage: Run Agent — python -m agent run --diff ${GIT_PREVIOUS_COMMIT}..${GIT_COMMIT}
5. Stage: Quality Gate — python -m agent gate --report reports/latest.json
   (exits non-zero if gate fails, failing the build)
6. Stage: Archive — archive reports/latest.html and reports/latest.json as artifacts
7. Post: always — docker compose down

The gate stage should fail the build if:
- API test coverage drops below 40%
- Any CRITICAL risk operation has failing tests
- Self-healing produced unreviewed escalations

Write a declarative Jenkinsfile. Also provide the docker-compose.jenkins.yml
to run Jenkins locally alongside Saleor.
```

---

#### Day 19 — Quality Gate Engine

**Outcome**: Configurable, enforceable quality gates that integrate with CI.

**Tasks**:
- [ ] Build `src/gates/quality_gate.py`
- [ ] Rules loaded from `config.yaml`: min coverage %, required layers, max failures
- [ ] Gate produces detailed pass/fail with per-rule breakdown
- [ ] Exit code 0 = pass, 1 = fail (for CI integration)
- [ ] Commit: "feat: configurable quality gate engine"

**Claude Code prompt for Day 19**:
```
I need to build src/gates/quality_gate.py.

This reads rules from config.yaml and evaluates them against the latest RunReport.

config.yaml gate section:
```yaml
quality_gate:
  min_api_coverage_percent: 40
  required_test_layers: ["api", "integration"]
  max_allowed_failures: 0
  critical_operations_must_pass: ["checkoutComplete", "tokenCreate"]
  max_heal_failures_before_block: 3
```

The gate should:
1. Load rules from config
2. Evaluate each rule against RunReport
3. Return GateResult: overall_pass, rules: list[RuleResult]
   where RuleResult = rule_name, passed, actual_value, threshold, message
4. Print a formatted table to stdout (use rich library)
5. Exit with code 1 if overall_pass is False

This is what the Jenkinsfile calls. Make it clean — the output will be in Jenkins logs.
```

---

#### Day 20 — Performance Testing with k6

**Outcome**: Agent generates k6 performance test scenarios from schema, enforces baselines.

**Tasks**:
- [ ] Build `src/runners/k6_runner.py` — runs k6 tests, parses results
- [ ] Build `src/generators/perf_test_generator.py` — OpenRouter generates k6 JS from operation schema
- [ ] Baseline thresholds in config.yaml: p95 < 500ms, error rate < 1%
- [ ] k6 results feed into quality gate
- [ ] Commit: "feat: k6 performance test generation and execution"

**Claude Code prompt for Day 20**:
```
I need to add performance testing to my agentic QA platform.

Part 1 — src/generators/perf_test_generator.py:
Use OpenRouter to generate k6 JavaScript test scripts from a GraphQL operation definition.
The script should simulate realistic load (10 VUs, 30s duration) and include:
- Realistic GraphQL POST requests with example variables
- Thresholds: http_req_duration p(95) < 500, http_req_failed < 0.01
- Tags for operation name (for filtering in results)
Output to generated_tests/performance/test_{operation_name}.js

Part 2 — src/runners/k6_runner.py:
Run k6 via subprocess (assume k6 is installed locally).
Parse the JSON summary output (--summary-export) into a Perf Result Pydantic model:
- operation_name, p50, p95, p99, error_rate, vus, duration_seconds, threshold_passed

Generate k6 tests for: productList query, checkoutCreate mutation, tokenCreate mutation.
```

---

#### Day 21 — Week 3 Integration + Self-Healing Demo

**Outcome**: Demonstrate self-healing working in CI. Pipeline shows a test fail, heal, and re-run green.

**Tasks**:
- [ ] Create a scripted demo: modify a Saleor schema field → run agent → test fails → healer fires → test is patched → pipeline goes green
- [ ] Document the demo in `docs/self-healing-demo.md` with screenshots
- [ ] Ensure Jenkins pipeline completes end-to-end
- [ ] Commit: "feat: Week 3 complete — self-healing + CI/CD + performance"

---

### Week 4: Security + Polish + Portfolio (Days 22-28)

**Week goal**: Security scanning added. Project is interview-ready with demo, docs, and roadmap.

---

#### Day 22 — OWASP ZAP Integration

**Outcome**: ZAP passive scan runs against Saleor; findings parsed into quality gate.

**Tasks**:
- [ ] Run OWASP ZAP in Docker: `docker run -d owasp/zap2docker-stable`
- [ ] Build `src/runners/zap_runner.py` — triggers ZAP passive scan via REST API
- [ ] Parse ZAP JSON alerts into `SecurityFinding` Pydantic models
- [ ] HIGH severity findings fail the quality gate (configurable)
- [ ] Commit: "feat: OWASP ZAP security scanning integration"

**Claude Code prompt for Day 22**:
```
I need to integrate OWASP ZAP passive scanning into my agentic QA platform.

ZAP will run as a Docker container: owasp/zap2docker-stable
It exposes a REST API at localhost:8090.

Build src/runners/zap_runner.py that:
1. Starts a ZAP session via the REST API
2. Spiders the target URL (Saleor at localhost:8000) for discovery
3. Waits for passive scan to complete (poll /JSON/pscan/view/recordsToScan)
4. Fetches alerts via /JSON/core/view/alerts
5. Returns list[SecurityFinding] with: risk_level (HIGH/MEDIUM/LOW/INFO),
   name, description, url, solution

Then add a security gate rule to quality_gate.py:
- Fail if any HIGH risk finding is present
- Warn (but not fail) for MEDIUM findings
- Include finding count in the quality report
```

---

#### Day 23 — Security Test Generation

**Outcome**: Agent generates basic security-oriented API tests showing security awareness.

**Tasks**:
- [ ] Build `src/generators/security_test_generator.py`
- [ ] 3 categories of generated security tests:
  1. Auth bypass: access mutations without token
  2. Input validation: inject malformed/oversized GraphQL variables
  3. Rate limiting: detect if brute-force is possible on tokenCreate
- [ ] 5-10 security tests generated and running
- [ ] Commit: "feat: security-oriented test generation"

---

#### Day 24 — Configuration & Extensibility

**Outcome**: Platform is configurable via YAML and not hardcoded to Saleor.

**Tasks**:
- [ ] Finalize `config.yaml` — all settings in one place (LLM model, URLs, gate rules, test dirs)
- [ ] Add `adapters/` pattern: `SaleorAdapter` implements a `TargetAdapter` interface
- [ ] Document: "to test a different app, implement TargetAdapter and update config.yaml"
- [ ] This shows architectural thinking in interviews
- [ ] Commit: "refactor: configurable adapter pattern for extensibility"

---

#### Day 25 — README + Architecture Documentation

**Outcome**: README is portfolio-quality. Someone reading it for 2 minutes understands the value.

**Tasks**:
- [ ] Write final `README.md` (structure below)
- [ ] Write `docs/architecture.md` with full architecture diagram + module descriptions
- [ ] Write 2-3 ADRs in `docs/adr/`: why OpenRouter/gpt-oss-120b over other options, why pytest over unittest, why Saleor
- [ ] Commit: "docs: production-quality README and architecture docs"

**README structure**:
```markdown
# Agentic QA Platform
[one-line description]

## Demo
[GIF or screenshot of agent running]

## The Problem This Solves
[3 sentences on why traditional QA doesn't scale with AI-generated code]

## Architecture
[architecture diagram]

## Modules
[table: module name, what it does, key technology]

## Quick Start
[5 commands to get it running]

## Capabilities
- [ ] Autonomous API test generation from GraphQL schema
- [ ] Cross-layer test generation (API + UI + integration)
- [ ] Self-healing tests with audit trail
- [ ] Risk-based test prioritization from git diffs
- [ ] Quality gates in Jenkins CI pipeline
- [ ] Performance baselines with k6
- [ ] Security scan integration (OWASP ZAP)

## Roadmap → Level 3
[link to ROADMAP.md]
```

---

#### Day 26 — Demo Recording / Walkthrough

**Outcome**: A demo artifact you can share in interviews and on LinkedIn.

**Tasks**:
- [ ] Write `docs/demo-script.md` — scripted 5-minute walkthrough of the full agent cycle
- [ ] Record using a screen recorder or create an animated GIF using `vhs` or `asciinema`
- [ ] Demo must show: git diff → agent run → report → self-healing → CI pipeline green
- [ ] Add demo link to README

---

#### Day 27 — ROADMAP.md + Final Code Quality Pass

**Outcome**: Roadmap document shows strategic thinking. Code is clean and consistent.

**Tasks**:
- [ ] Write `ROADMAP.md` (see Section 4 below)
- [ ] Run `ruff` and `mypy` across the whole codebase, fix issues
- [ ] Ensure all modules have proper type hints
- [ ] Add `pyproject.toml` with tool configs (ruff, mypy, pytest)
- [ ] Commit: "chore: code quality pass + type hints"

---

#### Day 28 — Final Polish + v1.0 Tag

**Outcome**: The repo is public, clean, and shareable.

**Tasks**:
- [ ] Final end-to-end run: everything works from a fresh clone
- [ ] Write `CONTRIBUTING.md` (brief)
- [ ] Tag `v1.0.0` release on GitHub with release notes
- [ ] Push to GitHub, verify README renders correctly
- [ ] Post to LinkedIn (optional draft in `docs/linkedin-post-draft.md`)
- [ ] Commit: "chore: v1.0 release"

---

## 4. Level 3 Roadmap

> Include this in `ROADMAP.md` in the repository.

### Level 3: Full Agentic Ecosystem (3-6 Month Horizon)

**1. Continuous Learning**
- Agent learns from historical test results to improve generation quality
- Flaky test detection and automatic quarantine with retry budgets
- Test effectiveness scoring: which tests actually catch bugs vs. green-washing

**2. Multi-App Generalization**
- Plugin architecture: swap Saleor for any app with an OpenAPI or GraphQL spec
- Auto-discovery of test targets — no manual schema pointing
- Support REST (OpenAPI 3.x), GraphQL, gRPC via protocol adapters

**3. Self-Evolving Test Suites**
- Agent monitors production error logs → generates regression tests for real incidents
- Mutation testing integration: agent verifies its own tests actually catch bugs
- Test pruning: agent removes redundant tests to keep suite fast and maintainable

**4. Advanced Self-Healing**
- UI test healing via visual diff (not just CSS selectors)
- Cross-layer healing: API schema change automatically updates integration + UI tests
- Healing confidence calibration from historical heal success rates

**5. Team Collaboration Layer**
- GitHub PR bot: posts auto-generated test suggestions as PR review comments
- Slack/Teams integration for quality reports and escalation notifications
- Dashboard for test generation metrics, coverage trends, heal rates over time

**6. Production Observability Loop**
- Connect to APM (Datadog/Grafana) → auto-generate performance tests for degrading endpoints
- Canary test generation for new deployments: generate smoke tests from recent changes
- Incident → regression test pipeline: production incident creates a test automatically

---

## 5. JD Requirement Mapping

| JD Requirement | Where Demonstrated | Status |
|---|---|---|
| End-to-end quality: unit, API, integration, UI | Multi-layer generators in Week 1-2 | ✅ Week 2 |
| Define quality engineering roadmap | ROADMAP.md + phased architecture | ✅ Week 4 |
| Agentic systems that auto-generate tests | Test Agent + tool use | ✅ Week 1-2 |
| Self-healing automation frameworks | Self-Healing Engine + audit trail | ✅ Week 3 |
| Regression systems for AI-generated code | Diff Analyzer + Risk Scorer | ✅ Week 2 |
| Quality gates in CI/CD | Jenkins pipeline + Gate Engine | ✅ Week 3 |
| Playwright/Cypress/Selenium expertise | Playwright UI generator | ✅ Week 2 |
| LLM experience (OpenRouter) | Tool use, structured output, agent loop | ✅ Throughout |
| CI/CD pipelines | Jenkins pipeline-as-code | ✅ Week 3 |
| Performance testing | k6 generation + execution | ✅ Week 3 |
| Security testing | ZAP integration + security test gen | ✅ Week 4 |
| Architectural thinking | Adapter pattern, YAML config, ADRs | ✅ Week 4 |

---

## 6. Claude Code Best Practices

### 6.1 — Create a `CLAUDE.md` File First (Day 1, Before Anything Else)

`CLAUDE.md` is loaded into every Claude Code session automatically. It is the single most impactful thing you can do for consistency across sessions.

**What to put in `CLAUDE.md`:**
```markdown
# Agentic QA Platform — Context for Claude Code

## Project Summary
An AI-driven QA platform that autonomously generates, executes, and self-heals tests
for Saleor (Python/Django e-commerce). Target role: Chief Agentic Quality Architect.

## Stack
- Python 3.12, Pydantic v2, pytest, Playwright, httpx
- OpenRouter API (gpt-oss-120b:free for generation, Claude Sonnet 4.6 fallback for reasoning)
- Saleor GraphQL at localhost:8000/graphql/
- Saleor storefront at localhost:3000
- Jenkins at localhost:8080

## Code Conventions
- All data models use Pydantic v2 with strict=True
- All public functions have type hints
- No print() — use Python logging module
- Generated test files go to generated_tests/{layer}/
- Reports go to reports/

## Module Responsibilities (do not mix concerns)
- src/analyzers/: read-only analysis, no side effects
- src/generators/: produce test code, do not execute
- src/runners/: execute tests, do not generate
- src/healers/: modify existing tests, never generate new ones
- src/agent/: orchestrate only, no business logic

## What has been built so far
[Update this section daily as you complete modules]
```

---

### 6.2 — Session Structure: One Module Per Session

Each Claude Code session should have a clear, bounded scope. Don't try to build two modules in one session.

**Good session scope:**
- "Build the SchemaAnalyzer class"
- "Add tool use to the test generator"
- "Write the Jenkinsfile"

**Bad session scope:**
- "Build Week 1"
- "Make the agent work"

---

### 6.3 — The Prompting Pattern That Works Best

Use this structure for every implementation prompt:

```
CONTEXT: [what module this is, what already exists, what it connects to]
TASK: [exactly what to build today]
CONSTRAINTS: [pydantic v2, no subprocess in generators, etc.]
OUTPUT: [where files should go, what the interface looks like]
DO NOT: [common things Claude will try to do that you don't want]
```

**Example:**
```
CONTEXT: I am building agentic-qa-platform. The SchemaAnalyzer in
src/analyzers/schema_analyzer.py is complete. I need the next module.

TASK: Build src/generators/api_test_generator.py that takes a GraphQLOperation
and returns a TestCase using the OpenRouter API with structured output.

CONSTRAINTS:
- Use Pydantic v2 for all models
- Use openai/gpt-oss-120b:free for cost efficiency
- The TestCase.test_code must be a complete, executable pytest function

OUTPUT: The module file + unit tests in tests/test_api_test_generator.py

DO NOT: Add a CLI entrypoint, add logging setup (already configured), import from
modules that don't exist yet.
```

---

### 6.4 — Always Tell Claude What Already Exists

Start each session by reading the current state:

```
Read the current state of these files before starting:
- src/analyzers/schema_analyzer.py (this is what you'll consume)
- src/config/settings.py (this is how config is loaded)
- tests/conftest.py (this is the existing test setup)

Then build the next module without changing any of the above.
```

This prevents Claude from reimplementing things you've already built.

---

### 6.5 — Commit After Every Module

Never end a Claude Code session without committing. This gives you:
- A safe rollback point
- Clear git history that shows your progress (good for interviews)
- Context anchors for the next session

```bash
git add src/generators/api_test_generator.py tests/test_api_test_generator.py
git commit -m "feat: LLM-powered API test generator with structured output"
```

Use conventional commits throughout: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`

---

### 6.6 — When Claude Goes Off-Track

Signs Claude is going off-track in a session:
- It's modifying files you didn't ask it to touch
- It's adding abstractions not in the spec
- The implementation is growing beyond ~200 lines for a single module

**Recovery prompt:**
```
Stop. You are modifying [file] which I did not ask you to change.
Revert those changes and focus only on [specific file].
The implementation should be under 150 lines. If it's growing beyond that,
ask me which part to simplify rather than adding complexity.
```

---

### 6.7 — Testing Each Module Before Moving On

Before ending a session, verify the module works:

```
Before we finish this session:
1. Run the unit tests for this module: pytest tests/test_{module}.py -v
2. Run a quick integration check: python -c "from src.generators.api_test_generator import ApiTestGenerator; print('import OK')"
3. If anything fails, fix it before we commit.
```

---

### 6.8 — Managing the OpenRouter API Cost

- Use `openai/gpt-oss-120b:free` for high-volume generation (test generation loops)
- Use `anthropic/claude-sonnet-4.6` (paid fallback) only for reasoning tasks (risk scoring, failure classification, self-healing)
- Add `max_tokens=1024` guards on generation calls to prevent runaway costs
- Estimated total cost for the project: **Free-tier for generation, $5-10 USD for fallback reasoning**

---

### 6.9 — Use `/plan` Before Complex Sessions

For any session involving multiple files or non-obvious architecture, type `/plan` first.
Describe what you want to build, let Claude present the approach, then approve before it writes code.

This prevents large amounts of code you have to throw away.

---

### 6.10 — Portfolio Hygiene (Do These Throughout)

- Every module should have a module-level docstring explaining its role in the system
- Keep `generated_tests/` in `.gitignore` but commit a `generated_tests/.gitkeep`
  Actually — **do commit a sample of generated tests** (10-15) to show what the agent produces
- Keep `reports/` gitignored but commit `reports/sample-report.html` as a demo artifact
- Use `git tag` at end of each week: `v0.1-week1`, `v0.2-week2`, etc.

---

## 7. Daily Claude Code Session Template

Copy this at the start of each working session:

```markdown
## Session: Day [N] — [Module Name]

**What was built yesterday**: [1 sentence]
**Today's goal**: [1 sentence]
**Files to build**: [list]
**Files that already exist and must not change**: [list]

### Prompt:
CONTEXT: [describe what's built so far]
TASK: [today's specific task]
CONSTRAINTS: [pydantic v2, type hints, test file location, etc.]
OUTPUT: [file locations, interface specification]
DO NOT: [things to avoid]

### Verification:
- [ ] Unit tests pass: `pytest tests/test_[module].py -v`
- [ ] Import works: `python -c "from src.[module] import [Class]"`
- [ ] Integration check: [specific check for this module]
- [ ] Committed: `git commit -m "feat: [description]"`
```

---

*Last updated: 2026-04-30 · Target completion: 2026-05-28*
