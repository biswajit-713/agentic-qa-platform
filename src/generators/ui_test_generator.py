"""
src/generators/ui_test_generator.py

Generates Playwright async Python tests for Saleor's React storefront using OpenRouter.
Tests target the storefront at localhost:3000 and cover critical user flows.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI

from src.config.settings import get_settings
from src.analyzers.page_context_extractor import PageContextExtractor

logger = logging.getLogger(__name__)

STOREFRONT_URL = "http://localhost:3000"

FLOWS = [
    "homepage renders with navigation, hero section, and footer visible",
    "navigating to an invalid product URL shows a 404 or not-found page",
    "search input is accessible and responds to keyboard input without requiring results",
    "mobile viewport: hamburger menu opens and nav links are reachable",
    "cart page renders an empty state message when no items have been added",
]


class UITestCase(BaseModel):
    """Structured output from LLM: a complete Playwright test case."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str = Field(
        ...,
        description="Snake_case test function name with 'test_' prefix, e.g. 'test_search_product'",
    )
    description: str = Field(..., description="Human-readable explanation of what the test verifies")
    test_code: str = Field(
        ...,
        description="Complete, executable async pytest-playwright function with imports, steps, and assertions",
    )


class UITestGenerator:
    """Generates Playwright tests for Saleor's storefront via OpenRouter."""

    SYSTEM_PROMPT = f"""You are an expert Playwright test engineer writing async Python tests for a Saleor
React/Next.js storefront at {STOREFRONT_URL}.

Rules:
1. Use `async def test_...` with `page: Page` as the fixture parameter.
2. Import only: `import pytest`, `from playwright.async_api import Page, expect`.
3. Add a `# Step N:` comment before each logical action group.
4. Include realistic assertions using `expect(locator).to_be_visible()`, `.to_have_text()`, `.to_have_url()`.
5. Use `page.goto`, `page.fill`, `page.click`, `page.locator`, `page.get_by_*` — standard Playwright API.
6. Mark the test with `@pytest.mark.asyncio`.
7. Use `await` on all page interactions and assertions.
8. Do NOT import httpx, requests, or any non-playwright libraries.
9. No TODOs, placeholders, or hardcoded credentials.
10. Target realistic Saleor storefront selectors (search input, product cards, cart icon, checkout button).

Example structure:
```python
import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_example_flow(page: Page):
    # Step 1: Navigate to storefront
    await page.goto("{STOREFRONT_URL}")
    # Step 2: ...
    await expect(page.locator("...")).to_be_visible()
```"""

    def __init__(
        self,
        storefront_url: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_base_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.storefront_url = storefront_url or STOREFRONT_URL
        self.openrouter_api_key = openrouter_api_key or settings.openrouter_api_key
        self.openrouter_base_url = openrouter_base_url or settings.openrouter_base_url

        self.client = OpenAI(
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
        )

    def generate(self, flow_name: str, page_context: Optional[dict] = None) -> UITestCase:
        """Generate a Playwright test for the given user flow description.

        Args:
            flow_name: Natural language description of the flow to test.
            page_context: Optional pruned accessibility tree from PageContextExtractor.
                          When provided, the LLM uses real selectors instead of guesses.

        Returns:
            UITestCase with the generated test code.

        Raises:
            ValueError: If the LLM returns an invalid or empty response.
        """
        user_prompt = self._build_prompt(flow_name, page_context)

        try:
            response = self.client.beta.chat.completions.parse(
                model="openai/gpt-oss-120b:free",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=UITestCase,
                temperature=0.2,
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw LLM response for flow '{flow_name}':\n{raw_content}")

            test_case = response.choices[0].message.parsed
            if not test_case:
                raise ValueError(f"LLM returned null test case for flow: {flow_name}")

            logger.info(f"Generated UI test '{test_case.test_name}' for flow: {flow_name}")
            return test_case

        except Exception as e:
            logger.error(f"Failed to generate UI test for flow '{flow_name}': {e}")
            raise

    def write_test(self, test_case: UITestCase) -> Path:
        """Write a UITestCase to generated_tests/ui/.

        Args:
            test_case: UITestCase with the test_code to write.

        Returns:
            Path of the written file.

        Raises:
            IOError: If the file cannot be written.
        """
        output_dir = Path("generated_tests/ui")
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^a-z0-9_]", "_", test_case.test_name.lower())
        if not safe_name.startswith("test_"):
            safe_name = f"test_{safe_name}"
        test_file = output_dir / f"{safe_name}.py"

        try:
            test_file.write_text(test_case.test_code)
            logger.info(f"Wrote UI test to {test_file}")
            return test_file
        except IOError as e:
            logger.error(f"Failed to write UI test file {test_file}: {e}")
            raise

    def generate_and_write(self, flow_name: str, page_context: Optional[dict] = None) -> Path:
        """Generate a test for a flow and write it to disk.

        Args:
            flow_name: Natural language description of the user flow.
            page_context: Optional accessibility tree from PageContextExtractor.

        Returns:
            Path of the written test file.
        """
        test_case = self.generate(flow_name, page_context)
        return self.write_test(test_case)

    def generate_from_live_page(self, flow_name: str, urls: list[str]) -> UITestCase:
        """Visit pages, extract live accessibility context, then generate the test.

        Use this for any site the LLM has not been trained on. The extractor
        snapshots the real DOM so the LLM grounds selectors in actual elements.

        Args:
            flow_name: Natural language description of the flow.
            urls: One URL per step in the flow (e.g. [home, product, cart]).

        Returns:
            UITestCase grounded in the live page structure.
        """
        extractor = PageContextExtractor()
        if len(urls) == 1:
            page_context = extractor.extract(urls[0])
        else:
            page_context = extractor.extract_flow(urls)
        return self.generate(flow_name, page_context)

    def _build_prompt(self, flow_name: str, page_context: Optional[dict] = None) -> str:
        prompt = f"""Generate a complete async Playwright test for the following Saleor storefront user flow.

**Storefront URL**: {self.storefront_url}
**Framework**: React / Next.js e-commerce app (Saleor storefront)
**Flow to test**: {flow_name}

The test should:
- Cover the full flow end-to-end
- Assert meaningful outcomes (visibility, text, URL changes)
- Use realistic selectors that would work on a standard Saleor storefront
- Include step comments for readability
"""
        if page_context:
            prompt += f"""
**Live page accessibility tree** (ground your selectors in these real elements):
```json
{json.dumps(page_context, indent=2)}
```

Use `get_by_role`, `get_by_label`, or `get_by_text` with the names visible in the tree above.
Prefer these over CSS class selectors or XPaths.
"""
        return prompt
