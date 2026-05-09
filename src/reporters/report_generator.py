"""
src/reporters/report_generator.py

Generates professional JSON and HTML quality reports from a RunReport.

JSON schema fields:
  timestamp          ISO-8601 UTC timestamp of the agent run
  diff_range         Git range analyzed (e.g. HEAD~3..HEAD)
  overall_risk       Aggregate risk level: CRITICAL | HIGH | MEDIUM | LOW
  recommended_tests  Number of tests the risk scorer suggested generating
  new_tests          List of test names generated this run
  failed_generations List of {operation_name, error} for generation failures
  run_result         {total, passed, failed, errors, duration_seconds, test_results[]}
  regressions        Test names that regressed (previously passed, now failing)
  quality_gate       Boolean — True if gate passed
  operation_risks    List of {operation_name, risk_level, reason, suggested_test_focus[]}
  coverage_before    API coverage % before this run (if available)
  coverage_after     API coverage % after this run (if available)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader

logger = logging.getLogger(__name__)

_RISK_COLOR = {
    "CRITICAL": "#c0392b",
    "HIGH": "#e67e22",
    "MEDIUM": "#f39c12",
    "LOW": "#27ae60",
}

_STATUS_COLOR = {
    "passed": "#27ae60",
    "failed": "#c0392b",
    "error": "#e67e22",
}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QA Agent Report — {{ timestamp_short }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      padding: 32px;
      line-height: 1.5;
    }
    h1 { font-size: 1.75rem; font-weight: 700; color: #f8fafc; }
    h2 { font-size: 1.1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase;
         letter-spacing: 0.08em; margin-bottom: 14px; }
    .header {
      display: flex; flex-wrap: wrap; gap: 12px;
      align-items: flex-start; margin-bottom: 32px;
    }
    .header-left { flex: 1; min-width: 280px; }
    .header-left .subtitle {
      color: #64748b; font-size: 0.875rem; margin-top: 4px;
    }
    .badge {
      display: inline-block; padding: 4px 14px; border-radius: 9999px;
      font-size: 0.8rem; font-weight: 700; letter-spacing: 0.05em;
      color: #fff;
    }
    .gate-badge {
      font-size: 1rem; padding: 8px 22px; border-radius: 8px; font-weight: 700;
      color: #fff;
      background: {% if quality_gate %}#27ae60{% else %}#c0392b{% endif %};
    }
    .section {
      background: #1e2433;
      border: 1px solid #2d3748;
      border-radius: 10px;
      padding: 24px;
      margin-bottom: 24px;
    }
    .stat-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 16px;
    }
    .stat {
      background: #0f1117;
      border: 1px solid #2d3748;
      border-radius: 8px;
      padding: 16px;
      text-align: center;
    }
    .stat .value {
      font-size: 2rem; font-weight: 800; line-height: 1;
      margin-bottom: 6px;
    }
    .stat .label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; }
    .stat.passed .value { color: #27ae60; }
    .stat.failed .value { color: #c0392b; }
    .stat.errors .value { color: #e67e22; }
    .stat.total .value { color: #60a5fa; }
    .stat.duration .value { color: #a78bfa; font-size: 1.5rem; }
    table {
      width: 100%; border-collapse: collapse; font-size: 0.875rem;
    }
    th {
      text-align: left; padding: 10px 12px;
      color: #64748b; font-weight: 600; font-size: 0.75rem;
      text-transform: uppercase; letter-spacing: 0.06em;
      border-bottom: 1px solid #2d3748;
    }
    td {
      padding: 10px 12px; border-bottom: 1px solid #1a2133;
      vertical-align: top;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #151c2a; }
    .mono { font-family: "SF Mono", "Fira Code", monospace; font-size: 0.8rem; }
    .tag {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.05em; color: #fff;
    }
    .coverage-bar-wrap {
      background: #0f1117; border-radius: 6px; height: 16px;
      overflow: hidden; margin-top: 8px; position: relative;
    }
    .coverage-bar {
      height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6);
      border-radius: 6px; transition: width 0.3s;
    }
    .coverage-row { display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
    .coverage-stat { text-align: center; }
    .coverage-stat .value { font-size: 1.6rem; font-weight: 800; color: #60a5fa; }
    .coverage-stat .delta-pos { color: #27ae60; font-size: 0.875rem; }
    .coverage-stat .delta-neg { color: #c0392b; font-size: 0.875rem; }
    .coverage-stat .label { font-size: 0.75rem; color: #64748b; }
    .reasoning-block {
      background: #0f1117; border-left: 3px solid #6366f1;
      border-radius: 4px; padding: 14px 18px; font-size: 0.875rem;
      color: #cbd5e1; line-height: 1.6; white-space: pre-wrap;
    }
    .op-focus { color: #7dd3fc; font-size: 0.78rem; }
    .chip-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .chip {
      background: #1e2433; border: 1px solid #3b4a63; border-radius: 4px;
      padding: 2px 8px; font-size: 0.72rem; color: #94a3b8;
    }
    .empty { color: #475569; font-style: italic; font-size: 0.875rem; }
    .footer {
      text-align: center; color: #334155; font-size: 0.75rem; margin-top: 32px;
    }
  </style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>QA Agent Report</h1>
    <div class="subtitle">
      {{ timestamp }} &nbsp;|&nbsp; git range: <span class="mono">{{ diff_range }}</span>
    </div>
  </div>
  <div>
    <span class="gate-badge">
      {% if quality_gate %}✓ QUALITY GATE PASSED{% else %}✗ QUALITY GATE FAILED{% endif %}
    </span>
  </div>
</div>

<!-- ── Run Summary ─────────────────────────────────────────────── -->
<div class="section">
  <h2>Run Summary</h2>
  <div class="stat-grid">
    <div class="stat total">
      <div class="value">{{ run_result.total }}</div>
      <div class="label">Total Tests</div>
    </div>
    <div class="stat passed">
      <div class="value">{{ run_result.passed }}</div>
      <div class="label">Passed</div>
    </div>
    <div class="stat failed">
      <div class="value">{{ run_result.failed }}</div>
      <div class="label">Failed</div>
    </div>
    <div class="stat errors">
      <div class="value">{{ run_result.errors }}</div>
      <div class="label">Errors</div>
    </div>
    <div class="stat duration">
      <div class="value">{{ "%.2f"|format(run_result.duration_seconds) }}s</div>
      <div class="label">Duration</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#f472b6;">{{ new_tests | length }}</div>
      <div class="label">New Tests</div>
    </div>
    <div class="stat">
      <div class="value" style="color:{% if regressions %}#c0392b{% else %}#27ae60{% endif %};">
        {{ regressions | length }}
      </div>
      <div class="label">Regressions</div>
    </div>
  </div>
</div>

<!-- ── Risk Assessment ─────────────────────────────────────────── -->
<div class="section">
  <h2>Risk Assessment</h2>
  <p style="margin-bottom:16px;">
    Overall risk:
    <span class="badge" style="background:{{ risk_color }};">{{ overall_risk }}</span>
    &nbsp; Recommended test count: <strong>{{ recommended_tests }}</strong>
  </p>
  {% if operation_risks %}
  <table>
    <thead>
      <tr>
        <th>Operation</th>
        <th>Risk Level</th>
        <th>Reason</th>
        <th>Test Focus</th>
      </tr>
    </thead>
    <tbody>
      {% for op in operation_risks %}
      <tr>
        <td class="mono">{{ op.operation_name }}</td>
        <td>
          <span class="tag" style="background:{{ op_risk_color(op.risk_level) }};">
            {{ op.risk_level }}
          </span>
        </td>
        <td style="color:#94a3b8; font-size:0.83rem;">{{ op.reason }}</td>
        <td>
          <div class="chip-list">
            {% for f in op.suggested_test_focus %}
            <span class="chip">{{ f }}</span>
            {% endfor %}
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">No operations analyzed.</p>
  {% endif %}
</div>

<!-- ── Test Results ────────────────────────────────────────────── -->
<div class="section">
  <h2>Test Results</h2>
  {% if run_result.test_results %}
  <table>
    <thead>
      <tr>
        <th>Test Name</th>
        <th>Layer</th>
        <th>Status</th>
        <th>Duration</th>
      </tr>
    </thead>
    <tbody>
      {% for t in run_result.test_results %}
      <tr>
        <td class="mono" style="word-break:break-all; max-width:460px;">{{ t.test_name }}</td>
        <td>
          <span class="tag" style="background:#1e3a5f; color:#7dd3fc;">{{ t | detect_layer }}</span>
        </td>
        <td>
          <span class="tag" style="background:{{ status_color(t.status) }};">{{ t.status }}</span>
        </td>
        <td class="mono" style="color:#64748b;">{{ "%.3f"|format(t.duration) }}s</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">No tests were executed this run.</p>
  {% endif %}
</div>

<!-- ── Coverage ────────────────────────────────────────────────── -->
<div class="section">
  <h2>API Coverage</h2>
  {% if coverage_after is not none %}
  <div class="coverage-row">
    <div class="coverage-stat">
      <div class="value">{{ "%.1f"|format(coverage_after) }}%</div>
      <div class="label">Current Coverage</div>
      {% if coverage_before is not none %}
        {% set delta = coverage_after - coverage_before %}
        {% if delta > 0 %}
        <div class="delta-pos">▲ +{{ "%.1f"|format(delta) }}% from last run</div>
        {% elif delta < 0 %}
        <div class="delta-neg">▼ {{ "%.1f"|format(delta) }}% from last run</div>
        {% else %}
        <div style="color:#64748b; font-size:0.875rem;">No change from last run</div>
        {% endif %}
      {% endif %}
    </div>
    <div style="flex:1; min-width:200px;">
      <div class="coverage-bar-wrap">
        <div class="coverage-bar" style="width:{{ coverage_after | min(100) }}%;"></div>
      </div>
    </div>
  </div>
  {% else %}
  <p class="empty">Coverage data not available for this run.</p>
  {% endif %}
</div>

<!-- ── Agent Reasoning ─────────────────────────────────────────── -->
<div class="section">
  <h2>Agent Reasoning</h2>
  {% if rationale %}
  <div class="reasoning-block">{{ rationale }}</div>
  {% else %}
  <p class="empty">No reasoning recorded for this run.</p>
  {% endif %}
  {% if new_tests %}
  <p style="margin-top:16px; font-size:0.875rem; color:#64748b;">
    Tests generated this run:
  </p>
  <div class="chip-list" style="margin-top:8px;">
    {% for name in new_tests %}
    <span class="chip mono">{{ name }}</span>
    {% endfor %}
  </div>
  {% endif %}
  {% if regressions %}
  <p style="margin-top:16px; font-size:0.875rem; color:#c0392b; font-weight:600;">
    Regressions detected:
  </p>
  <div class="chip-list" style="margin-top:8px;">
    {% for r in regressions %}
    <span class="chip mono" style="border-color:#c0392b; color:#f87171;">{{ r }}</span>
    {% endfor %}
  </div>
  {% endif %}
</div>

<div class="footer">
  Agentic QA Platform &nbsp;·&nbsp; Generated {{ timestamp }}
</div>

</body>
</html>
"""


