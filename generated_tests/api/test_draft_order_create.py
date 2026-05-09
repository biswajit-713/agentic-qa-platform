import pytest
from conftest import execute_graphql


@pytest.fixture(scope="module")
def variant_id(auth_headers):
    """Return the GraphQL ID of the first available product variant."""
    query = "{ products(first: 1, channel: \"default-channel\") { edges { node { variants { id } } } } }"
    result = execute_graphql(query, headers=auth_headers)
    edges = result.get("data", {}).get("products", {}).get("edges", [])
    if not edges:
        pytest.skip("No products found in Saleor — cannot test draftOrderCreate.")
    variants = edges[0]["node"].get("variants", [])
    if not variants:
        pytest.skip("First product has no variants — cannot test draftOrderCreate.")
    return variants[0]["id"]


def test_draft_order_create(variant_id, channel_id, auth_headers):
    """Create a draft order with a single line and verify the response."""
    mutation = """
    mutation DraftOrderCreate($input: DraftOrderCreateInput!) {
        draftOrderCreate(input: $input) {
            order {
                id
                status
            }
            errors {
                field
                message
            }
        }
    }
    """

    variables = {
        "input": {
            "channelId": channel_id,
            "lines": [{"variantId": variant_id, "quantity": 2}],
            "customerNote": "Test draft order created by pytest",
            "metadata": [{"key": "test-key", "value": "test-value"}],
        }
    }

    response = execute_graphql(mutation, variables, headers=auth_headers)
    payload = (response.get("data") or {}).get("draftOrderCreate")
    assert payload is not None, f"draftOrderCreate returned null — full response: {response}"

    errors = payload.get("errors", [])
    assert len(errors) == 0, f"Unexpected errors: {errors}"

    order = payload.get("order")
    assert order is not None, "Mutation returned no order object"
    assert isinstance(order.get("id"), str) and order["id"], "Order ID should be a non-empty string"
    assert isinstance(order.get("status"), str) and order["status"], "Order status should be a non-empty string"
