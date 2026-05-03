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

### Week 1 — Level 1 Autonomy

**What the human does**: Invoke one command (`python -m src.agent.generate_command`)
**What the system does**: Everything else (analyze → decide → generate → run → report)

This is **Level 1 Autonomy**: LLM test generation on demand. Human still triggers it and reviews results. No autonomous decision-making yet.

**Next Steps (Weeks 2-4)**:
- Week 2: Level 2 — autonomous decision-making (analyze diffs, risk score, prioritize)
- Week 3: Add self-healing (auto-patch stale tests with human escalation)
- Week 4: Portfolio polish + extensibility
