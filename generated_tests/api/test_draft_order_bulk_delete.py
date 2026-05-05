import os
import httpx
import pytest

from conftest import execute_graphql, SALEOR_GRAPHQL_URL

SALEOR_CHANNEL_ID = os.getenv("SALEOR_CHANNEL_ID", "Q2hhbm5lbDox")

CREATE_DRAFT_ORDER_MUTATION = """
mutation CreateDraftOrder($input: DraftOrderCreateInput!) {
  draftOrderCreate(input: $input) {
    order {
      id
    }
    errors {
      field
      message
    }
  }
}
"""

LIST_DRAFT_ORDERS_QUERY = """
query DraftOrders($first: Int) {
  draftOrders(first: $first) {
    edges {
      node {
        id
      }
    }
  }
}
"""

DELETE_DRAFT_ORDERS_MUTATION = """
mutation DraftOrderBulkDelete($ids: [ID!]!) {
  draftOrderBulkDelete(ids: $ids) {
    count
    errors {
      field
      message
    }
  }
}
"""


def test_draft_order_bulk_delete(auth_headers):
    """Create two draft orders, delete them with bulkDelete, and ensure they are gone."""
    # Step 1: Create two draft orders
    created_ids = []
    for _ in range(2):
        create_input = {
            "input": {
                "userEmail": "test@example.com",
                "channelId": SALEOR_CHANNEL_ID,
                "lines": [],
            }
        }
        result = execute_graphql(CREATE_DRAFT_ORDER_MUTATION, create_input, headers=auth_headers)
        assert "errors" not in result, f"GraphQL errors on create: {result.get('errors')}"
        draft_order = result.get("data", {}).get("draftOrderCreate", {})
        assert draft_order.get("errors") == [], f"Creation errors: {draft_order.get('errors')}"
        created_ids.append(draft_order["order"]["id"])

    # Verify the orders appear in the list
    list_result = execute_graphql(LIST_DRAFT_ORDERS_QUERY, {"first": 10}, headers=auth_headers)
    assert "errors" not in list_result, f"GraphQL errors on list: {list_result.get('errors')}"
    existing_ids = [edge["node"]["id"] for edge in list_result["data"]["draftOrders"]["edges"]]
    for cid in created_ids:
        assert cid in existing_ids, f"Created draft order {cid} not found in list"

    # Step 2: Bulk delete
    delete_response = httpx.post(
        SALEOR_GRAPHQL_URL,
        json={"query": DELETE_DRAFT_ORDERS_MUTATION, "variables": {"ids": created_ids}},
        headers=auth_headers,
        timeout=10.0,
    )
    assert delete_response.status_code == 200, f"Unexpected status {delete_response.status_code}: {delete_response.text}"
    delete_result = delete_response.json()
    assert "errors" not in delete_result, f"GraphQL errors on delete: {delete_result.get('errors')}"
    bulk_data = delete_result["data"]["draftOrderBulkDelete"]
    assert bulk_data["errors"] == [], f"Bulk delete returned errors: {bulk_data['errors']}"
    assert bulk_data["count"] == len(created_ids), (
        f"Expected delete count {len(created_ids)} but got {bulk_data['count']}"
    )

    # Step 3: Ensure the orders are no longer present
    post_delete_list = execute_graphql(LIST_DRAFT_ORDERS_QUERY, {"first": 10}, headers=auth_headers)
    remaining_ids = [edge["node"]["id"] for edge in post_delete_list["data"]["draftOrders"]["edges"]]
    assert all(cid not in remaining_ids for cid in created_ids), (
        f"Some draft orders were not deleted: {[d for d in created_ids if d in remaining_ids]}"
    )