def _detect_layer(test_result) -> str:
    name = test_result.test_name.lower()
    if "integration" in name or "/integration/" in name:
        return "integration"
    if "/ui/" in name or "playwright" in name or "page" in name:
        return "ui"
    return "api"


def _build_json_payload(report, coverage_before: Optional[float], coverage_after: Optional[float]) -> dict:
    data = report.model_dump()
    data["coverage_before"] = coverage_before
    data["coverage_after"] = coverage_after
    return data


def generate_reports(
    report,
    output_dir: Path = Path("reports"),
    coverage_before: Optional[float] = None,
    coverage_after: Optional[float] = None,
    rationale: Optional[str] = None,
) -> tuple[Path, Path]:
    """Generate reports/latest.json and reports/latest.html from a RunReport.

    Args:
        report: RunReport instance from src.agent.core.
        output_dir: Directory to write report files into.
        coverage_before: API coverage % from before this run (0–100).
        coverage_after: API coverage % after this run (0–100).
        rationale: Free-text agent reasoning summary (from RiskAssessment.rationale).

    Returns:
        (json_path, html_path) as resolved Path objects.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON ──────────────────────────────────────────────────────────────────
    json_payload = _build_json_payload(report, coverage_before, coverage_after)
    if rationale:
        json_payload["rationale"] = rationale
    json_path = output_dir / "latest.json"
    json_path.write_text(json.dumps(json_payload, indent=2, default=str))
    logger.info("JSON report written to %s", json_path)

    # ── HTML ──────────────────────────────────────────────────────────────────
    env = Environment(loader=BaseLoader(), autoescape=True)
    env.globals["op_risk_color"] = lambda level: _RISK_COLOR.get(level, "#6b7280")
    env.globals["status_color"] = lambda status: _STATUS_COLOR.get(status, "#6b7280")
    env.filters["detect_layer"] = _detect_layer
    env.filters["min"] = min

    ts = datetime.fromisoformat(report.timestamp)
    timestamp_short = ts.strftime("%Y-%m-%d %H:%M UTC")

    tmpl = env.from_string(_HTML_TEMPLATE)
    html = tmpl.render(
        timestamp=report.timestamp,
        timestamp_short=timestamp_short,
        diff_range=report.diff_range,
        overall_risk=report.overall_risk,
        risk_color=_RISK_COLOR.get(report.overall_risk, "#6b7280"),
        recommended_tests=report.recommended_test_count,
        new_tests=report.new_tests_generated,
        run_result=report.run_result,
        regressions=report.regressions,
        quality_gate=report.quality_gate_passed,
        operation_risks=report.operation_risks,
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        rationale=rationale or "",
    )

    html_path = output_dir / "latest.html"
    html_path.write_text(html)
    logger.info("HTML report written to %s", html_path)

    return json_path, html_path
