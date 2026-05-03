"""
src/analyzers/coverage_analyzer.py

Identifies which GraphQL operations are covered by generated tests
and produces a prioritized list of uncovered operations.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from src.analyzers.schema_analyzer import GraphQLOperation, SchemaAnalyzer

logger = logging.getLogger(__name__)


class CoverageReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_operations: int
    covered_operations: int
    coverage_percentage: float
    uncovered: list[GraphQLOperation] = Field(default_factory=list)
    covered: list[str] = Field(default_factory=list)
    priority_queue: list[GraphQLOperation] = Field(default_factory=list)


class CoverageAnalyzer:
    """Compares schema operations against generated tests to identify coverage gaps."""

    def __init__(
        self,
        schema_analyzer: Optional[SchemaAnalyzer] = None,
        test_dir: Optional[Path] = None,
    ) -> None:
        self._schema_analyzer = schema_analyzer or SchemaAnalyzer()
        self._test_dir = test_dir or Path("generated_tests/api")
        self._covered_cache: set[str] = set()

    @staticmethod
    def _to_snake_case(name: str) -> str:
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()

    def _get_covered_names(self) -> set[str]:
        if not self._test_dir.is_dir():
            logger.warning("Test directory %s does not exist", self._test_dir)
            return set()
        return {p.stem for p in self._test_dir.glob("*.py")}

    def _score(self, op: GraphQLOperation) -> int:
        score = 0
        name_lower = op.name.lower()

        if op.type_ == "mutation":
            score += 20

        if any(kw in name_lower for kw in ("create", "update", "delete")):
            score += 15

        if any(kw in name_lower for kw in ("checkout", "payment", "order")):
            score += 25

        prefix = self._to_snake_case(op.name).split("_")[0]
        if any(covered.startswith(prefix) for covered in self._covered_cache):
            score -= 10

        return score

    def analyze(self) -> CoverageReport:
        all_ops = (
            self._schema_analyzer.get_all_queries()
            + self._schema_analyzer.get_all_mutations()
        )
        total = len(all_ops)

        self._covered_cache = self._get_covered_names()

        covered_names: list[str] = []
        uncovered_ops: list[GraphQLOperation] = []

        for op in all_ops:
            if self._to_snake_case(op.name) in self._covered_cache:
                covered_names.append(op.name)
            else:
                uncovered_ops.append(op)

        covered_count = len(covered_names)
        percentage = round(covered_count / total * 100.0, 2) if total > 0 else 0.0
        priority_queue = sorted(uncovered_ops, key=self._score, reverse=True)

        logger.info(
            "Coverage: %d/%d operations (%.1f%%)", covered_count, total, percentage
        )

        return CoverageReport(
            total_operations=total,
            covered_operations=covered_count,
            coverage_percentage=percentage,
            uncovered=uncovered_ops,
            covered=covered_names,
            priority_queue=priority_queue,
        )
