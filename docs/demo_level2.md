# Level 2 Demo — Autonomous Agent Loop

This walkthrough shows how the agent responds to a simulated Saleor code change from a clean checkout.

## Setup (one-time)

```bash
git clone https://github.com/yourusername/agentic-qa-platform
cd agentic-qa-platform
uv sync
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
podman compose up -d          # start Saleor + PostgreSQL + Redis
uv run python scripts/health_check.py  # confirm everything is green
```

## Step 1 — Establish a baseline

Run the agent once on a recent commit to seed the state file:

```bash
uv run python -m src.agent run --diff HEAD~3..HEAD
```

Expected output (abbreviated):
```
INFO  Diff: 0 file(s) changed, 0 operation(s) affected
INFO  Risk: overall=LOW, recommended_tests=0
INFO  No HIGH/CRITICAL operations — skipping targeted generation
INFO  Tests: 186 passed, 0 failed, 0 errors in 3.40s
INFO  Quality gate PASSED
```

The agent writes `.agent_state.json` recording all 186 passing tests.

## Step 2 — Simulate a high-risk Saleor change

Create a fake commit that touches a checkout mutation file:

```bash
# Option A: empty commit (tests the diff path without real file changes)
git commit --allow-empty -m "feat: update CheckoutComplete payment logic"

# Option B: touch an actual Saleor mutations file if you have a local clone
# touch saleor/graphql/checkout/mutations/checkout.py
# git add -A && git commit -m "feat: update CheckoutComplete payment logic"
```

## Step 3 — Run the agent

```bash
uv run python -m src.agent run --diff HEAD~1..HEAD
```

The agent executes ten steps:

| Step | What happens |
|---|---|
| 1 | `git diff HEAD~1..HEAD` parsed; `CheckoutComplete` detected as affected operation |
| 2 | LLM scores `CheckoutComplete` as **HIGH** risk (payment flow) |
| 3 | Previous state loaded from `.agent_state.json` |
| 4 | Schema fetched from Saleor GraphQL (or skipped if unreachable) |
| 5 | New test generated for `checkoutComplete` → `generated_tests/api/test_checkout_complete.py` |
| 6 | Full test suite run (186 + 1 new test) |
| 7 | Regressions checked against baseline state |
| 8 | Quality gate evaluated (pass if no regressions and no CRITICAL failures) |
| 9 | State file updated with new results |
| 10 | Report written to `reports/latest.json` + `reports/latest.html` |

Expected output:
```
======================================================================
AGENT RUN REPORT
======================================================================
Timestamp:           2026-05-09T10:35:00+00:00
Diff Range:          HEAD~1..HEAD
Overall Risk:        HIGH
Recommended Tests:   2
New Tests Generated: 1
Generation Failures: 0

TEST EXECUTION
  Passed:  187
  Failed:  0
  Errors:  0
  Total:   187
  Time:    4.50s

Regressions:         0
Quality Gate:        PASS

Report saved to reports/agent_run_report.json
======================================================================
```

## Step 4 — View the HTML report

Open `reports/latest.html` in a browser. You will see:

- **Run header**: timestamp, diff range, quality gate badge (green PASS)
- **Stat grid**: total/passed/failed/errors/duration
- **Risk table**: `CheckoutComplete` at HIGH risk with rationale
- **Test results**: per-test status with layer detection (api/ui/integration)
- **Coverage bar**: before/after delta
- **Agent reasoning**: the LLM's rationale for the risk assessment

## Step 5 — Trigger a quality gate failure

Break a test to see the gate fail:

```bash
# Temporarily corrupt a generated test
echo "assert False, 'deliberate failure'" >> generated_tests/api/test_checkout_complete.py
git commit --allow-empty -m "chore: next change"
uv run python -m src.agent run --diff HEAD~1..HEAD
echo "Exit code: $?"   # expect 1
```

The agent will output:
```
WARNING  Regressions: ['test_checkout_complete_happy_path']
WARNING  Quality gate FAILED: 1 regression(s): [...]
Quality Gate:        FAIL
```

And exit with code 1 — suitable for failing a CI pipeline.

## Cleanup

```bash
git restore generated_tests/  # undo any deliberate test corruption
podman compose down
```
