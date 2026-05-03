import os
import json
import httpx
import pytest

SALEOR_GRAPHQL_URL = os.getenv(
    "SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/"
)
SALEOR_AUTH_TOKEN = os.getenv("SALEOR_AUTH_TOKEN")


def _execute(query: str, variables: dict | None = None) -> dict:
    """Helper to execute a GraphQL operation against Saleor.

    Returns the parsed JSON response.
    """
    headers = {"Content-Type": "application/json"}
    if SALEOR_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {SALEOR_AUTH_TOKEN}"
    payload = {"query": query, "variables": variables or {}}
    response = httpx.post(SALEOR_GRAPHQL_URL, headers=headers, json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json()


def _get_first_channel_slug() -> str:
    query = """
    query GetChannels {
      channels(first: 1) {
        edges {
          node {
            slug
          }
        }
      }
    }
    """
    result = _execute(query)
    edges = result["data"]["channels"]["edges"]
    assert edges, "No channels found in the Saleor instance"
    return edges[0]["node"]["slug"]


def _get_first_stored_payment_method_id() -> str:
    query = """
    query GetStoredPaymentMethods {
      me {
        storedPaymentMethods(first: 1) {
          edges {
            node {
              id
            }
          }
        }
      }
    }
    """
    result = _execute(query)
    edges = (
        result["data"]["me"]["storedPaymentMethods"]["edges"]
        if result["data"]["me"]
        else []
    )
    assert edges, "Authenticated user has no stored payment methods"
    return edges[0]["node"]["id"]


@pytest.mark.skipif(
    not SALEOR_AUTH_TOKEN,
    reason="SALEOR_AUTH_TOKEN environment variable is required for authenticated tests",
)
def test_stored_payment_method_request_delete():
    """Test the storedPaymentMethodRequestDelete mutation.

    The test:
    1. Retrieves a channel slug.
    2. Retrieves an existing stored payment method ID for the authenticated user.
    3. Calls the mutation to request deletion of that payment method.
    4. Asserts that the response is successful and contains a valid status.
    """
    # Step 1: obtain a channel slug
    channel_slug = _get_first_channel_slug()

    # Step 2: obtain a stored payment method ID
    payment_method_id = _get_first_stored_payment_method_id()

    # Step 3: execute the mutation
    mutation = """
    mutation storedPaymentMethodRequestDelete($channel: String!, $id: ID!) {
      storedPaymentMethodRequestDelete(channel: $channel, id: $id) {
        status
        errors {
          field
          message
        }
      }
    }
    """
    variables = {"channel": channel_slug, "id": payment_method_id}
    result = _execute(mutation, variables)

    # Step 4: assertions
    # The helper already raises for non‑200 responses, but we keep an explicit check for clarity.
    # The response JSON is stored in `result`.
    assert "errors" not in result, f"GraphQL errors: {result.get('errors')}"
    data = result.get("data")
    assert data is not None, "Response missing 'data' field"
    delete_response = data.get("storedPaymentMethodRequestDelete")
    assert delete_response is not None, "Mutation returned null"
    # The status field is defined by Saleor – typical values are REQUESTED or SUCCESS.
    assert delete_response.get("status") in ("REQUESTED", "SUCCESS"), (
        f"Unexpected status value: {delete_response.get('status')}"
    )
