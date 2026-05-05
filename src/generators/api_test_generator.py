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

    test_name: str = Field(..., description="Snake_case test function name including 'test_' prefix, e.g. 'test_create_order'")
    description: str = Field(..., description="Human-readable explanation of what the test does")
    graphql_query: str = Field(..., description="Complete GraphQL query or mutation string")
    test_code: str = Field(
        ...,
        description="Complete, executable pytest function (must include imports, logic, assertions)",
    )


class ApiTestGenerator:
    """Generates pytest test cases from GraphQL operations using OpenRouter."""

    SYSTEM_PROMPT = """You are an expert pytest test engineer generating test cases for Saleor GraphQL operations.

Rules:
1. ALWAYS use the shared `execute_graphql(query, variables, headers)` helper from conftest.py — never import or call httpx directly.
2. ALWAYS accept `auth_headers` as a pytest fixture parameter for any operation that requires authentication.
3. Pass `auth_headers` to `execute_graphql` as the `headers` argument: `execute_graphql(query, variables, headers=auth_headers)`.
4. Do NOT import os, httpx, or read env vars in the test — conftest.py handles all of that.
5. The ONLY imports needed are `import pytest`, `from conftest import execute_graphql`, and any standard library types used in assertions. Always include `from conftest import execute_graphql`.
6. Add meaningful assertions beyond just checking that `errors` is empty.
7. Generate realistic test data — no placeholders or TODO/FIXME comments.
8. Generate valid GraphQL syntax, never hardcode URLs or sensitive data.
9. Function name in test_code must start with 'test_' so pytest can discover it.

Example test structure:
```python
import pytest
from conftest import execute_graphql

@pytest.mark.parametrize('param', ['value'])
def test_some_operation(param, auth_headers):
    query = '''
    mutation SomeOperation($input: SomeInput!) {
        someOperation(input: $input) {
            result { id }
            errors { field message }
        }
    }
    '''
    variables = {'input': {'field': param}}
    response_data = execute_graphql(query, variables, headers=auth_headers)
    data = response_data.get('data', {}).get('someOperation', {})
    errors = data.get('errors', [])
    assert len(errors) == 0, f'Errors: {errors}'
```

Output test_code as a complete, ready-to-run pytest function following this exact pattern."""

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

            raw_content = response.choices[0].message.content
            logger.warning(f"Raw LLM response for {operation.name}:\n{raw_content}")

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
        if not safe_name.startswith("test_"):
            safe_name = f"test_{safe_name}"
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
            # Strip GraphQL type modifiers (! and []) to get the base type name
            clean_type_name = type_name.replace("!", "").replace("[", "").replace("]", "")
            type_def = self.schema_analyzer.get_type_definition(clean_type_name)
            if not type_def:
                return f"Type '{type_name}' not found"

            fields_info = []
            # INPUT_OBJECT types use inputFields, OBJECT types use fields
            fields = type_def.get("inputFields") or type_def.get("fields") or []

            for field in fields:
                field_type = self._extract_full_type_string(field.get("type", {}))
                fields_info.append(
                    f"  - {field.get('name')} ({field_type}): {field.get('description', 'N/A')}"
                )

            return "\n".join(fields_info)

        except Exception as e:
            logger.warning(f"Error getting type info for {type_name}: {e}")
            return f"Error retrieving type info: {str(e)}"

    def _extract_base_type_name(self, type_obj: dict) -> Optional[str]:
        """Extract the bare type name from a nested type structure (strips NON_NULL/LIST wrappers)."""
        if not type_obj:
            return None
        name = type_obj.get("name")
        if name:
            return name
        of_type = type_obj.get("ofType")
        if of_type:
            return self._extract_base_type_name(of_type)
        return None

    def _build_return_type_info(self, return_type_name: str) -> str:
        """Introspect the return type and describe its structure for the LLM.

        Tells the LLM whether sub-selections are allowed and which fields exist,
        preventing it from guessing wrong (e.g. adding { id } on an ENUM).
        """
        clean_name = return_type_name.replace("!", "").replace("[", "").replace("]", "")
        type_def = self.schema_analyzer.get_type_definition(clean_name)
        if not type_def:
            return f"**Return Type**: {return_type_name}"

        kind = type_def.get("kind", "UNKNOWN")

        if kind in ("SCALAR", "ENUM"):
            return (
                f"**Return Type**: {return_type_name} (kind: {kind})\n"
                f"IMPORTANT: {kind} types must NOT have sub-selections. "
                f"Write the field name only — no `{{ }}` after it."
            )

        if kind == "OBJECT":
            fields = type_def.get("fields") or []
            lines = [f"**Return Type**: {return_type_name} (kind: OBJECT)", "Selectable fields:"]
            for field in fields:
                field_type_str = self._extract_full_type_string(field.get("type", {}))
                base_name = self._extract_base_type_name(field.get("type", {}))
                field_type_def = self.schema_analyzer.get_type_definition(base_name) if base_name else None
                field_kind = field_type_def.get("kind", "") if field_type_def else ""
                if field_kind in ("SCALAR", "ENUM"):
                    note = f"({field_type_str}) — scalar/enum, no sub-selection"
                elif field_kind in ("OBJECT", "INTERFACE", "UNION"):
                    note = f"({field_type_str}) — object, needs sub-selection {{ ... }}"
                else:
                    note = f"({field_type_str})"
                lines.append(f"  - {field.get('name')}: {note}")
            return "\n".join(lines)

        if kind in ("UNION", "INTERFACE"):
            return (
                f"**Return Type**: {return_type_name} (kind: {kind})\n"
                f"Use inline fragments (`... on TypeName {{ fields }}`) to select fields."
            )

        return f"**Return Type**: {return_type_name} (kind: {kind})"

    def _extract_nested_input_type(self, type_obj: dict) -> Optional[str]:
        """Extract the first INPUT_OBJECT type found in a nested type structure.

        For example, from [AddressInput!]! returns 'AddressInput'.
        """
        if not type_obj:
            return None

        kind = type_obj.get("kind", "")
        name = type_obj.get("name")

        # If this is an INPUT_OBJECT, return its name
        if kind == "INPUT_OBJECT":
            return name

        # Recursively check ofType for wrapped types
        of_type = type_obj.get("ofType")
        if of_type:
            return self._extract_nested_input_type(of_type)

        return None

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
        Recursively includes nested input types (AddressInput, etc).
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

        # Collect all input types to destructure (main args + nested types)
        types_to_destructure = set()
        for arg in required_args + optional_args:
            if "Input" in arg.type_name:
                clean_name = arg.type_name.replace("!", "").replace("[", "").replace("]", "")
                types_to_destructure.add(clean_name)

        # Add nested input types found in fields
        visited = set()
        type_details = ""
        while types_to_destructure:
            type_name = types_to_destructure.pop()
            if type_name in visited:
                continue
            visited.add(type_name)

            fields_info = self._get_input_type_info(type_name)
            # Check if we got actual fields (not an error message)
            if fields_info and not fields_info.startswith("Type") and not fields_info.startswith("Error"):
                type_details += f"\n**Fields of {type_name}:**\n{fields_info}\n"

                # Find nested input types in this type's fields
                type_def = self.schema_analyzer.get_type_definition(type_name)
                if type_def:
                    input_fields = type_def.get("inputFields") or type_def.get("fields") or []
                    for field in input_fields:
                        field_type = field.get("type", {})
                        # Extract the base type name from the nested type
                        nested_type = self._extract_nested_input_type(field_type)
                        if nested_type and nested_type not in visited:
                            types_to_destructure.add(nested_type)

        return_type_info = self._build_return_type_info(operation.return_type)

        return f"""Generate a pytest test case for the following Saleor GraphQL operation.

**Operation Name**: {operation.name}
**Type**: {operation.type_}
{return_type_info}
**Description**: {operation.description or "No description provided"}

{args_description}{type_details}

**Target GraphQL Endpoint**: {self.graphql_url}

Create a test that calls this operation with realistic variables and verifies the response.
"""