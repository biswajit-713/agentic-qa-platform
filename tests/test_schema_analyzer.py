"""
tests/test_schema_analyzer.py

Unit tests for the GraphQL schema analyzer with httpx mocking.
"""

import pytest
from unittest.mock import patch, MagicMock
import httpx

from src.analyzers.schema_analyzer import (
    SchemaAnalyzer,
    GraphQLOperation,
    GraphQLField,
    GraphQLInputValue,
)


@pytest.fixture
def mock_schema_response():
    """Mock response from GraphQL introspection query."""
    return {
        "data": {
            "__schema": {
                "types": [
                    {
                        "name": "String",
                        "kind": "SCALAR",
                        "description": "String type",
                        "fields": [],
                    }
                ],
                "queryType": {
                    "name": "Query",
                    "fields": [
                        {
                            "name": "products",
                            "description": "Get all products",
                            "args": [
                                {
                                    "name": "first",
                                    "description": "Number of products",
                                    "type": {
                                        "name": "Int",
                                        "kind": "SCALAR",
                                        "ofType": None,
                                    },
                                    "defaultValue": None,
                                }
                            ],
                            "type": {
                                "name": None,
                                "kind": "NON_NULL",
                                "ofType": {
                                    "name": "ProductConnection",
                                    "kind": "OBJECT",
                                    "ofType": None,
                                },
                            },
                        }
                    ],
                },
                "mutationType": {
                    "name": "Mutation",
                    "fields": [
                        {
                            "name": "createProduct",
                            "description": "Create a product",
                            "args": [
                                {
                                    "name": "input",
                                    "description": "Product input",
                                    "type": {
                                        "name": None,
                                        "kind": "NON_NULL",
                                        "ofType": {
                                            "name": "ProductInput",
                                            "kind": "INPUT_OBJECT",
                                            "ofType": None,
                                        },
                                    },
                                    "defaultValue": None,
                                }
                            ],
                            "type": {
                                "name": "CreateProductPayload",
                                "kind": "OBJECT",
                                "ofType": None,
                            },
                        }
                    ],
                },
            }
        }
    }


@pytest.fixture
def analyzer(mock_schema_response):
    """Create SchemaAnalyzer instance with mocked fetch."""
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_schema_response
        mock_post.return_value = mock_response

        analyzer = SchemaAnalyzer("http://localhost:8000/graphql/")
        analyzer.fetch_schema()
        return analyzer


def test_schema_analyzer_initialization():
    """Test that SchemaAnalyzer initializes correctly."""
    analyzer = SchemaAnalyzer("http://localhost:8000/graphql/")
    assert analyzer.graphql_url == "http://localhost:8000/graphql/"
    assert analyzer._schema is None
    assert len(analyzer._queries) == 0
    assert len(analyzer._mutations) == 0


def test_fetch_schema_success(mock_schema_response):
    """Test successful schema fetching and parsing."""
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_schema_response
        mock_post.return_value = mock_response

        analyzer = SchemaAnalyzer("http://localhost:8000/graphql/")
        schema = analyzer.fetch_schema()

        assert schema is not None
        assert "queryType" in schema
        assert "mutationType" in schema
        mock_post.assert_called_once()


def test_fetch_schema_graphql_error(mock_schema_response):
    """Test handling of GraphQL errors in response."""
    with patch("httpx.Client.post") as mock_post:
        error_response = {"errors": [{"message": "Invalid query"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = error_response
        mock_post.return_value = mock_response

        analyzer = SchemaAnalyzer("http://localhost:8000/graphql/")
        with pytest.raises(ValueError, match="GraphQL introspection failed"):
            analyzer.fetch_schema()


def test_fetch_schema_http_error():
    """Test handling of HTTP errors."""
    with patch("httpx.Client.post") as mock_post:
        mock_post.side_effect = httpx.RequestError("Connection failed")

        analyzer = SchemaAnalyzer("http://localhost:8000/graphql/")
        with pytest.raises(httpx.RequestError):
            analyzer.fetch_schema()


def test_get_all_queries(analyzer):
    """Test retrieving all queries."""
    queries = analyzer.get_all_queries()
    assert len(queries) == 1
    assert queries[0].name == "products"
    assert queries[0].type_ == "query"
    assert queries[0].return_type == "ProductConnection"


def test_get_all_mutations(analyzer):
    """Test retrieving all mutations."""
    mutations = analyzer.get_all_mutations()
    assert len(mutations) == 1
    assert mutations[0].name == "createProduct"
    assert mutations[0].type_ == "mutation"
    assert mutations[0].return_type == "CreateProductPayload"


def test_get_operation_by_name_query(analyzer):
    """Test retrieving a specific query by name."""
    op = analyzer.get_operation_by_name("products")
    assert op is not None
    assert op.name == "products"
    assert op.type_ == "query"


def test_get_operation_by_name_mutation(analyzer):
    """Test retrieving a specific mutation by name."""
    op = analyzer.get_operation_by_name("createProduct")
    assert op is not None
    assert op.name == "createProduct"
    assert op.type_ == "mutation"


def test_get_operation_by_name_not_found(analyzer):
    """Test retrieving a non-existent operation."""
    op = analyzer.get_operation_by_name("nonExistentOperation")
    assert op is None


def test_operation_args_parsing(analyzer):
    """Test that operation arguments are parsed correctly."""
    products_op = analyzer.get_operation_by_name("products")
    assert len(products_op.args) == 1
    assert products_op.args[0].name == "first"
    assert products_op.args[0].type_name == "Int"

    create_op = analyzer.get_operation_by_name("createProduct")
    assert len(create_op.args) == 1
    assert create_op.args[0].name == "input"
    assert create_op.args[0].type_name == "ProductInput"
    assert create_op.args[0].is_required is True


def test_extract_type_name_from_scalar():
    """Test extracting type name from scalar type."""
    analyzer = SchemaAnalyzer()
    type_obj = {"name": "String", "kind": "SCALAR", "ofType": None}
    assert analyzer._extract_type_name(type_obj) == "String"


def test_extract_type_name_from_wrapped_type():
    """Test extracting type name from wrapped (nullable/non-null) type."""
    analyzer = SchemaAnalyzer()
    type_obj = {
        "name": None,
        "kind": "NON_NULL",
        "ofType": {"name": "ProductConnection", "kind": "OBJECT", "ofType": None},
    }
    assert analyzer._extract_type_name(type_obj) == "ProductConnection"


def test_is_required_type():
    """Test checking if a type is required (non-null)."""
    analyzer = SchemaAnalyzer()
    assert analyzer._is_required_type({"kind": "NON_NULL"}) is True
    assert analyzer._is_required_type({"kind": "OBJECT"}) is False
    assert analyzer._is_required_type({}) is False
