"""
src/agent/core.py

Autonomous agent loop: diff → risk score → targeted test generation → run → quality gate → report.

Usage: python -m src.agent --diff HEAD~3..HEAD
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from pydantic import BaseModel, ConfigDict, Field

from src.analyzers.diff_analyzer import DiffAnalyzer, DiffAnalysis
from src.analyzers.risk_scorer import RiskScorer, RiskAssessment
from src.analyzers.schema_analyzer import SchemaAnalyzer, GraphQLOperation
from src.generators.api_test_generator import ApiTestGenerator
from src.reporters.report_generator import generate_reports
from src.runners.pytest_runner import run_tests, PytestRunResult

logger = logging.getLogger(__name__)

_HIGH_RISK_LEVELS = {"CRITICAL", "HIGH"}


class FailedGeneration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_name: str
    error: str


class RunReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timestamp: str
    diff_range: str
    overall_risk: str
    recommended_test_count: int
    new_tests_generated: list[str] = Field(default_factory=list)
    failed_generations: list[FailedGeneration] = Field(default_factory=list)
    run_result: PytestRunResult
    regressions: list[str] = Field(default_factory=list)
    quality_gate_passed: bool
    operation_risks: list[dict] = Field(default_factory=list)


class AgentState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    last_run_timestamp: Optional[str] = None
    last_run_results: dict[str, str] = Field(default_factory=dict)


def get_git_diff(diff_range: str, repo_path: Path = Path(".")) -> str:
    """Run git diff for the given range and return unified diff text."""
    result = subprocess.run(
        ["git", "diff", diff_range],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("git diff returned non-zero exit: %s", result.stderr.strip())
    return result.stdout


def load_state(state_file: Path) -> AgentState:
    """Load agent state from disk, returning empty state if file is missing or corrupt."""
    if not state_file.exists():
        logger.info("No state file at %s — starting fresh", state_file)
        return AgentState()
    try:
        return AgentState.model_validate(json.loads(state_file.read_text()))
    except Exception as e:
        logger.warning("Failed to load state from %s: %s — starting fresh", state_file, e)
        return AgentState()


def save_state(state_file: Path, run_result: PytestRunResult) -> None:
    """Write test results to state file for regression detection in the next run."""
    state = AgentState(
        last_run_timestamp=datetime.now(timezone.utc).isoformat(),
        last_run_results={r.test_name: r.status for r in run_result.test_results},
    )
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(state.model_dump_json(indent=2))
    logger.info("State saved to %s (%d results)", state_file, len(state.last_run_results))


def fetch_schema_ops(schema_analyzer: SchemaAnalyzer) -> dict[str, GraphQLOperation]:
    """Fetch all schema operations as a lowercase-name → GraphQLOperation map."""
    ops: dict[str, GraphQLOperation] = {}
    try:
        for op in schema_analyzer.get_all_queries():
            ops[op.name.lower()] = op
        for op in schema_analyzer.get_all_mutations():
            ops[op.name.lower()] = op
        logger.info("Fetched %d schema operations", len(ops))
    except Exception as e:
        logger.warning("Could not fetch schema (Saleor may be unreachable): %s", e)
    return ops


def generate_targeted_tests(
    risk: RiskAssessment,
    schema_ops: dict[str, GraphQLOperation],
    generator: ApiTestGenerator,
) -> tuple[list[str], list[FailedGeneration]]:
    """Generate tests for HIGH and CRITICAL operations in the risk assessment.

    Returns (generated_test_names, failed_generations).
    """
    generated: list[str] = []
    failures: list[FailedGeneration] = []

    high_risk_ops = [op for op in risk.operation_risks if op.risk_level in _HIGH_RISK_LEVELS]

    if not high_risk_ops:
        logger.info("No HIGH/CRITICAL operations — skipping targeted generation")
        return generated, failures

    logger.info("Generating tests for %d HIGH/CRITICAL operation(s)", len(high_risk_ops))

    for i, op_risk in enumerate(high_risk_ops, 1):
        name = op_risk.operation_name
        schema_op = schema_ops.get(name.lower())

        if not schema_op:
            logger.warning("[%d/%d] %s not found in schema — skipping", i, len(high_risk_ops), name)
            failures.append(FailedGeneration(operation_name=name, error="Operation not found in schema"))
            continue

        try:
            logger.info(
                "[%d/%d] Generating test for %s (risk=%s)", i, len(high_risk_ops), name, op_risk.risk_level
            )
            test_case = generator.generate(schema_op)
            test_file = generator.write_test(test_case)
            generated.append(test_case.test_name)
            logger.info("✓ %s → %s", name, test_file)
        except Exception as e:
            logger.warning("✗ Skipping %s: %s", name, e)
            failures.append(FailedGeneration(operation_name=name, error=str(e)))

    return generated, failures


def detect_regressions(run_result: PytestRunResult, previous_state: AgentState) -> list[str]:
    """Return test names that previously passed but now fail or error."""
    return [
        r.test_name
        for r in run_result.test_results
        if r.status in ("failed", "error")
        and previous_state.last_run_results.get(r.test_name) == "passed"
    ]


def check_quality_gate(
    risk: RiskAssessment,
    run_result: PytestRunResult,
    regressions: list[str],
) -> bool:
    """Return True if the quality gate passes: no regressions and no CRITICAL-op test failures."""
    if regressions:
        logger.warning("Quality gate FAILED: %d regression(s): %s", len(regressions), regressions)
        return False

    critical_op_names = {op.operation_name.lower() for op in risk.operation_risks if op.risk_level == "CRITICAL"}
    if critical_op_names:
        critical_failures = [
            r.test_name
            for r in run_result.test_results
            if r.status in ("failed", "error")
            and any(op in r.test_name.lower() for op in critical_op_names)
        ]
        if critical_failures:
            logger.warning(
                "Quality gate FAILED: %d CRITICAL operation test(s) failing: %s",
                len(critical_failures),
                critical_failures,
            )
            return False

    logger.info("Quality gate PASSED")
    return True


def score_risk_with_fallback(diff_analysis: DiffAnalysis) -> RiskAssessment:
    """Score diff risk, returning a MEDIUM fallback if the LLM call fails (e.g. rate limit)."""
    try:
        return RiskScorer().score(diff_analysis)
    except Exception as e:
        logger.warning("Risk scoring failed (%s: %s); using MEDIUM fallback", type(e).__name__, e)
        return RiskAssessment(
            overall_risk="MEDIUM",
            rationale=f"Risk scoring unavailable ({type(e).__name__}): {e}",
            recommended_test_count=0,
            operation_risks=[],
        )


def run_loop(
    diff_range: str,
    test_dir: str = "generated_tests/api",
    state_file: str = ".agent_state.json",
    report_path: str = "reports/agent_run_report.json",
) -> RunReport:
    """Execute the full agent loop for a given git diff range."""
    logger.info("=== Agent loop start | diff=%s ===", diff_range)

    # Step 1: Diff → affected operations
    diff_text = get_git_diff(diff_range)
    if not diff_text.strip():
        logger.info("Empty diff — no source changes detected")
    diff_analysis = DiffAnalyzer.analyze_diff_text(diff_text)
    logger.info(
        "Diff: %d file(s) changed, %d operation(s) affected",
        len(diff_analysis.changed_files),
        len(diff_analysis.affected_operations),
    )

    # Step 2: Risk scoring (with fallback for LLM unavailability / rate limits)
    risk = score_risk_with_fallback(diff_analysis)
    logger.info("Risk: overall=%s, recommended_tests=%d", risk.overall_risk, risk.recommended_test_count)

    # Step 3: Load previous state for regression tracking
    state = load_state(Path(state_file))

    # Step 4: Fetch schema (best-effort; generation skipped gracefully if Saleor is down)
    schema_ops = fetch_schema_ops(SchemaAnalyzer())

    # Step 5: Generate tests for HIGH/CRITICAL operations
    generator = ApiTestGenerator()
    generated, failures = generate_targeted_tests(risk, schema_ops, generator)
    logger.info("Generation: %d new, %d failed", len(generated), len(failures))

    # Step 6: Run tests
    test_path = Path(test_dir)
    if test_path.exists():
        run_result = run_tests(test_dir=test_dir)
        logger.info(
            "Tests: %d passed, %d failed, %d errors in %.2fs",
            run_result.passed, run_result.failed, run_result.errors, run_result.duration_seconds,
        )
    else:
        logger.warning("Test directory %s not found — skipping test run", test_dir)
        run_result = PytestRunResult(total=0, passed=0, failed=0, errors=0, duration_seconds=0.0)

    # Step 7: Detect regressions
    regressions = detect_regressions(run_result, state)
    if regressions:
        logger.warning("Regressions: %s", regressions)

    # Step 8: Quality gate
    gate_passed = check_quality_gate(risk, run_result, regressions)

    # Step 9: Persist state for next run
    save_state(Path(state_file), run_result)

    # Step 10: Write report
    report = RunReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        diff_range=diff_range,
        overall_risk=risk.overall_risk,
        recommended_test_count=risk.recommended_test_count,
        new_tests_generated=generated,
        failed_generations=failures,
        run_result=run_result,
        regressions=regressions,
        quality_gate_passed=gate_passed,
        operation_risks=[r.model_dump() for r in risk.operation_risks],
    )

    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report.model_dump_json(indent=2))
    logger.info("Report saved to %s", report_path)

    generate_reports(
        report,
        output_dir=Path(report_path).parent,
        rationale=risk.rationale,
    )

    logger.info("=== Agent loop complete | gate=%s ===", "PASS" if gate_passed else "FAIL")
    return report


# ─── CLI ─────────────────────────────────────────────────────────────────────

app = typer.Typer(help="Autonomous QA agent: diff → risk → generate → run → report")


@app.callback()
def _main() -> None:
    pass


@app.command()
def run(
    diff: str = typer.Option(..., "--diff", help="Git diff range, e.g. HEAD~3..HEAD"),
    test_dir: str = typer.Option("generated_tests/api", "--test-dir", help="Directory for generated tests"),
    state_file: str = typer.Option(".agent_state.json", "--state", help="Path to agent state JSON"),
    report_path: str = typer.Option(
        "reports/agent_run_report.json", "--report", help="Path to write JSON report"
    ),
) -> None:
    """Run the full autonomous agent loop for a git diff range."""
    report = run_loop(
        diff_range=diff,
        test_dir=test_dir,
        state_file=state_file,
        report_path=report_path,
    )

    print()
    print("=" * 70)
    print("AGENT RUN REPORT")
    print("=" * 70)
    print(f"Timestamp:           {report.timestamp}")
    print(f"Diff Range:          {report.diff_range}")
    print(f"Overall Risk:        {report.overall_risk}")
    print(f"Recommended Tests:   {report.recommended_test_count}")
    print(f"New Tests Generated: {len(report.new_tests_generated)}")
    print(f"Generation Failures: {len(report.failed_generations)}")
    print()
    print("TEST EXECUTION")
    print(f"  Passed:  {report.run_result.passed}")
    print(f"  Failed:  {report.run_result.failed}")
    print(f"  Errors:  {report.run_result.errors}")
    print(f"  Total:   {report.run_result.total}")
    print(f"  Time:    {report.run_result.duration_seconds:.2f}s")
    print()
    print(f"Regressions:         {len(report.regressions)}")
    gate_label = "PASS" if report.quality_gate_passed else "FAIL"
    print(f"Quality Gate:        {gate_label}")
    print()
    print(f"Report saved to {report_path}")
    print("=" * 70)

    if not report.quality_gate_passed:
        raise typer.Exit(1)


@app.command()
def review(
    queue_file: str = typer.Option("needs_review.json", "--queue", help="Path to escalation queue"),
    show_all: bool = typer.Option(False, "--all", help="Show resolved entries too"),
) -> None:
    """Show pending test escalations that need human attention."""
    from src.healers.escalation_manager import EscalationManager

    manager = EscalationManager(queue_file=Path(queue_file))
    entries = manager.list_all() if show_all else manager.list_pending()

    if not entries:
        label = "escalations" if show_all else "pending escalations"
        print(f"No {label} found in {queue_file}")
        return

    label = "escalations (all)" if show_all else "pending escalations"
    print()
    print("=" * 70)
    print(f"ESCALATION QUEUE — {label.upper()}")
    print("=" * 70)

    for i, entry in enumerate(entries, 1):
        status_marker = "[RESOLVED]" if entry.status == "resolved" else "[PENDING] "
        print(f"\n{i}. {status_marker} {entry.test_name}")
        print(f"   Category:   {entry.category}  (confidence={entry.confidence:.0%})")
        print(f"   Escalated:  {entry.escalated_at}")
        if entry.original_error:
            print(f"   Error:      {entry.original_error}")
        if entry.reasoning:
            print(f"   Reasoning:  {entry.reasoning}")
        if entry.suggested_fix_hint:
            print(f"   Hint:       {entry.suggested_fix_hint}")
        if entry.status == "resolved":
            print(f"   Resolution: {entry.resolution} at {entry.resolved_at}")
            if entry.resolution_note:
                print(f"   Note:       {entry.resolution_note}")

    print()
    print(f"Total: {len(entries)}")
    if not show_all:
        print("Tip: use `resolve --test <name> --action accept|reject` to close an entry.")
    print("=" * 70)


@app.command()
def resolve(
    test: str = typer.Option(..., "--test", help="Pytest node ID of the test to resolve"),
    action: str = typer.Option(..., "--action", help="Resolution action: accept or reject"),
    note: str = typer.Option("", "--note", help="Optional free-text note"),
    queue_file: str = typer.Option("needs_review.json", "--queue", help="Path to escalation queue"),
) -> None:
    """Resolve a pending escalation by accepting or rejecting it."""
    from src.healers.escalation_manager import EscalationManager, ResolutionAction

    if action not in ("accept", "reject"):
        print(f"Error: --action must be 'accept' or 'reject', got {action!r}")
        raise typer.Exit(1)

    manager = EscalationManager(queue_file=Path(queue_file))
    try:
        entry = manager.resolve(test, action=action, note=note)  # type: ignore[arg-type]
    except KeyError as e:
        print(f"Error: {e}")
        raise typer.Exit(1) from e

    print()
    print("=" * 70)
    print("ESCALATION RESOLVED")
    print("=" * 70)
    print(f"Test:       {entry.test_name}")
    print(f"Action:     {entry.resolution}")
    print(f"Resolved:   {entry.resolved_at}")
    if entry.resolution_note:
        print(f"Note:       {entry.resolution_note}")
    print("=" * 70)


if __name__ == "__main__":
    app()
