"""
src/analyzers/risk_scorer.py

LLM-powered risk scorer: takes a DiffAnalysis + affected GraphQL operations,
loads a rubric from risk_config.yml, and returns a structured RiskAssessment.
"""

import json
import logging
from pathlib import Path
from typing import Literal, Optional

import yaml
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.analyzers.diff_analyzer import DiffAnalysis
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

RiskLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "risk_config.yml"


class RiskConfig(BaseModel):
    """Parsed risk_config.yml — the rubric fed to the LLM."""

    model_config = ConfigDict(populate_by_name=True)

    risk_levels: dict[str, dict] = Field(default_factory=dict)
    model: str = Field(default="openai/gpt-oss-20b:free")
    fallback_level: RiskLevel = Field(default="MEDIUM")


class OperationRisk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_name: str
    risk_level: RiskLevel
    reason: str
    suggested_test_focus: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    overall_risk: RiskLevel
    rationale: str
    operation_risks: list[OperationRisk] = Field(default_factory=list)
    recommended_test_count: int


def load_risk_config(config_path: Optional[Path] = None) -> RiskConfig:
    """Load and validate risk_config.yml, falling back to defaults if missing."""
    path = config_path or _DEFAULT_CONFIG
    if not path.exists():
        logger.warning("risk_config.yml not found at %s; using defaults", path)
        return RiskConfig()
    with open(path) as f:
        raw = yaml.safe_load(f)
    return RiskConfig.model_validate(raw)


def _build_rubric_text(config: RiskConfig) -> str:
    """Render risk level definitions as a compact text block for the prompt."""
    lines: list[str] = []
    for level, details in config.risk_levels.items():
        desc = details.get("description", "").strip().replace("\n", " ")
        keywords = ", ".join(details.get("keywords", []))
        lines.append(f"- {level}: {desc} (keywords: {keywords})")
    return "\n".join(lines)


def _build_system_prompt(config: RiskConfig) -> str:
    rubric = _build_rubric_text(config)
    return f"""You are a senior QA architect assessing the risk level of GraphQL API changes.

Risk level definitions:
{rubric}

Your job:
1. Examine each affected GraphQL operation and the diff summary provided.
2. Assign a risk level (CRITICAL, HIGH, MEDIUM, or LOW) to each operation using the rubric above.
3. Determine the overall risk level for the entire change set (worst-case across all operations).
4. Recommend how many tests to generate for this change set overall.

You MUST respond with valid JSON matching this exact schema — no markdown, no explanation outside the JSON:
{{
  "overall_risk": "<CRITICAL|HIGH|MEDIUM|LOW>",
  "rationale": "<2-3 sentence explanation of the overall risk>",
  "recommended_test_count": <integer>,
  "operation_risks": [
    {{
      "operation_name": "<name>",
      "risk_level": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "reason": "<one sentence>",
      "suggested_test_focus": ["<focus area 1>", "<focus area 2>"]
    }}
  ]
}}"""


def _build_user_prompt(analysis: DiffAnalysis, operations: list[str]) -> str:
    changed_files = [
        f"  - {c.file_path} ({c.change_type.value}, +{len(c.added_lines)}/-{len(c.removed_lines)} lines)"
        for c in analysis.changed_files
    ]
    ops_text = "\n".join(f"  - {op}" for op in operations) or "  (none detected)"
    untraced = "\n".join(f"  - {p}" for p in analysis.untraced_changes) or "  (none)"

    return f"""Changed files:
{chr(10).join(changed_files)}

Affected GraphQL operations:
{ops_text}

Untraced files (no operation mapping found):
{untraced}

Assess the risk of this change set and return JSON as specified."""


class RiskScorer:
    """Scores risk for a DiffAnalysis using an LLM and a YAML rubric."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config = load_risk_config(config_path)
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )

    def score(
        self,
        analysis: DiffAnalysis,
        operations: Optional[list[str]] = None,
    ) -> RiskAssessment:
        """Return a RiskAssessment for the given DiffAnalysis."""
        ops = operations if operations is not None else analysis.affected_operations

        if not analysis.changed_files and not ops:
            logger.info("Empty diff — returning LOW risk with zero tests")
            return RiskAssessment(
                overall_risk="LOW",
                rationale="No changed files or operations detected in the diff.",
                operation_risks=[],
                recommended_test_count=0,
            )

        system_prompt = _build_system_prompt(self._config)
        user_prompt = _build_user_prompt(analysis, ops)

        logger.debug("Sending risk scoring request to OpenRouter model=%s", self._config.model)
        response = self._client.chat.completions.create(
            model=self._config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )

        raw = response.choices[0].message.content or ""
        logger.debug("Raw LLM response: %s", raw)

        # Strip markdown code fences if the model wraps JSON in them
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        data = json.loads(cleaned)
        assessment = RiskAssessment.model_validate(data)
        logger.info(
            "Risk assessment: overall=%s, test_count=%d, operations=%d",
            assessment.overall_risk,
            assessment.recommended_test_count,
            len(assessment.operation_risks),
        )
        return assessment
