"""Tests for src/analyzers/coverage_analyzer.py"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.analyzers.coverage_analyzer import CoverageAnalyzer, CoverageReport
from src.analyzers.schema_analyzer import GraphQLOperation


@pytest.fixture
def query_op():
    return GraphQLOperation(name="products", type="query", returnType="ProductConnection")


@pytest.fixture
def mutation_create_op():
    return GraphQLOperation(name="productCreate", type="mutation", returnType="ProductCreate")


@pytest.fixture
def mutation_checkout_op():
    return GraphQLOperation(name="checkoutCreate", type="mutation", returnType="CheckoutCreate")


@pytest.fixture
def mock_schema(query_op, mutation_create_op, mutation_checkout_op):
    schema = MagicMock()
    schema.get_all_queries.return_value = [query_op]
    schema.get_all_mutations.return_value = [mutation_create_op, mutation_checkout_op]
    return schema


def test_empty_test_dir_returns_zero_coverage(mock_schema, tmp_path):
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    report = analyzer.analyze()

    assert report.total_operations == 3
    assert report.covered_operations == 0
    assert report.coverage_percentage == 0.0
    assert len(report.covered) == 0
    assert len(report.uncovered) == 3


def test_partial_coverage(mock_schema, tmp_path):
    (tmp_path / "products.py").touch()
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    report = analyzer.analyze()

    assert report.covered_operations == 1
    assert "products" in report.covered
    assert report.coverage_percentage == pytest.approx(33.33, abs=0.01)


def test_full_coverage(mock_schema, tmp_path):
    (tmp_path / "products.py").touch()
    (tmp_path / "product_create.py").touch()
    (tmp_path / "checkout_create.py").touch()
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    report = analyzer.analyze()

    assert report.covered_operations == 3
    assert report.coverage_percentage == 100.0
    assert len(report.uncovered) == 0
    assert len(report.priority_queue) == 0


def test_mutation_scores_higher_than_query(mock_schema, tmp_path):
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    analyzer._covered_cache = set()

    query_score = analyzer._score(
        GraphQLOperation(name="products", type="query", returnType="X")
    )
    mutation_score = analyzer._score(
        GraphQLOperation(name="tagCreate", type="mutation", returnType="X")
    )
    assert mutation_score > query_score


def test_checkout_keyword_adds_highest_bonus(tmp_path):
    schema = MagicMock()
    schema.get_all_queries.return_value = []
    schema.get_all_mutations.return_value = []
    analyzer = CoverageAnalyzer(schema_analyzer=schema, test_dir=tmp_path)
    analyzer._covered_cache = set()

    checkout_op = GraphQLOperation(name="checkoutCreate", type="mutation", returnType="X")
    plain_mutation = GraphQLOperation(name="tagCreate", type="mutation", returnType="X")

    assert analyzer._score(checkout_op) > analyzer._score(plain_mutation)


def test_priority_queue_sorted_descending(mock_schema, tmp_path):
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    report = analyzer.analyze()

    scores = [analyzer._score(op) for op in report.priority_queue]
    assert scores == sorted(scores, reverse=True)


def test_coverage_percentage_calculation(mock_schema, tmp_path):
    (tmp_path / "product_create.py").touch()
    analyzer = CoverageAnalyzer(schema_analyzer=mock_schema, test_dir=tmp_path)
    report = analyzer.analyze()

    assert report.coverage_percentage == pytest.approx(33.33, abs=0.01)


def test_nonexistent_test_dir_handled_gracefully(mock_schema):
    analyzer = CoverageAnalyzer(
        schema_analyzer=mock_schema,
        test_dir=Path("/nonexistent/path/that/does/not/exist"),
    )
    report = analyzer.analyze()

    assert report.covered_operations == 0
    assert report.coverage_percentage == 0.0
