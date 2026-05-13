# Agentic QA Platform — Architecture

## Week 1: LLM Test Generation

### Overview

Week 1 establishes the foundation: a pipeline that reads a GraphQL schema, identifies test gaps, generates realistic pytest test cases using an LLM, executes them, and reports coverage.

```
Saleor GraphQL Schema
        │
        ▼
   SchemaAnalyzer ──introspection──→ all queries & mutations
        │
        ├──────────────┬────────────────┤
        ▼              ▼                ▼
   ExistingTests  CoverageAnalyzer  Priority Scoring
   (files)            │
                      ├─ total_operations
                      ├─ covered_operations
                      ├─ coverage_percentage
                      └─ priority_queue → top N uncovered
                            │
                            ▼
                    ApiTestGenerator ──LLM──→ TestCase
                            │         (OpenRouter)
                            ▼
                        write_test()
                            │
                            ▼
                    generated_tests/api/*.py
                            │
                            ▼
                      PytestRunner ──run tests──→ PytestRunResult
                            │
                            ├─ total, passed, failed, errors
                            ├─ duration_seconds
                            └─ per-test details
                                  │
                                  ▼
                            GenerationReport (JSON)
```

### Module Responsibilities

| Module | File | Responsibility | Key Output |
|--------|------|-----------------|------------|
| **SchemaAnalyzer** | `src/analyzers/schema_analyzer.py` | Fetch & parse GraphQL schema via introspection | `list[GraphQLOperation]` |
| **CoverageAnalyzer** | `src/analyzers/coverage_analyzer.py` | Compare schema ops vs test files; score by priority | `CoverageReport` with priority queue |
| **ApiTestGenerator** | `src/generators/api_test_generator.py` | Use LLM to generate pytest code from operations | `TestCase` (test_code + metadata) |
| **PytestRunner** | `src/runners/pytest_runner.py` | Execute tests via pytest Python API | `PytestRunResult` (structured results) |
| **GenerateCommand** | `src/agent/generate_command.py` | Orchestrate: analyze → generate → run → report | `GenerationReport` (JSON) |

### Data Models

**`GraphQLOperation`** — represents a query or mutation
```python
name: str                        # e.g., "productCreate"
type_: str                       # "query" or "mutation"
return_type: str                 # return type name
args: list[GraphQLInputValue]    # parameters
description: Optional[str]       # from schema
```

**`CoverageReport`** — analysis of gap and priorities
```python
total_operations: int            # all ops in schema
covered_operations: int          # with existing tests
coverage_percentage: float       # covered / total
uncovered: list[GraphQLOperation]
covered: list[str]               # names
priority_queue: list[GraphQLOperation]  # sorted by:
                                        # +20 mutations
                                        # +15 CRUD ops
                                        # +25 checkout/payment/order
                                        # -10 similar existing test
```

**`TestCase`** — generated test metadata
```python
test_name: str                   # snake_case
description: str
graphql_query: str               # full GQL query/mutation
variables: dict
assertions: list[str]
test_code: str                   # executable pytest function
```

**`PytestRunResult`** — execution summary
```python
total: int
passed: int
failed: int
errors: int
duration_seconds: float
test_results: list[SingleTestResult]  # per-test detail
```

**`GenerationReport`** — full run summary
```python
timestamp: str
count_requested: int
generated: list[str]             # test names written
failed_generations: list[FailedGeneration]
coverage_before: float
coverage_after: float
total_operations: int
run_result: PytestRunResult
```

### Usage: `GenerateCommand`

CLI entry point: `uv run python -m src.agent.generate_command`

**Options**:
- `--count N` — generate up to N tests (default: 10)
- `--test-dir DIR` — where to write tests (default: generated_tests/api)
- `--report PATH` — JSON report destination (default: reports/generation_report.json)

**Example**:
```bash
uv run python -m src.agent.generate_command --count 50 --report reports/week1.json
```

**Orchestration Steps** (in `run_generation()`):

