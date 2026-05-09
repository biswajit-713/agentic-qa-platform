"""
tests/test_ui_test_generator.py

Unit tests for UITestGenerator. Mocks OpenRouter API calls.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.generators.ui_test_generator import UITestGenerator, UITestCase, FLOWS


@pytest.fixture
def sample_test_case() -> UITestCase:
    return UITestCase(
        test_name="test_search_product",
        description="Search for a product by name and verify results are displayed",
        test_code="""import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_search_product(page: Page):
    # Step 1: Navigate to storefront
    await page.goto("http://localhost:3000")
    # Step 2: Search for a product
    await page.get_by_placeholder("Search").fill("T-Shirt")
    await page.keyboard.press("Enter")
    # Step 3: Verify results
    await expect(page.locator("[data-testid='product-card']").first).to_be_visible()
""",
    )


@pytest.fixture
def generator() -> UITestGenerator:
    return UITestGenerator(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )


class TestUITestCaseModel:
    def test_valid_model(self, sample_test_case: UITestCase):
        assert sample_test_case.test_name == "test_search_product"
        assert "playwright" in sample_test_case.test_code.lower()

    def test_requires_test_name(self):
        with pytest.raises(Exception):
            UITestCase(description="desc", test_code="code")

    def test_requires_test_code(self):
        with pytest.raises(Exception):
            UITestCase(test_name="test_x", description="desc")


class TestUITestGeneratorInit:
    def test_uses_provided_storefront_url(self):
        gen = UITestGenerator(
            storefront_url="http://custom:4000",
            openrouter_api_key="key",
        )
        assert gen.storefront_url == "http://custom:4000"

    def test_defaults_to_localhost_3000(self, generator: UITestGenerator):
        assert generator.storefront_url == "http://localhost:3000"

    def test_system_prompt_contains_storefront_url(self, generator: UITestGenerator):
        assert "localhost:3000" in generator.SYSTEM_PROMPT

    def test_system_prompt_requires_asyncio_mark(self, generator: UITestGenerator):
        assert "asyncio" in generator.SYSTEM_PROMPT


class TestGenerate:
    def test_generate_returns_ui_test_case(self, generator: UITestGenerator, sample_test_case: UITestCase):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"

        with patch.object(generator.client.beta.chat.completions, "parse", return_value=mock_response):
            result = generator.generate("search for a product")

        assert isinstance(result, UITestCase)
        assert result.test_name == "test_search_product"

    def test_generate_raises_on_null_response(self, generator: UITestGenerator):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = None
        mock_response.choices[0].message.content = "null"

        with patch.object(generator.client.beta.chat.completions, "parse", return_value=mock_response):
            with pytest.raises(ValueError, match="null test case"):
                generator.generate("some flow")

    def test_generate_raises_on_api_error(self, generator: UITestGenerator):
        with patch.object(generator.client.beta.chat.completions, "parse", side_effect=Exception("API error")):
            with pytest.raises(Exception, match="API error"):
                generator.generate("some flow")

    def test_generate_sends_flow_name_in_prompt(self, generator: UITestGenerator, sample_test_case: UITestCase):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"

        with patch.object(generator.client.beta.chat.completions, "parse", return_value=mock_response) as mock_parse:
            generator.generate("add product to cart")

        call_kwargs = mock_parse.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        assert "add product to cart" in user_message


class TestWriteTest:
    def test_write_creates_file(self, generator: UITestGenerator, sample_test_case: UITestCase, tmp_path: Path):
        with patch("src.generators.ui_test_generator.Path") as mock_path_cls:
            output_dir = tmp_path / "generated_tests" / "ui"
            mock_path_cls.return_value = output_dir
            # Use real Path for this test
            result = generator.write_test.__wrapped__(generator, sample_test_case) if hasattr(generator.write_test, "__wrapped__") else None

        # Test with real filesystem via tmp_path
        import os
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(sample_test_case)
            assert result.exists()
            assert result.name == "test_search_product.py"
            assert "playwright" in result.read_text().lower()
        finally:
            os.chdir(original_dir)

    def test_write_sanitizes_filename(self, generator: UITestGenerator, tmp_path: Path):
        test_case = UITestCase(
            test_name="test-search-product",
            description="desc",
            test_code="import pytest\n",
        )
        import os
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(test_case)
            assert "-" not in result.name
            assert result.name == "test_search_product.py"
        finally:
            os.chdir(original_dir)

    def test_write_adds_test_prefix_if_missing(self, generator: UITestGenerator, tmp_path: Path):
        test_case = UITestCase(
            test_name="search_product",
            description="desc",
            test_code="import pytest\n",
        )
        import os
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = generator.write_test(test_case)
            assert result.name.startswith("test_")
        finally:
            os.chdir(original_dir)


class TestPageContextInjection:
    """Tests that page_context is correctly injected into the LLM prompt."""

    def _mock_response(self, sample_test_case):
        mock_response = MagicMock()
        mock_response.choices[0].message.parsed = sample_test_case
        mock_response.choices[0].message.content = "{}"
        return mock_response

    def _get_user_message(self, mock_parse):
        call_kwargs = mock_parse.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1]
        return next(m["content"] for m in messages if m["role"] == "user")

    def test_prompt_without_context_has_no_accessibility_tree(
        self, generator: UITestGenerator, sample_test_case: UITestCase
    ):
        with patch.object(
            generator.client.beta.chat.completions, "parse", return_value=self._mock_response(sample_test_case)
        ) as mock_parse:
            generator.generate("search flow", page_context=None)

        user_msg = self._get_user_message(mock_parse)
        assert "accessibility tree" not in user_msg.lower()

    def test_prompt_with_context_includes_accessibility_tree(
        self, generator: UITestGenerator, sample_test_case: UITestCase
    ):
        context = {"role": "main", "children": [{"role": "button", "name": "Add to cart"}]}

        with patch.object(
            generator.client.beta.chat.completions, "parse", return_value=self._mock_response(sample_test_case)
        ) as mock_parse:
            generator.generate("search flow", page_context=context)

        user_msg = self._get_user_message(mock_parse)
        assert "accessibility tree" in user_msg.lower()
        assert "Add to cart" in user_msg

    def test_prompt_with_context_instructs_get_by_role(
        self, generator: UITestGenerator, sample_test_case: UITestCase
    ):
        context = {"role": "button", "name": "Checkout"}

        with patch.object(
            generator.client.beta.chat.completions, "parse", return_value=self._mock_response(sample_test_case)
        ) as mock_parse:
            generator.generate("checkout flow", page_context=context)

        user_msg = self._get_user_message(mock_parse)
        assert "get_by_role" in user_msg

    def test_generate_from_live_page_single_url(
        self, generator: UITestGenerator, sample_test_case: UITestCase
    ):
        fake_context = {"role": "button", "name": "Search"}

        with patch("src.generators.ui_test_generator.PageContextExtractor") as MockExtractor:
            MockExtractor.return_value.extract.return_value = fake_context
            with patch.object(
                generator.client.beta.chat.completions,
                "parse",
                return_value=self._mock_response(sample_test_case),
            ) as mock_parse:
                result = generator.generate_from_live_page("search flow", ["http://localhost:3000"])

        MockExtractor.return_value.extract.assert_called_once_with("http://localhost:3000")
        assert isinstance(result, UITestCase)

    def test_generate_from_live_page_multiple_urls_uses_extract_flow(
        self, generator: UITestGenerator, sample_test_case: UITestCase
    ):
        fake_context = {
            "http://localhost:3000": {"role": "button", "name": "Search"},
            "http://localhost:3000/cart": {"role": "button", "name": "Checkout"},
        }
        urls = ["http://localhost:3000", "http://localhost:3000/cart"]

        with patch("src.generators.ui_test_generator.PageContextExtractor") as MockExtractor:
            MockExtractor.return_value.extract_flow.return_value = fake_context
            with patch.object(
                generator.client.beta.chat.completions,
                "parse",
                return_value=self._mock_response(sample_test_case),
            ):
                generator.generate_from_live_page("cart flow", urls)

        MockExtractor.return_value.extract_flow.assert_called_once_with(urls)


class TestFlowsConstant:
    def test_flows_contains_five_entries(self):
        assert len(FLOWS) == 5

    def test_flows_cover_expected_areas(self):
        flows_text = " ".join(FLOWS).lower()
        assert "cart" in flows_text
        assert "homepage" in flows_text
        assert "keyboard" in flows_text or "accessible" in flows_text
