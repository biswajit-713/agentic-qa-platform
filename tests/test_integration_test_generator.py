"""
tests/test_integration_test_generator.py

Unit tests for IntegrationTestGenerator. Mocks OpenRouter API calls.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.generators.integration_test_generator import (
    IntegrationTestGenerator,
    IntegrationTestCase,
    SCENARIOS,
    GRAPHQL_URL,
    STOREFRONT_URL,
)


@pytest.fixture
def sample_test_case() -> IntegrationTestCase:
    return IntegrationTestCase(
        test_name="test_create_product_verify_storefront",
        description="Create a product via GraphQL then verify it appears on the storefront",
        test_code="""import pytest
import httpx
import os
from playwright.sync_api import sync_playwright, expect

GRAPHQL_URL = "http://localhost:8000/graphql/"
STOREFRONT_URL = "http://localhost:3000"

def test_create_product_verify_storefront():
    token = os.environ.get("SALEOR_ADMIN_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Setup
    product_id = None

    # Action
    mutation = '''
    mutation CreateProduct($input: ProductCreateInput!) {
        productCreate(input: $input) {
            product { id name }
            errors { field message }
        }
    }
    '''
    resp = httpx.post(GRAPHQL_URL, json={"query": mutation, "variables": {"input": {"name": "Test Product", "productType": "1", "category": "1"}}}, headers=headers)
    data = resp.json().get("data", {}).get("productCreate", {})
    assert not data.get("errors"), f"API errors: {data.get('errors')}"
    product_id = data["product"]["id"]

    # Assert UI
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(STOREFRONT_URL)
        expect(page.get_by_text("Test Product")).to_be_visible()
        browser.close()

    # Teardown
    if product_id:
        delete_mutation = '''
        mutation DeleteProduct($id: ID!) {
            productDelete(id: $id) { product { id } errors { field message } }
        }
        '''
        httpx.post(GRAPHQL_URL, json={"query": delete_mutation, "variables": {"id": product_id}}, headers=headers)
""",
    )


@pytest.fixture
def generator() -> IntegrationTestGenerator:
    return IntegrationTestGenerator(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )


class TestIntegrationTestCaseModel:
    def test_valid_model(self, sample_test_case: IntegrationTestCase):
        assert sample_test_case.test_name == "test_create_product_verify_storefront"
        assert "httpx" in sample_test_case.test_code

    def test_requires_test_name(self):
        with pytest.raises(Exception):
            IntegrationTestCase(description="desc", test_code="code")

    def test_requires_test_code(self):
        with pytest.raises(Exception):
            IntegrationTestCase(test_name="test_x", description="desc")


class TestIntegrationTestGeneratorInit:
    def test_defaults_to_module_constants(self, generator: IntegrationTestGenerator):
        assert generator.graphql_url == GRAPHQL_URL
        assert generator.storefront_url == STOREFRONT_URL

    def test_accepts_custom_urls(self):
        gen = IntegrationTestGenerator(
            graphql_url="http://custom:9000/graphql/",
            storefront_url="http://custom:4000",
            openrouter_api_key="key",
        )
        assert gen.graphql_url == "http://custom:9000/graphql/"
        assert gen.storefront_url == "http://custom:4000"

    def test_system_prompt_contains_both_urls(self, generator: IntegrationTestGenerator):
        assert "localhost:8000" in generator.SYSTEM_PROMPT
        assert "localhost:3000" in generator.SYSTEM_PROMPT

    def test_system_prompt_mentions_phases(self, generator: IntegrationTestGenerator):
        prompt = generator.SYSTEM_PROMPT
        assert "Setup" in prompt
        assert "Teardown" in prompt


class TestGenerate:
    def test_generate_returns_integration_test_case(
        self, generator: IntegrationTestGenerator, sample_test_case: IntegrationTestCase
    ):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"

        with patch.object(generator.client.beta.chat.completions, "parse", return_value=mock_response):
            result = generator.generate("create product via API then verify on storefront")

        assert isinstance(result, IntegrationTestCase)
        assert result.test_name == "test_create_product_verify_storefront"

    def test_generate_raises_on_null_response(self, generator: IntegrationTestGenerator):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = None
        mock_response.choices[0].message.content = "null"

        with patch.object(generator.client.beta.chat.completions, "parse", return_value=mock_response):
            with pytest.raises(ValueError, match="null test case"):
                generator.generate("some scenario")

    def test_generate_raises_on_api_error(self, generator: IntegrationTestGenerator):
        with patch.object(
            generator.client.beta.chat.completions, "parse", side_effect=Exception("API error")
        ):
            with pytest.raises(Exception, match="API error"):
                generator.generate("some scenario")

    def test_generate_sends_scenario_in_prompt(
        self, generator: IntegrationTestGenerator, sample_test_case: IntegrationTestCase
    ):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"

        with patch.object(
            generator.client.beta.chat.completions, "parse", return_value=mock_response
        ) as mock_parse:
            generator.generate("create product via API then verify on storefront")

        call_kwargs = mock_parse.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        assert "create product via API" in user_message

    def test_generate_includes_both_urls_in_prompt(
        self, generator: IntegrationTestGenerator, sample_test_case: IntegrationTestCase
    ):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"

        with patch.object(
            generator.client.beta.chat.completions, "parse", return_value=mock_response
        ) as mock_parse:
            generator.generate("any scenario")

        call_kwargs = mock_parse.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        assert "localhost:8000" in user_message
        assert "localhost:3000" in user_message


class TestWriteTest:
    def test_write_creates_file(self, generator: IntegrationTestGenerator, sample_test_case: IntegrationTestCase, tmp_path: Path):
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(sample_test_case)
            assert result.exists()
            assert result.name == "test_create_product_verify_storefront.py"
            assert "httpx" in result.read_text()
        finally:
            os.chdir(original_dir)

    def test_write_sanitizes_filename(self, generator: IntegrationTestGenerator, tmp_path: Path):
        test_case = IntegrationTestCase(
            test_name="test-create-product",
            description="desc",
            test_code="import pytest\n",
        )
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(test_case)
            assert "-" not in result.name
        finally:
            os.chdir(original_dir)

    def test_write_adds_test_prefix_if_missing(self, generator: IntegrationTestGenerator, tmp_path: Path):
        test_case = IntegrationTestCase(
            test_name="create_product_flow",
            description="desc",
            test_code="import pytest\n",
        )
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(test_case)
            assert result.name.startswith("test_")
        finally:
            os.chdir(original_dir)

    def test_write_outputs_to_integration_directory(
        self, generator: IntegrationTestGenerator, sample_test_case: IntegrationTestCase, tmp_path: Path
    ):
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(sample_test_case)
            assert "integration" in str(result)
        finally:
            os.chdir(original_dir)


class TestScenariosConstant:
    def test_has_three_scenarios(self):
        assert len(SCENARIOS) == 3

    def test_covers_api_to_ui(self):
        assert any("api" in s.lower() or "API" in s for s in SCENARIOS)

    def test_covers_ui_to_api(self):
        assert any("ui" in s.lower() or "cart" in s.lower() for s in SCENARIOS)

    def test_covers_checkout(self):
        assert any("checkout" in s.lower() or "order" in s.lower() for s in SCENARIOS)