1. **Analyze coverage** — `CoverageAnalyzer(test_dir).analyze()`
   - Scans `test_dir` for existing `.py` files
   - Compares against `SchemaAnalyzer.get_all_*()` results
   - Returns priority queue of uncovered operations

2. **Take top N** — `coverage_report.priority_queue[:count]`
   - Highest-priority operations first

3. **Generate** — for each operation:
   - `generator.generate(op)` — LLM produces TestCase
   - `generator.write_test(test_case)` — write to disk
   - On failure: skip, log error, continue

4. **Run tests** — `run_tests(test_dir)`
   - Pytest executes all .py files in test_dir
   - Captures structured results (duration, status, error messages)

5. **Report** — Write JSON to `report_path`
   - Coverage before/after
   - List of generated test names
   - List of failures with reasons
   - Full pytest result details

### Error Handling

**Generation Failures** (skip and continue):
- LLM timeout or refusal → skip operation, log error
- Invalid GraphQL syntax generated → skip
- Type introspection fails → skip

**Other Failures** (escalate):
- Schema fetch fails → halt, raise
- Test execution fails for ALL tests → halt, raise
- Report write fails → halt, raise

### Cost & Performance

- **Cost**: Free (uses OpenRouter gpt-oss-120b:free model)
- **Latency per test**: ~5-10s (LLM generation + execution)
- **For 50 tests**: ~5-10 minutes end-to-end
- **Caching**: Schema fetched once, reused; test files persist

### Testing Strategy

All modules unit-tested with mocks:
- No real Saleor required (mocked httpx responses)
- No real LLM calls (mocked OpenAI client)
- No real test execution (mocked pytest)
- Temporary directories for file I/O

Test files: `tests/test_*.py`
```
test_schema_analyzer.py      ✅ 13 tests
test_api_test_generator.py   ✅ 5 tests
test_pytest_runner.py        ✅ 9 tests
test_coverage_analyzer.py    ✅ 8 tests
test_generate_command.py     ✅ 5 tests
─────────────────────────────────────
Total: 40 tests, all passing
```

---

## Week 2: Autonomous Agent Loop

### Overview

Week 2 adds autonomous decision-making. The agent reacts to a git diff, scores risk with an LLM, generates tests only for HIGH/CRITICAL operations, runs them, detects regressions against previous runs, and enforces a quality gate.

```
git diff <range>
      │
      ▼
 DiffAnalyzer.analyze_diff_text()  ← @staticmethod, no side effects
      │
      ▼  DiffAnalysis (changed_files, affected_operations)
      │
      ▼
 RiskScorer.score()  ──LLM──→ RiskAssessment
      │                        (overall_risk, operation_risks[])
      ▼
 [HIGH/CRITICAL ops only]
      │
      ▼
 fetch_schema_ops()  ──introspection──→ {name: GraphQLOperation}
      │
      ▼
 generate_targeted_tests()
      │  ApiTestGenerator.generate() + write_test() per op
      ▼
 generated_tests/api/*.py
      │
      ▼
 run_tests(test_dir)  ──→  PytestRunResult
      │
      ├── detect_regressions(result, AgentState)
      │         ← loads .agent_state.json (previous run results)
      │
      ├── check_quality_gate(risk, result, regressions)
      │         FAIL if: regressions exist OR CRITICAL-op test fails
      │
      ├── save_state(.agent_state.json)
      │
      └── RunReport (JSON)
```

### Module Responsibilities

| Module | File | Responsibility | Key Output |
|--------|------|-----------------|------------|
| **DiffAnalyzer** | `src/analyzers/diff_analyzer.py` | Parse unified diff → GraphQL operation names | `DiffAnalysis` |
| **RiskScorer** | `src/analyzers/risk_scorer.py` | LLM-powered risk level per operation | `RiskAssessment` |
| **AgentCore** | `src/agent/core.py` | Orchestrate full loop + quality gate | `RunReport` |

### State Persistence

