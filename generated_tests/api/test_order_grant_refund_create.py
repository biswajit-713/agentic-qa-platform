import os
import json
import httpx
import pytest
from decimal import Decimal

SALEOR_GRAPHQL_URL = os.getenv(
    "SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/"
)
# Optional: authentication token for Saleor (e.g., JWT). Provide via env variable.
SALEOR_AUTH_TOKEN = os.getenv("SALEOR_AUTH_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
}
if SALEOR_AUTH_TOKEN:
    HEADERS["Authorization"] = f"JWT {SALEOR_AUTH_TOKEN}"

@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=SALEOR_GRAPHQL_URL, headers=HEADERS, timeout=30.0) as client:
        yield client

def execute_query(client, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    response = client.post("", json=payload)
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    return response.json()

def test_order_grant_refund_create(client):
    """Test the `orderGrantRefundCreate` mutation.

    The test performs the following steps:
    1. Retrieves a draft order that has at least one line and a successful transaction.
    2. Uses the first line, its ID, and the first transaction ID to build the mutation input.
    3. Executes the `orderGrantRefundCreate` mutation.
    4. Asserts that the mutation succeeded and the returned data matches the input.
    """

    # ---------------------------------------------------------------------
    # 1. Fetch a suitable order (draft, with lines and a transaction)
    # ---------------------------------------------------------------------
    orders_query = """
    query GetOrders {
      orders(first: 10, filter: {status: DRAFT}) {
        edges {
          node {
            id
            lines {
              id
            }
            transactions {
              id
              chargedAmount {
                amount
                currency
              }
            }
          }
        }
      }
    }
    """
    orders_resp = execute_query(client, orders_query)
    assert "errors" not in orders_resp, f"Errors while fetching orders: {orders_resp.get('errors')}"
    orders = orders_resp["data"]["orders"]["edges"]
    assert orders, "No draft orders found – cannot run grant refund test"

    # Pick the first order that has at least one line and one transaction
    selected = None
    for edge in orders:
        node = edge["node"]
        if node["lines"] and node["transactions"]:
            selected = node
            break
    assert selected, "No order with lines and transactions available"

    order_id = selected["id"]
    line_id = selected["lines"][0]["id"]
    transaction = selected["transactions"][0]
    transaction_id = transaction["id"]
    # Use a fraction of the charged amount to stay within limits
    charged_amount = Decimal(transaction["chargedAmount"]["amount"])
    grant_amount = (charged_amount * Decimal("0.5")).quantize(Decimal("0.01"))

    # ---------------------------------------------------------------------
    # 2. Build mutation variables
    # ---------------------------------------------------------------------
    grant_input = {
        "amount": str(grant_amount),  # GraphQL expects a string for Decimal
        "reason": "Customer returned items",
        "lines": [
            {
                "id": line_id,
                "quantity": 1,
                "reason": "Item damaged",
            }
        ],
        "grantRefundForShipping": False,
        "transactionId": transaction_id,
    }
    variables = {"id": order_id, "input": grant_input}

    # ---------------------------------------------------------------------
    # 3. Execute the mutation
    # ---------------------------------------------------------------------
    mutation = """
    mutation OrderGrantRefundCreate($id: ID!, $input: OrderGrantRefundCreateInput!) {
      orderGrantRefundCreate(id: $id, input: $input) {
        order {
          id
          status
        }
        grantRefund {
          id
          amount
          reason
          lines {
            id
            quantity
            reason
          }
        }
        errors {
          field
          message
        }
      }
    }
    """
    resp = execute_query(client, mutation, variables)

    # ---------------------------------------------------------------------
    # 4. Assertions
    # ---------------------------------------------------------------------
    assert "errors" not in resp, f"GraphQL errors: {resp.get('errors')}"
    data = resp.get("data")
    assert data is not None, "Response missing data field"
    grant_result = data["orderGrantRefundCreate"]
    # No business‑logic errors should be returned
    assert not grant_result["errors"], f"Operation returned errors: {grant_result['errors']}"

    # Verify returned order matches the requested one
    assert grant_result["order"]["id"] == order_id, "Returned order ID does not match the requested one"

    # Verify grant refund fields
    grant_refund = grant_result["grantRefund"]
    assert grant_refund["amount"] is not None, "Grant refund amount should be present"
    assert grant_refund["reason"] == grant_input["reason"], "Reason mismatch in grant refund"
    # Verify line information
    returned_line = grant_refund["lines"][0]
    assert returned_line["id"] == line_id, "Returned line ID does not match input"
    assert returned_line["quantity"] == grant_input["lines"][0]["quantity"], "Returned line quantity mismatch"
    assert returned_line["reason"] == grant_input["lines"][0]["reason"], "Returned line reason mismatch"

    # Optional: print the successful payload for debugging (won't affect test outcome)
    print(json.dumps(resp, indent=2))
