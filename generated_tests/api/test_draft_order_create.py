import pytest
from conftest import execute_graphql

@pytest.mark.parametrize(
    "variant_id, channel_id",
    [
        # These IDs are base64‑encoded Saleor node IDs. In a real test suite they would be
        # obtained from fixtures that create a product/variant and a channel.
        ("VGVzdDp2YXJpYW50OjE=", "VGVzdDpjaGFubmVsOjE="),
    ],
)
def test_draft_order_create(variant_id, channel_id, auth_headers):
    """Create a draft order with a single line and verify the response.

    The test uses realistic‑looking IDs for a product variant and a channel.
    It asserts that the mutation returns no errors and that an order object with a
    non‑null GraphQL ID is created.
    """
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
            "lines": [
                {
                    "variantId": variant_id,
                    "quantity": 2,
                }
            ],
            "customerNote": "Test draft order created by pytest",
            "metadata": [
                {"key": "test-key", "value": "test-value"}
            ],
        }
    }

    response = execute_graphql(mutation, variables, headers=auth_headers)
    # Navigate to the payload returned by the mutation
    payload = response.get("data", {}).get("draftOrderCreate", {})
    errors = payload.get("errors", [])
    assert len(errors) == 0, f"Unexpected errors returned: {errors}"

    order = payload.get("order")
    assert order is not None, "The mutation did not return an order object"
    order_id = order.get("id")
    assert isinstance(order_id, str) and order_id.startswith("VGVzdDpvcmRlciI"), (
        "Order ID should be a non‑empty base64 string, got: {order_id}"
    )
    # Verify that the status field is present and is a string (e.g., DRAFT)
    status = order.get("status")
    assert isinstance(status, str) and status, "Order status should be a non‑empty string"
