import pytest
from conftest import execute_graphql

@pytest.mark.usefixtures("auth_headers")
def test_stored_payment_method_request_delete(auth_headers):
    """Retrieve a stored payment method for the authenticated user and request its deletion.

    The test performs two GraphQL calls:
    1. A query to fetch the first stored payment method ID.
    2. The `storedPaymentMethodRequestDelete` mutation using that ID.
    It asserts that both calls succeed and that the mutation returns a non‑null result with no errors.
    """
    # ---------------------------------------------------------------------
    # Step 1: fetch an existing stored payment method for the current user
    # ---------------------------------------------------------------------
    fetch_query = """
    query FetchStoredPaymentMethod($channel: String!) {
      me {
        storedPaymentMethods(channel: $channel) {
          id
        }
      }
    }
    """
    fetch_response = execute_graphql(fetch_query, variables={"channel": "default-channel"}, headers=auth_headers)
    me_data = fetch_response.get("data", {}).get("me", {})
    methods = me_data.get("storedPaymentMethods", [])
    if not methods:
        pytest.skip("Authenticated user has no stored payment methods — skipping deletion test")
    payment_method_id = methods[0]["id"]

    # ---------------------------------------------------------------
    # Step 2: request deletion of the retrieved stored payment method
    # ---------------------------------------------------------------
    delete_mutation = """
    mutation StoredPaymentMethodRequestDelete($id: ID!, $channel: String!) {
      storedPaymentMethodRequestDelete(id: $id, channel: $channel) {
        result
        errors {
          field
          message
        }
      }
    }
    """
    variables = {
        "id": payment_method_id,
        # Use a channel slug that is guaranteed to exist in test environments.
        "channel": "default-channel",
    }
    delete_response = execute_graphql(delete_mutation, variables, headers=auth_headers)
    payload = delete_response.get("data", {}).get("storedPaymentMethodRequestDelete", {})
    errors = payload.get("errors", [])
    # The mutation should not return any errors.
    assert len(errors) == 0, f"Mutation returned errors: {errors}"
    # The result field is an enum indicating the request status; it must be present.
    result = payload.get("result")
    assert result is not None, "Result field is missing in the mutation response"
    # Typical successful enum values are "REQUESTED" or similar – ensure it is a non‑empty string.
    assert isinstance(result, str) and result, f"Unexpected result value: {result}"

    # Optional sanity check: the result should not be an error enum like "INVALID".
    assert result.upper() != "INVALID", f"Deletion request returned an invalid result: {result}"