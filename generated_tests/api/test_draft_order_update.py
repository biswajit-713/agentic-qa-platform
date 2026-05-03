import os
import json
import httpx
import pytest

SALEOR_GRAPHQL_URL = os.getenv(
    "SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/"
)
SALEOR_TOKEN = os.getenv("SALEOR_TOKEN")
# ID of a draft order that exists in the test environment.
DRAFT_ORDER_ID = os.getenv("DRAFT_ORDER_ID")

@pytest.mark.skipif(
    not SALEOR_TOKEN or not DRAFT_ORDER_ID,
    reason="SALEOR_TOKEN and DRAFT_ORDER_ID environment variables must be set",
)
def test_draft_order_update():
    """Update a draft order's email and metadata and verify the response."""
    mutation = """
    mutation DraftOrderUpdate($id: ID!, $input: DraftOrderInput!) {
      draftOrderUpdate(id: $id, input: $input) {
        order {
          id
          userEmail
          metadata {
            key
            value
          }
        }
        errors {
          field
          message
        }
      }
    }
    """

    new_email = "testuser+updated@example.com"
    variables = {
        "id": DRAFT_ORDER_ID,
        "input": {
            "userEmail": new_email,
            "metadata": [
                {"key": "testKey", "value": "testValue"}
            ]
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SALEOR_TOKEN}",
    }

    payload = {"query": mutation, "variables": variables}

    with httpx.Client(timeout=30.0) as client:
        response = client.post(SALEOR_GRAPHQL_URL, headers=headers, json=payload)

    # Basic HTTP checks
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"

    try:
        resp_json = response.json()
    except json.JSONDecodeError as exc:
        pytest.fail(f"Response is not valid JSON: {exc}")

    # GraphQL error handling
    assert "errors" not in resp_json, f"GraphQL errors: {resp_json.get('errors')}"
    assert resp_json.get("data") is not None, "Response missing data field"

    update_data = resp_json["data"]["draftOrderUpdate"]
    assert update_data["order"] is not None, "Order not returned"
    assert update_data["order"]["userEmail"] == new_email, "Email was not updated"
    # Verify metadata was set correctly
    metadata = update_data["order"]["metadata"]
    assert isinstance(metadata, list) and len(metadata) > 0, "Metadata list is empty"
    assert metadata[0]["key"] == "testKey", "Metadata key mismatch"
    assert metadata[0]["value"] == "testValue", "Metadata value mismatch"

    # Ensure no mutation‑level errors were reported
    assert not update_data["errors"], f"Mutation returned errors: {update_data['errors']}"