`AgentState` is written to `.agent_state.json` after every run:

```json
{
  "last_run_timestamp": "2026-05-07T10:00:00+00:00",
  "last_run_results": {
    "test_checkout_complete": "passed",
    "test_product_create": "failed"
  }
}
```

Used by `detect_regressions()` on the next run to identify tests that previously passed but now fail.

### Quality Gate Logic

```
PASS if:
  - no regressions (tests that were passing before and now fail)
  - no CRITICAL-operation tests currently failing

FAIL otherwise → CLI exits with code 1 (CI-safe)
```

### Usage

```bash
uv run python -m src.agent run --diff HEAD~3..HEAD --test-dir generated_tests/api --state .agent_state.json --report reports/agent_run_report.json
```

### Test Coverage

```
test_agent_core.py    ✅ 24 tests (get_git_diff, load/save_state,
                                   detect_regressions, check_quality_gate,
                                   generate_targeted_tests, run_loop)
─────────────────────────────────────
Total Week 2: 103 tests, all passing
```

### Week 2 — Level 2 Autonomy

**What the human does**: Push a commit (or provide a diff range)
**What the system does**: Analyze change → assess risk → generate targeted tests → run → report

This is **Level 2 Autonomy**: the agent makes decisions (what to test, how much risk, whether to pass the gate) without human input.

---

### Week 1 — Level 1 Autonomy

**What the human does**: Invoke one command (`python -m src.agent.generate_command`)
**What the system does**: Everything else (analyze → decide → generate → run → report)

This is **Level 1 Autonomy**: LLM test generation on demand. Human still triggers it and reviews results. No autonomous decision-making yet.

---

## Week 3: Self-Healing + Audit Trail (Level 3 on API layer)

### Overview

Week 3 adds autonomous failure triage and repair. When a test fails the agent classifies the root cause, decides whether to auto-heal or escalate to a human, applies the patch only if it passes verification, and logs every action for governance.

```
 failing test (test_name, test_code, error_message, stack_trace, recent_diff)
        │
        ▼
 FailureClassifier.classify()  ──LLM──→ FailureClassification
        │                                 category: APP_BUG | TEST_STALE |
        │                                           FLAKY | ENVIRONMENT | UNKNOWN
        │                                 confidence: 0.0–1.0
        │                                 should_escalate: bool
        │
        ├─── should_escalate == True ──→ EscalationManager.push()
        │                                 needs_review.json (pending queue)
        │
        └─── should_auto_heal() == True (TEST_STALE | FLAKY, confidence ≥ 0.7)
                    │
                    ▼
             SelfHealer.heal()
                    │
                    ├── 1. LLM generates full patched test code
                    ├── 2. Write to temp file
                    ├── 3. PytestRunner runs temp file
                    │
                    ├── passes ──→ overwrite original file
                    │              HealEvent(outcome=HEALED) → heals.jsonl
                    │
                    └── still fails ──→ HealEvent(outcome=FAILED) → heals.jsonl
                                        EscalationManager.push() (fallback)
```

### Module Responsibilities

| Module | File | Responsibility | Key Output |
|--------|------|----------------|------------|
| **FailureClassifier** | `src/healers/failure_classifier.py` | LLM root-cause classification of failed tests | `FailureClassification` |
| **SelfHealer** | `src/healers/self_healer.py` | Generate + verify patch for TEST_STALE failures | `HealEvent` → `heals.jsonl` |
| **EscalationManager** | `src/healers/escalation_manager.py` | Queue failures needing human review | `EscalationEntry` → `needs_review.json` |
| **UITestGenerator** | `src/generators/ui_test_generator.py` | Playwright async tests for storefront flows | `UITestCase` → `generated_tests/ui/` |
| **IntegrationTestGenerator** | `src/generators/integration_test_generator.py` | Cross-layer API + UI tests | `IntegrationTestCase` → `generated_tests/integration/` |
| **ReportGenerator** | `src/reporters/report_generator.py` | JSON + HTML quality reports from RunReport | `reports/latest.json`, `reports/latest.html` |

