"""
src/generators/api_test_generator.py

Generates pytest test cases for Saleor GraphQL operations using OpenRouter's LLM.
Produces executable test code that uses httpx to call Saleor's GraphQL endpoint.
Includes detailed type information in prompts to help LLM understand complex input types.
"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI

from src.analyzers.schema_analyzer import GraphQLOperation, SchemaAnalyzer
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

    SYSTEM_PROMPT = """You are an expert pytest test engineer generating test cases for Saleor GraphQL operations.

Rules:
1. Use httpx for HTTP calls, os.getenv() for environment variables
2. Read SALEOR_GRAPHQL_URL from environment (default: http://localhost:8000/graphql/)
3. Include proper error handling: check status codes, parse responses
4. Add meaningful assertions beyond just "errors" not in response
5. Generate realistic test data — no placeholders or TODO/FIXME comments
6. Each test is self-contained and executable
7. Generate valid GraphQL syntax, never hardcode URLs or sensitive data

Output test_code as a complete, ready-to-run pytest function with all imports included."""

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

        self.schema_analyzer = SchemaAnalyzer(graphql_url=self.graphql_url)

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
                temperature=0.2,
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

    def _get_input_type_info(self, type_name: str) -> str:
        """Get detailed info about an input type for the prompt."""
        try:
            type_def = self.schema_analyzer.get_type_definition(type_name)
            if not type_def:
                return f"Type '{type_name}' not found"

            fields_info = []
            for field in type_def.get("fields", []):
                field_type = self._extract_full_type_string(field.get("type", {}))
                fields_info.append(
                    f"  - {field.get('name')} ({field_type}): {field.get('description', 'N/A')}"
                )

            return "\n".join(fields_info)

        except Exception as e:
            logger.warning(f"Error getting type info for {type_name}: {e}")
            return f"Error retrieving type info: {str(e)}"

    def _extract_full_type_string(self, type_obj: dict) -> str:
        """Extract full type string including wrappers (e.g., [String!]!)."""
        if not type_obj:
            return "Unknown"

        kind = type_obj.get("kind", "")
        name = type_obj.get("name")

        if kind == "NON_NULL":
            of_type = type_obj.get("ofType", {})
            return self._extract_full_type_string(of_type) + "!"

        if kind == "LIST":
            of_type = type_obj.get("ofType", {})
            return "[" + self._extract_full_type_string(of_type) + "]"

        return name or "Unknown"

    def _build_prompt(self, operation: GraphQLOperation) -> str:
        """Build the user prompt for test generation.

        For complex input types (like CheckoutCreateInput), includes
        detailed field information to help the LLM generate realistic test data.
        """
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

        # For complex input types (ending with Input), include field details
        type_details = ""
        for arg in required_args + optional_args:
            if "Input" in arg.type_name:
                fields_info = self._get_input_type_info(arg.type_name)
                if fields_info and "not found" not in fields_info.lower():
                    type_details += f"\n**Fields of {arg.type_name}:**\n{fields_info}\n"

        return f"""Generate a pytest test case for the following Saleor GraphQL operation.

**Operation Name**: {operation.name}
**Type**: {operation.type_}
**Return Type**: {operation.return_type}
**Description**: {operation.description or "No description provided"}

{args_description}{type_details}

**Target GraphQL Endpoint**: {self.graphql_url}

Create a test that calls this operation with realistic variables and verifies the response.
Return your test as a JSON object matching this structure:
{{
  "test_name": "snake_case_name",
  "description": "what this test does",
  "graphql_query": "the full GraphQL query/mutation",
  "variables": {{}},
  "assertions": ["assertion 1", "assertion 2"],
  "test_code": "complete pytest function with imports"
}}"""
