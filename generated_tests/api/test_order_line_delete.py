import os
import json
import httpx
import pytest

SALEOR_GRAPHQL_URL = os.getenv(
    "SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/"
)
# Optional: token with MANAGE_ORDERS permission
SALEOR_TOKEN = os.getenv("SALEOR_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
}
if SALEOR_TOKEN:
    HEADERS["Authorization"] = f"JWT {SALEOR_TOKEN}"

# Helper to execute a GraphQL request
def graphql_request(query: str, variables: dict | None = None) -> dict:
    payload = {"query": query, "variables": variables or {}}
    response = httpx.post(SALEOR_GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json()

# Query to fetch an existing order with at least one line
ORDER_QUERY = """
query GetOrderWithLines {
  orders(first: 1, filter: {status: READY_TO_FULFILL}) {
    edges {
      node {
        id
        lines {
          id
        }
      }
    }
  }
}
"""

@pytest.mark.parametrize("order_status", ["READY_TO_FULFILL"])
def test_order_line_delete(order_status):
    """Test the orderLineDelete mutation.

    The test performs the following steps:
    1. Retrieves an order that has at least one line.
    2. Calls the orderLineDelete mutation for the first line.
    3. Asserts that the mutation succeeded and the line is no longer present.
    """

    # 1️⃣ Fetch an order with at least one line
    result = graphql_request(ORDER_QUERY)
    assert "errors" not in result, f"GraphQL errors while fetching order: {result.get('errors')}"
    orders = result["data"]["orders"]["edges"]
    assert orders, "No orders with status READY_TO_FULFILL found in the test environment"
    order_node = orders[0]["node"]
    order_id = order_node["id"]
    lines = order_node.get("lines") or []
    assert lines, "Selected order does not contain any order lines to delete"
    line_id = lines[0]["id"]

    # 2️⃣ Perform the deletion mutation
    variables = {"id": line_id}
    mutation_result = graphql_request(
        query="""
        mutation OrderLineDelete($id: ID!) {
          orderLineDelete(id: $id) {
            order {
              id
              lines {
                id
              }
            }
            orderLine {
              id
            }
            errors {
              field
              message
            }
          }
        }
        """,
        variables=variables,
    )

    # 3️⃣ Assertions on the mutation response
    assert "errors" not in mutation_result, f"Unexpected GraphQL errors: {mutation_result.get('errors')}"
    data = mutation_result.get("data")
    assert data, "Response missing 'data' field"
    delete_payload = data.get("orderLineDelete")
    assert delete_payload, "Missing 'orderLineDelete' payload"

    # No business‑logic errors should be returned
    assert not delete_payload.get("errors"), f"Mutation returned errors: {delete_payload.get('errors')}"

    # The returned order should still exist and match the original order ID
    returned_order = delete_payload.get("order")
    assert returned_order, "Mutation did not return the updated order"
    assert returned_order["id"] == order_id, "Returned order ID does not match the original order"

    # The deleted line should be absent from the order's line list
    remaining_line_ids = [ln["id"] for ln in returned_order.get("lines", [])]
    assert line_id not in remaining_line_ids, "Deleted line ID still present in order lines"

    # The orderLine field should be null (Saleor returns the deleted line when possible, but after deletion it is None)
    assert delete_payload.get("orderLine") is None, "orderLine field should be null after deletion"