### Data Models

**`FailedTest`** — input to the classifier
```python
test_name: str                  # pytest node ID, e.g. "tests/test_foo.py::test_bar"
test_code: str                  # full source of the test function
error_message: str              # one-line error or assertion message
stack_trace: str                # full traceback
recent_diff: str                # git diff that preceded the failure
last_passing_run: Optional[datetime]
```

**`FailureClassification`** — output of the classifier
```python
category: Literal["APP_BUG", "TEST_STALE", "ENVIRONMENT", "FLAKY", "UNKNOWN"]
confidence: float               # 0.0–1.0
reasoning: str                  # step-by-step explanation
suggested_fix_hint: str         # concrete hint for fixer
should_escalate: bool           # True when category in {APP_BUG, UNKNOWN}
                                # OR confidence < 0.7
```

**`HealEvent`** — audit record written to heals.jsonl
```python
timestamp: str
test_name: str
original_error: str
fix_applied: str                # full patched test code that was attempted
confidence: float
outcome: Literal["HEALED", "FAILED"]
failure_reason: Optional[str]   # set only when outcome=FAILED
```

**`EscalationEntry`** — one item in needs_review.json
```python
test_name: str
category: str
confidence: float
reasoning: str
suggested_fix_hint: str
original_error: str
escalated_at: str               # ISO-8601 UTC
status: Literal["pending", "resolved"]
resolved_at: Optional[str]
resolution: Optional[Literal["accept", "reject"]]
resolution_note: str
```

### Escalation Decision Logic

```
should_auto_heal(classification) → bool

  True  when:  category in {TEST_STALE, FLAKY}
               AND confidence ≥ 0.7
               AND not a UI test (no DOM signal for verification)

  False when:  category in {APP_BUG, UNKNOWN}  ← always escalate
               OR confidence < 0.7             ← low confidence → escalate
               OR it's a UI test               ← SelfHealer rejects these
```

### CLI Commands (Week 3)

```bash
# List all pending escalations
uv run python -m src.agent review

# List all (including resolved)
uv run python -m src.agent review --all

# Resolve a pending escalation
uv run python -m src.agent resolve \
  --test "generated_tests/api/test_checkout.py::test_checkout_create" \
  --action accept \
  --note "Schema rename was intentional, patch is correct"

# Dry-run self-healing (show patch without writing)
# (called programmatically via SelfHealer.heal(dry_run=True))
```

### Governance Model

Two audit files are always written:

| File | Written by | Content |
|---|---|---|
| `heals.jsonl` | `SelfHealer` | One JSON line per healing attempt (HEALED or FAILED) |
| `needs_review.json` | `EscalationManager` | Array of EscalationEntry objects; status updated in-place on resolve |

These files are the governance layer: every autonomous change to a test file has a corresponding `heals.jsonl` entry, and every case where the agent chose _not_ to auto-heal has a corresponding `needs_review.json` entry.

### Test Coverage (Week 3)

```
test_failure_classifier.py     ✅ 26 tests  (LLM mock, classification logic, escalation rules)
test_self_healer.py            ✅ 40 tests  (patch gen, temp-file verify, heals.jsonl append)
test_escalation_manager.py     ✅ 24 tests  (push idempotency, list/resolve, disk persistence)
──────────────────────────────────────────
Week 3 additions: 90 tests
Running total: 282 tests, all passing
```

### Week 3 — Level 3 Autonomy (API Layer)

**What the human does**: Review the `needs_review.json` queue via `python -m src.agent review`; accept or reject each escalation
**What the system does**: Classify failures → auto-patch TEST_STALE → verify patch → commit or escalate → log every decision

This is **Level 3 Autonomy** on the API layer: the system closes the fail→fix loop without human input when confidence is high. Humans are only brought in for genuine application bugs, unknown failures, and low-confidence classifications.
