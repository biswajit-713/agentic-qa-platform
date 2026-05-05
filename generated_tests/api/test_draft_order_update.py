import pytest
from conftest import execute_graphql

@pytest.mark.parametrize('billing_city,country_area,postal_code', [
    ('SPRINGFIELD', 'IL', '62701'),
])
def test_draft_order_update(billing_city, country_area, postal_code, auth_headers, channel_id):
    """Create a draft order, then update its billing address and customer note.

    The test verifies that:
    * Both mutations return no errors.
    * The returned order ID is the same after the update.
    * The billing address fields are updated as requested.
    * The customer note is persisted.
    """
    # ---------------------------------------------------------------------
    # Step 1: Create a minimal draft order so we have a valid ID to update.
    # ---------------------------------------------------------------------
    create_mutation = '''
    mutation DraftOrderCreate($input: DraftOrderCreateInput!) {
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
    '''
    create_variables = {
        "input": {
            "channelId": channel_id,
        }
    }
    create_resp = execute_graphql(create_mutation, create_variables, headers=auth_headers)
    create_data = create_resp.get('data', {}).get('draftOrderCreate', {})
    create_errors = create_data.get('errors', [])
    assert len(create_errors) == 0, f"Draft order creation errors: {create_errors}"
    order_id = create_data.get('order', {}).get('id')
    assert order_id, "Draft order creation did not return an order ID"

    # ---------------------------------------------------------------------
    # Step 2: Update the draft order with a billing address and a note.
    # ---------------------------------------------------------------------
    update_mutation = '''
    mutation DraftOrderUpdate($id: ID, $input: DraftOrderInput!) {
      draftOrderUpdate(id: $id, input: $input) {
        order {
          id
          billingAddress {
            firstName
            city
          }
          customerNote
        }
        errors {
          field
          message
        }
      }
    }
    '''
    update_variables = {
        "id": order_id,
        "input": {
            "billingAddress": {
                "firstName": "John",
                "lastName": "Doe",
                "streetAddress1": "742 Evergreen Terrace",
                "city": billing_city,
                "countryArea": country_area,
                "postalCode": postal_code,
                "country": "US",
                "skipValidation": True
            },
            "customerNote": "Please deliver between 9am-5pm",
            "saveBillingAddress": True
        }
    }
    update_resp = execute_graphql(update_mutation, update_variables, headers=auth_headers)
    update_data = update_resp.get('data', {}).get('draftOrderUpdate', {})
    update_errors = update_data.get('errors', [])
    assert len(update_errors) == 0, f"Draft order update errors: {update_errors}"

    updated_order = update_data.get('order')
    assert updated_order, "Update mutation did not return an order object"
    # The ID must stay the same after the update.
    assert updated_order.get('id') == order_id, "Order ID changed after update"
    # Verify billing address fields.
    billing = updated_order.get('billingAddress')
    assert billing, "Billing address was not returned"
    assert billing.get('firstName') == "John", "Billing firstName not updated"
    assert billing.get('city') == billing_city, "Billing city not updated"
    # Verify the customer note.
    assert updated_order.get('customerNote') == "Please deliver between 9am-5pm", "Customer note not persisted"

    # ---------------------------------------------------------------------
    # Optional clean‑up: delete the draft order if the API provides such a mutation.
    # (Not required for the assertion logic of this test.)
    # ---------------------------------------------------------------------

    # Test passed if we reach this point without assertion failures.
