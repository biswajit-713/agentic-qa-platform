"""
src/analyzers/schema_analyzer.py

Parses Saleor's GraphQL schema into structured Python objects using introspection.
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
import httpx

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class GraphQLInputValue(BaseModel):
    """Represents an input value/argument to a GraphQL field."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type_name: str = Field(..., alias="typeName")
    is_required: bool = Field(default=False, alias="isRequired")
    description: Optional[str] = None


class GraphQLField(BaseModel):
    """Represents a field in a GraphQL type."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type_name: str = Field(..., alias="typeName")
    description: Optional[str] = None
    args: list[GraphQLInputValue] = Field(default_factory=list)
    is_required: bool = Field(default=False, alias="isRequired")


class GraphQLType(BaseModel):
    """Represents a GraphQL type (scalar, object, etc.)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    kind: str
    description: Optional[str] = None
    fields: list[GraphQLField] = Field(default_factory=list)


class GraphQLOperation(BaseModel):
    """Represents a GraphQL operation (query or mutation)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type_: str = Field(..., alias="type")
    return_type: str = Field(..., alias="returnType")
    args: list[GraphQLInputValue] = Field(default_factory=list)
    description: Optional[str] = None


class SchemaAnalyzer:
    """Analyzes Saleor's GraphQL schema via introspection."""

    INTROSPECTION_QUERY = """
    query IntrospectionQuery {
      __schema {
        types {
          name
          kind
          description
          fields(includeDeprecated: false) {
            name
            description
            isDeprecated
            args {
              name
              description
              type {
                name
                kind
                ofType {
                  name
                  kind
                  ofType {
                    name
                    kind
                  }
                }
              }
              defaultValue
            }
            type {
              name
              kind
              ofType {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
          }
          inputFields {
            name
            description
            type {
              name
              kind
              ofType {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
          }
        }
        queryType {
          name
          fields(includeDeprecated: false) {
            name
            description
            args {
              name
              description
              type {
                name
                kind
                ofType {
                  name
                  kind
                  ofType {
                    name
                    kind
                  }
                }
              }
            }
            type {
              name
              kind
              ofType {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
          }
        }
        mutationType {
          name
          fields(includeDeprecated: false) {
            name
            description
            args {
              name
              description
              type {
                name
                kind
                ofType {
                  name
                  kind
                  ofType {
                    name
                    kind
                  }
                }
              }
            }
            type {
              name
              kind
              ofType {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
          }
        }
      }
    }
    """

    def __init__(self, graphql_url: Optional[str] = None):
        """Initialize SchemaAnalyzer with a GraphQL endpoint URL."""
        if graphql_url:
            self.graphql_url = graphql_url
        else:
            settings = get_settings()
            self.graphql_url = str(settings.saleor_graphql_url)
        self._schema = None
        self._queries: dict[str, GraphQLOperation] = {}
        self._mutations: dict[str, GraphQLOperation] = {}

    def fetch_schema(self) -> dict:
        """Fetch the GraphQL schema via introspection query."""
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.graphql_url,
                    json={"query": self.INTROSPECTION_QUERY},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            if "errors" in data:
                logger.error(f"GraphQL introspection errors: {data['errors']}")
                raise ValueError(f"GraphQL introspection failed: {data['errors']}")

            self._schema = data.get("data", {}).get("__schema", {})
            self._parse_operations()
            logger.info(f"Schema fetched: {len(self._queries)} queries, {len(self._mutations)} mutations")
            return self._schema

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch schema from {self.graphql_url}: {e}")
            raise

    def _parse_operations(self) -> None:
        """Parse query and mutation operations from the schema."""
        if not self._schema:
            return

        # Parse queries
        query_type = self._schema.get("queryType", {})
        if query_type:
            query_name = query_type.get("name")
            for field in query_type.get("fields", []):
                op = self._field_to_operation(field, "query")
                if op:
                    self._queries[op.name] = op

        # Parse mutations
        mutation_type = self._schema.get("mutationType", {})
        if mutation_type:
            mutation_name = mutation_type.get("name")
            for field in mutation_type.get("fields", []):
                op = self._field_to_operation(field, "mutation")
                if op:
                    self._mutations[op.name] = op

    def _field_to_operation(self, field: dict, op_type: str) -> Optional[GraphQLOperation]:
        """Convert a GraphQL field to an Operation."""
        try:
            name = field.get("name")
            description = field.get("description")
            return_type = self._extract_type_name(field.get("type", {}))
            args = [
                GraphQLInputValue(
                    name=arg.get("name"),
                    typeName=self._extract_type_name(arg.get("type", {})),
                    isRequired=self._is_required_type(arg.get("type", {})),
                    description=arg.get("description"),
                )
                for arg in field.get("args", [])
            ]

            return GraphQLOperation(
                name=name,
                type=op_type,
                returnType=return_type,
                args=args,
                description=description,
            )
        except Exception as e:
            logger.warning(f"Failed to parse field {field.get('name')}: {e}")
            return None

    def _extract_type_name(self, type_obj: dict) -> str:
        """Extract the base type name from a nested type structure."""
        if not type_obj:
            return "Unknown"

        name = type_obj.get("name")
        if name:
            return name

        # Traverse ofType for wrapped types (e.g., [Type], Type!)
        of_type = type_obj.get("ofType")
        if of_type:
            return self._extract_type_name(of_type)

        return "Unknown"

    def _is_required_type(self, type_obj: dict) -> bool:
        """Check if a type is non-nullable (required)."""
        return type_obj.get("kind") == "NON_NULL"

    def get_all_queries(self) -> list[GraphQLOperation]:
        """Return all available queries."""
        if not self._queries:
            self.fetch_schema()
        return list(self._queries.values())

    def get_all_mutations(self) -> list[GraphQLOperation]:
        """Return all available mutations."""
        if not self._mutations:
            self.fetch_schema()
        return list(self._mutations.values())

    def get_operation_by_name(self, name: str) -> Optional[GraphQLOperation]:
        """Get a specific operation (query or mutation) by name."""
        if not self._queries and not self._mutations:
            self.fetch_schema()

        return self._queries.get(name) or self._mutations.get(name)

    def get_type_definition(self, type_name: str) -> Optional[dict]:
        """Get the full definition of a GraphQL type by name.

        Args:
            type_name: Name of the type to look up (e.g., 'CheckoutCreateInput')

        Returns:
            Dictionary with type definition including fields and structure,
            or None if type not found
        """
        if not self._schema:
            self.fetch_schema()

        types = self._schema.get("types", [])
        for type_obj in types:
            if type_obj.get("name") == type_name:
                return type_obj

        return None
