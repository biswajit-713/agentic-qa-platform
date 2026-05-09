import pytest
from conftest import execute_graphql


def test_checkout_create_basic(auth_headers):
    query = '''
    mutation CheckoutCreate($input: CheckoutCreateInput!) {
      checkoutCreate(input: $input) {
        errors {
          field
          message
        }
        checkout {
          id
          token
        }
      }
    }
    '''
    variables = {
        "input": {
            "channel": "default-channel",
            "email": "test@example.com",
            "lines": [
                {
                    "variantId": "UHJvZHVjdFZhcmlhbnQ6MQ==",
                    "quantity": 1
                }
            ]
        }
    }
    response = execute_graphql(query, variables, headers=auth_headers)
    data = response.get('data', {}).get('checkoutCreate', {})
    errors = data.get('errors', [])
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    checkout = data.get('checkout')
    assert checkout is not None, "Checkout object should be returned"
    assert checkout.get('id'), "Checkout ID should be present"
    assert checkout.get('token'), "Checkout token should be present"
