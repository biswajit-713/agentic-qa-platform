import os
import json
import httpx
import pytest

SALEOR_GRAPHQL_URL = os.getenv(
    "SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/"
)

# Helper to execute a GraphQL operation
def execute_graphql(query: str, variables: dict, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"JWT {token}"
    payload = {"query": query, "variables": variables}
    response = httpx.post(SALEOR_GRAPHQL_URL, headers=headers, json=payload, timeout=30.0)
    response.raise_for_status()
    return response

# Helper to create a draft order (requires MANAGE_ORDERS permission)
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

@pytest.fixture(scope="module")
def auth_token():
    """Obtain a JWT token with MANAGE_ORDERS permission.
    Adjust this fixture to match your authentication flow.
    """
    # Example: login mutation – replace with real credentials
    login_mutation = """
    mutation TokenCreate($email: String!, $password: String!) {
      tokenCreate(email: $email, password: $password) {
        token
        errors {
          field
          message
        }
      }
    }
    """
    credentials = {
        "email": os.getenv("SALEOR_TEST_USER_EMAIL", "admin@example.com"),
        "password": os.getenv("SALEOR_TEST_USER_PASSWORD", "admin")
    }
    resp = execute_graphql(login_mutation, credentials)
    data = resp.json()["data"]["tokenCreate"]
    assert data["errors"] == [], f"Login failed: {data['errors']}"
    return data["token"]

def test_draft_order_bulk_delete(auth_token):
    """Create a draft order, then delete it using draftOrderBulkDelete mutation.
    The test asserts that the deletion count is 1 and no errors are returned.
    """
    # 1. Create a draft order
    create_variables = {
        "input": {
            "userEmail": "customer@example.com",
            "billingAddress": {
                "firstName": "John",
                "lastName": "Doe",
                "streetAddress1": "123 Main St",
                "city": "Metropolis",
                "postalCode": "12345",
                "country": "US"
            },
            "lines": []
        }
    }
    create_resp = execute_graphql(CREATE_DRAFT_ORDER_MUTATION, create_variables, token=auth_token)
    create_json = create_resp.json()
    assert create_resp.status_code == 200
    assert "errors" not in create_json
    draft_order_data = create_json["data"]["draftOrderCreate"]
    assert draft_order_data["errors"] == []
    order_id = draft_order_data["order"]["id"]

    # 2. Delete the draft order using bulk delete
    delete_variables = {"ids": [order_id]}
    delete_query = """
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
    delete_resp = execute_graphql(delete_query, delete_variables, token=auth_token)
    assert delete_resp.status_code == 200
    resp_json = delete_resp.json()
    assert "errors" not in resp_json
    bulk_delete_data = resp_json["data"]["draftOrderBulkDelete"]
    assert bulk_delete_data["errors"] == []
    assert bulk_delete_data["count"] == 1
