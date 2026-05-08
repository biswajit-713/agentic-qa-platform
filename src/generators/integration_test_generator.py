"""
src/generators/integration_test_generator.py

Generates cross-layer integration tests that combine GraphQL API calls and
Playwright UI interactions to verify end-to-end Saleor behaviour.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

GRAPHQL_URL = "http://localhost:8000/graphql/"
STOREFRONT_URL = "http://localhost:3000"

SCENARIOS = [
    "create product via API then verify it appears on the storefront product listing page",
    "add a product to cart via UI then verify cart contents via the GraphQL API",
    "complete checkout via API then verify order status on the storefront UI",
]


class IntegrationTestCase(BaseModel):
    """Structured LLM output: a complete cross-layer integration test."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str = Field(
        ...,
        description="Snake_case test function name with 'test_' prefix",
    )
    description: str = Field(..., description="Human-readable summary of what the test verifies")
    test_code: str = Field(
        ...,
        description=(
            "Complete, executable pytest function using httpx for GraphQL and "
            "Playwright for UI, with setup/action/assertion/teardown phases"
        ),
    )


class IntegrationTestGenerator:
    """Generates cross-layer integration tests via OpenRouter."""

    SYSTEM_PROMPT = f"""You are an expert test engineer writing cross-layer integration tests for Saleor.

Tests combine two layers:
- **API layer**: synchronous httpx calls to the GraphQL endpoint at {GRAPHQL_URL}
- **UI layer**: async Playwright interactions with the storefront at {STOREFRONT_URL}

Rules:
1. Use `def test_...` (sync) — Playwright is invoked via `sync_playwright`.
2. Imports allowed: `import pytest`, `import httpx`, `import os`, `from playwright.sync_api import sync_playwright, expect`.
3. Read the Saleor auth token from `os.environ.get("SALEOR_ADMIN_TOKEN", "")`.
4. Structure every test with clear phase comments: `# Setup`, `# Action`, `# Assert`, `# Teardown`.
5. Teardown must clean up any data created during the test (delete product, cancel order, etc.).
6. GraphQL calls use `httpx.post(url, json={{"query": ..., "variables": ...}}, headers=headers)`.
7. Playwright blocks use `with sync_playwright() as p:` → `browser = p.chromium.launch(headless=True)`.
8. Include meaningful assertions at both API and UI layers where applicable.
9. No TODOs, placeholders, or hardcoded credentials beyond the env-var pattern.
10. Use realistic Saleor GraphQL mutations/queries (productCreate, checkout*, order*).

Example skeleton:
```python
import pytest
import httpx
import os
from playwright.sync_api import sync_playwright, expect

GRAPHQL_URL = "{GRAPHQL_URL}"
STOREFRONT_URL = "{STOREFRONT_URL}"

def test_example_integration():
    token = os.environ.get("SALEOR_ADMIN_TOKEN", "")
    headers = {{"Authorization": f"Bearer {{token}}", "Content-Type": "application/json"}}

    # Setup
    ...

    # Action
    ...

    # Assert
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        ...
        browser.close()

    # Teardown
    ...
```"""

    def __init__(
        self,
        graphql_url: Optional[str] = None,
        storefront_url: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_base_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.graphql_url = graphql_url or GRAPHQL_URL
        self.storefront_url = storefront_url or STOREFRONT_URL
        self.openrouter_api_key = openrouter_api_key or settings.openrouter_api_key
        self.openrouter_base_url = openrouter_base_url or settings.openrouter_base_url

        self.client = OpenAI(
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
        )

    def generate(self, scenario_description: str) -> IntegrationTestCase:
        """Generate an integration test for the given scenario.

        Args:
            scenario_description: Natural language description of the cross-layer scenario.

        Returns:
            IntegrationTestCase with generated test code.

        Raises:
            ValueError: If the LLM returns a null response.
        """
        user_prompt = self._build_prompt(scenario_description)

        try:
            response = self.client.beta.chat.completions.parse(
                model="openai/gpt-oss-120b:free",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=IntegrationTestCase,
                temperature=0.2,
            )

            raw_content = response.choices[0].message.content
            logger.debug(f"Raw LLM response for scenario '{scenario_description}':\n{raw_content}")

            test_case = response.choices[0].message.parsed
            if not test_case:
                raise ValueError(f"LLM returned null test case for scenario: {scenario_description}")

            logger.info(f"Generated integration test '{test_case.test_name}' for: {scenario_description}")
            return test_case

        except Exception as e:
            logger.error(f"Failed to generate integration test for '{scenario_description}': {e}")
            raise

    def write_test(self, test_case: IntegrationTestCase) -> Path:
        """Write an IntegrationTestCase to generated_tests/integration/.

        Args:
            test_case: IntegrationTestCase with test_code to persist.

        Returns:
            Path of the written file.

        Raises:
            IOError: If the file cannot be written.
        """
        output_dir = Path("generated_tests/integration")
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^a-z0-9_]", "_", test_case.test_name.lower())
        if not safe_name.startswith("test_"):
            safe_name = f"test_{safe_name}"
        test_file = output_dir / f"{safe_name}.py"

        try:
            test_file.write_text(test_case.test_code)
            logger.info(f"Wrote integration test to {test_file}")
            return test_file
        except IOError as e:
            logger.error(f"Failed to write integration test file {test_file}: {e}")
            raise

    def generate_and_write(self, scenario_description: str) -> Path:
        """Generate a test for a scenario and write it to disk.

        Args:
            scenario_description: Natural language description of the scenario.

        Returns:
            Path of the written test file.
        """
        test_case = self.generate(scenario_description)
        return self.write_test(test_case)

    def _build_prompt(self, scenario_description: str) -> str:
        return f"""Generate a complete cross-layer integration test for the following Saleor scenario.

**GraphQL API URL**: {self.graphql_url}
**Storefront URL**: {self.storefront_url}
**Scenario**: {scenario_description}

The test must:
- Use httpx for all GraphQL API calls
- Use Playwright (sync API) for all storefront UI interactions
- Follow setup → action → assert → teardown structure
- Clean up any data created during the test
- Include assertions at both the API response level and UI level where applicable
"""
