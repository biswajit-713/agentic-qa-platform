# ADR-002: Use pytest as the Test Execution Engine

**Date**: 2026-05-01
**Status**: Accepted

---

## Context

The platform needs to execute generated test files and capture structured results (per-test status, duration, error messages, stdout). The execution engine must support:
- Programmatic invocation (no subprocess; called from within Python)
- Per-test result collection (not just pass/fail counts)
- Filtering tests by directory or name pattern
- Works with LLM-generated code that follows standard Python testing conventions

Options considered:

| Option | Programmatic API | Per-test results | LLM output compatibility | Ecosystem |
|---|---|---|---|---|
| pytest | Yes (plugin API) | Yes (custom plugin) | High (de facto standard) | Excellent |
| unittest | Yes (TestLoader) | Partial (TestResult) | Moderate | Good |
| nose2 | Limited | Limited | Moderate | Declining |
| Custom subprocess runner | Yes (subprocess) | Requires parsing | Any | N/A |

---

## Decision

Use **pytest** as the execution engine, invoked via `pytest.main()` with a custom `ResultCollector` plugin. The plugin implements `pytest_runtest_logreport()` to capture per-test outcomes in a structured `PytestRunResult` Pydantic model.

A subprocess runner was explicitly rejected because:
1. It requires parsing stdout (fragile, format-dependent)
2. It adds process-launch overhead per run
3. It cannot share in-process state (e.g., fixtures defined in conftest.py)

---

## Consequences

**Positive:**
- LLM-generated tests use pytest conventions naturally (fixtures, parametrize, assert)
- `pytest.main()` returns a structured exit code; the plugin captures fine-grained results
- Filtering by directory, file, or `-k` pattern works without custom logic
- The platform's own tests use the same runner — no tool duplication

**Negative:**
- pytest's internal plugin API changes between major versions; the `ResultCollector` plugin may need updates
- `pytest.main()` calls `sys.exit()` internally; must be called in a subprocess or guarded

**Mitigations:**
- `PytestRunner` is isolated in `src/runners/` — the interface (`PytestRunResult`) is stable even if the plugin internals change
- The runner is fully unit-tested with mocks; pytest version is pinned in `pyproject.toml`
