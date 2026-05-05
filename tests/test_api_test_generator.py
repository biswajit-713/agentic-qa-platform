"""
tests/test_api_test_generator.py

Unit tests for ApiTestGenerator. Mocks OpenRouter API calls.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.generators.api_test_generator import ApiTestGenerator, TestCase
from src.analyzers.schema_analyzer import GraphQLOperation, GraphQLInputValue


@pytest.fixture
def query_operation() -> GraphQLOperation:
    """A sample GraphQL query operation."""
    return GraphQLOperation(
        name="GetProduct",
        type="query",
        returnType="Product",
        description="Fetch a single product by ID",
        args=[
            GraphQLInputValue(
                name="id",
                typeName="ID",
                isRequired=True,
                description="Product ID",
            )
        ],
    )


@pytest.fixture
def mutation_operation() -> GraphQLOperation:
    """A sample GraphQL mutation operation."""
    return GraphQLOperation(
        name="CreateOrder",
        type="mutation",
        returnType="Order",
        description="Create a new order",
        args=[
            GraphQLInputValue(
                name="input",
                typeName="OrderInput",
                isRequired=True,
                description="Order input data",
            ),
            GraphQLInputValue(
                name="dryRun",
                typeName="Boolean",
                isRequired=False,
                description="Dry run flag",
            ),
        ],
    )


@pytest.fixture
def sample_test_case() -> TestCase:
    """A sample generated test case."""
    return TestCase(
        test_name="test_get_product_by_id",
        description="Test fetching a product by its ID",
        graphql_query="""
        query GetProduct($id: ID!) {
            product(id: $id) {
                id
                name
                slug
            }
        }
        """,
        test_code="""
import pytest
from conftest import execute_graphql


def test_get_product_by_id(auth_headers):
    query = '''
    query GetProduct($id: ID!) {
        product(id: $id) {
            id
            name
            slug
        }
    }
    '''
    variables = {"id": "UHJvZHVjdDox"}

    response_data = execute_graphql(query, variables, headers=auth_headers)
    data = response_data.get("data", {}).get("product", {})
    assert data.get("id") == variables["id"]
    assert "name" in data
    assert "slug" in data
""",
    )


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_generate_returns_test_case(mock_openai_class, mock_get_settings, query_operation, sample_test_case):
    """Test that generate() returns a TestCase object."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # Mock the API response
    mock_response = Mock()
    mock_message = Mock()
    mock_message.parsed = sample_test_case
    mock_response.choices = [Mock(message=mock_message)]
    mock_client.beta.chat.completions.parse.return_value = mock_response

    generator = ApiTestGenerator()
    result = generator.generate(query_operation)

    assert isinstance(result, TestCase)
    assert result.test_name == sample_test_case.test_name
    assert result.graphql_query == sample_test_case.graphql_query
    assert result.test_code == sample_test_case.test_code


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_write_test_creates_file(mock_openai_class, mock_get_settings, sample_test_case, tmp_path):
    """Test that write_test() creates a file in the correct location."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_openai_class.return_value = MagicMock()

    # Patch Path to use tmp_path for this test
    with patch("src.generators.api_test_generator.Path") as mock_path_class:
        mock_output_dir = tmp_path / "generated_tests" / "api"
        mock_output_dir.mkdir(parents=True, exist_ok=True)

        mock_path_class.return_value = mock_output_dir

        generator = ApiTestGenerator()
        test_file = generator.write_test(sample_test_case)

        # Verify path construction
        mock_path_class.assert_called_with("generated_tests/api")


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_write_test_filename_is_test_name(mock_openai_class, mock_get_settings, sample_test_case, tmp_path):
    """Test that filename matches test_name."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_openai_class.return_value = MagicMock()

    # Temporarily change working directory to tmp_path
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        generator = ApiTestGenerator()
        test_file = generator.write_test(sample_test_case)

        assert test_file.name == f"{sample_test_case.test_name}.py"
        assert test_file.exists()
        assert test_file.read_text() == sample_test_case.test_code
    finally:
        os.chdir(original_cwd)


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_generate_with_mutation_operation(mock_openai_class, mock_get_settings, mutation_operation, sample_test_case):
    """Test that generate() works with mutation operations."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # Mock the API response
    mock_response = Mock()
    mock_message = Mock()
    mock_message.parsed = sample_test_case
    mock_response.choices = [Mock(message=mock_message)]
    mock_client.beta.chat.completions.parse.return_value = mock_response

    generator = ApiTestGenerator()
    result = generator.generate(mutation_operation)

    assert isinstance(result, TestCase)
    # Verify the prompt was built with mutation-specific language
    call_args = mock_client.beta.chat.completions.parse.call_args
    prompt_content = call_args[1]["messages"][1]["content"]
    assert "mutation" in prompt_content


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_generate_handles_api_error(mock_openai_class, mock_get_settings, query_operation):
    """Test that generate() handles API errors gracefully."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.beta.chat.completions.parse.side_effect = Exception("API request failed")

    generator = ApiTestGenerator()

    with pytest.raises(Exception, match="API request failed"):
        generator.generate(query_operation)


@patch("src.generators.api_test_generator.get_settings")
@patch("src.generators.api_test_generator.OpenAI")
def test_generated_code_imports_execute_graphql(mock_openai_class, mock_get_settings, query_operation, sample_test_case):
    """Generated test_code must import execute_graphql from conftest, not use httpx directly."""
    mock_settings = Mock()
    mock_settings.openrouter_api_key = "test-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.saleor_graphql_url = "http://localhost:8000/graphql/"
    mock_get_settings.return_value = mock_settings

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_response = Mock()
    mock_message = Mock()
    mock_message.parsed = sample_test_case
    mock_response.choices = [Mock(message=mock_message)]
    mock_client.beta.chat.completions.parse.return_value = mock_response

    generator = ApiTestGenerator()
    result = generator.generate(query_operation)

    assert "from conftest import execute_graphql" in result.test_code, (
        "Generated test must import execute_graphql from conftest"
    )
    assert "import httpx" not in result.test_code, (
        "Generated test must not import httpx directly"
    )
    assert "import os" not in result.test_code, (
        "Generated test must not import os directly"
    )
