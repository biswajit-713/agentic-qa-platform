"""
src/generators/api_test_generator.py

Generates pytest test cases for Saleor GraphQL operations using OpenRouter's LLM.
Produces executable test code that uses httpx to call Saleor's GraphQL endpoint.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI

from src.analyzers.schema_analyzer import GraphQLOperation
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class TestCase(BaseModel):
    """Structured output from LLM: a complete test case ready to execute."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str = Field(..., description="Snake_case test function name (without 'test_' prefix)")
    description: str = Field(..., description="Human-readable explanation of what the test does")
    graphql_query: str = Field(..., description="Complete GraphQL query or mutation string")
    variables: dict = Field(default_factory=dict, description="Example variables for the query")
    assertions: list[str] = Field(
        default_factory=list,
        description="Plain-language assertions, rendered as comments in test_code",
    )
    test_code: str = Field(
        ...,
        description="Complete, executable pytest function (must include imports, logic, assertions)",
    )


class ApiTestGenerator:
    """Generates pytest test cases from GraphQL operations using OpenRouter."""

    SYSTEM_PROMPT = """You are an expert pytest test engineer. Your task is to generate comprehensive,
realistic test cases for Saleor GraphQL operations.

IMPORTANT:
1. Generate realistic test data — no placeholders, no TODO/FIXME comments
2. Each test must be self-contained and executable
3. Use httpx for HTTP calls, os.getenv() for environment variables
4. Target SALEOR_GRAPHQL_URL environment variable (default: http://localhost:8000/graphql/)
5. Include proper error handling (status code checks, response parsing)
6. Add meaningful assertions beyond just checking for errors
7. Generate valid GraphQL syntax
8. Never hardcode URLs or sensitive data

The test_code field must be a complete, ready-to-run pytest function that can be saved directly to a .py file.
Include all necessary imports at the top of the function or as module-level imports."""

    def __init__(
        self,
        graphql_url: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_base_url: Optional[str] = None,
    ):
        """Initialize the test generator with API credentials."""
        settings = get_settings()
        self.graphql_url = graphql_url or str(settings.saleor_graphql_url)
        self.openrouter_api_key = openrouter_api_key or settings.openrouter_api_key
        self.openrouter_base_url = openrouter_base_url or settings.openrouter_base_url

        self.client = OpenAI(
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
        )

    def generate(self, operation: GraphQLOperation) -> TestCase:
        """Generate a test case for a GraphQL operation.

        Args:
            operation: GraphQLOperation from schema analyzer

        Returns:
            TestCase with generated test code

        Raises:
            ValueError: If API response is invalid or missing required fields
        """
        user_prompt = self._build_prompt(operation)

        try:
            response = self.client.beta.chat.completions.parse(
                model="openai/gpt-oss-120b:free",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=TestCase,
                temperature=0.7,
            )

            test_case = response.choices[0].message.parsed
            if not test_case:
                raise ValueError("LLM returned null test case")

            logger.info(f"Generated test case: {test_case.test_name} for operation {operation.name}")
            return test_case

        except Exception as e:
            logger.error(f"Failed to generate test for operation {operation.name}: {e}")
            raise

    def write_test(self, test_case: TestCase) -> Path:
        """Write generated test code to a file.

        Args:
            test_case: TestCase object with test_code

        Returns:
            Path to the written test file

        Raises:
            IOError: If file writing fails
        """
        output_dir = Path("generated_tests/api")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize test name to valid Python filename
        safe_name = test_case.test_name.replace("-", "_")
        test_file = output_dir / f"{safe_name}.py"

        try:
            test_file.write_text(test_case.test_code)
            logger.info(f"Wrote test to {test_file}")
            return test_file
        except IOError as e:
            logger.error(f"Failed to write test file {test_file}: {e}")
            raise

    def _build_prompt(self, operation: GraphQLOperation) -> str:
        """Build the user prompt for test generation."""
        required_args = [arg for arg in operation.args if arg.is_required]
        optional_args = [arg for arg in operation.args if not arg.is_required]

        args_description = ""
        if required_args:
            args_description += "**Required arguments:**\n"
            for arg in required_args:
                args_description += f"- {arg.name} ({arg.type_name}): {arg.description or 'N/A'}\n"

        if optional_args:
            args_description += "\n**Optional arguments:**\n"
            for arg in optional_args:
                args_description += f"- {arg.name} ({arg.type_name}): {arg.description or 'N/A'}\n"

        return f"""Generate a comprehensive pytest test case for the following Saleor GraphQL operation:

**Operation Name**: {operation.name}
**Type**: {operation.type_} (query or mutation)
**Return Type**: {operation.return_type}
**Description**: {operation.description or "No description provided"}

{args_description}

**Target GraphQL Endpoint**: {self.graphql_url}

Generate a test that:
1. Constructs a realistic GraphQL {operation.type_} with appropriate variables
2. Calls the endpoint using httpx.post()
3. Verifies the response status and structure
4. Makes operation-specific assertions about the returned data
5. Handles both success and potential error cases appropriately

The test_code must be complete and executable, with all necessary imports included."""
