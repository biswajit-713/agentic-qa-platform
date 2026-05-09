import pytest
from conftest import execute_graphql

@pytest.mark.parametrize('checkout_id', ['checkout-id-1234'])
def test_checkout_complete_creates_order_or_requires_confirmation(checkout_id, auth_headers):
    query = '''
    mutation CheckoutComplete($id: ID!, $paymentData: JSONString, $redirectUrl: String, $storeSource: Boolean) {
      checkoutComplete(id: $id, paymentData: $paymentData, redirectUrl: $redirectUrl, storeSource: $storeSource) {
        order {
          id
          status
          total {
            gross {
              amount
              currency
            }
          }
        }
        confirmationNeeded
        confirmationData
        errors {
          field
          message
        }
      }
    }
    '''
    variables = {
        "id": checkout_id,
        "paymentData": "{\"type\": \"credit-card\", \"token\": \"test-token\"}",
        "redirectUrl": "https://example.com/checkout-success",
        "storeSource": False,
    }
    response = execute_graphql(query, variables, headers=auth_headers)
    data = response.get('data', {}).get('checkoutComplete', {})
    errors = data.get('errors', [])
    assert len(errors) == 0, f'GraphQL errors returned: {errors}'
    # Either an order is created or confirmation is needed
    confirmation_needed = data.get('confirmationNeeded')
    order = data.get('order')
    assert confirmation_needed is not None, 'confirmationNeeded field missing'
    if confirmation_needed:
        # When confirmation is needed, no order should be present yet
        assert order is None, 'Order should not be created when confirmation is required'
        assert isinstance(data.get('confirmationData'), (str, type(None))), 'confirmationData should be a string or null'
    else:
        # When no confirmation is needed, an order must be returned
        assert order is not None, 'Order should be created when no confirmation is required'
        assert order.get('id') is not None, 'Order ID should be present'
        assert order.get('status') in ('UNFULFILLED', 'FULFILLED', 'DRAFT'), 'Order status should be a valid enum value'
        total = order.get('total', {}).get('gross', {})
        assert total.get('amount') is not None and total.get('currency') is not None, 'Order total gross amount and currency must be present'
