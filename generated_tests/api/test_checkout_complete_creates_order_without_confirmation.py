import pytest
from conftest import execute_graphql

@pytest.fixture
def checkout_id(auth_headers):
    # Create a checkout with a dummy product line (assumes a product variant with ID 'variant-id-1' exists)
    create_query = '''
    mutation CheckoutCreate($input: CheckoutCreateInput!) {
        checkoutCreate(input: $input) {
            checkout { id }
            errors { field message }
        }
    }
    '''
    variables = {
        "input": {
            "lines": [{"variantId": "variant-id-1", "quantity": 1}]
        }
    }
    resp = execute_graphql(create_query, variables, headers=auth_headers)
    data = resp.get('data', {}).get('checkoutCreate', {})
    errors = data.get('errors', [])
    assert len(errors) == 0, f'Checkout creation errors: {errors}'
    checkout = data.get('checkout')
    assert checkout and checkout.get('id'), 'Checkout ID not returned'
    return checkout['id']

def test_checkout_complete_creates_order_without_confirmation(auth_headers, checkout_id):
    query = '''
    mutation CheckoutComplete($id: ID!, $redirectUrl: String!) {
        checkoutComplete(id: $id, redirectUrl: $redirectUrl) {
            order { id total { gross { amount currency } } }
            confirmationNeeded
            confirmationData
            errors { field message }
        }
    }
    '''
    variables = {
        "id": checkout_id,
        "redirectUrl": "https://example.com/order-confirmation/"
    }
    response = execute_graphql(query, variables, headers=auth_headers)
    payload = response.get('data', {}).get('checkoutComplete', {})
    errors = payload.get('errors', [])
    assert len(errors) == 0, f'checkoutComplete errors: {errors}'
    # Confirmation should not be needed for a simple checkout without payment steps
    assert payload.get('confirmationNeeded') is False, 'Unexpected confirmationNeeded flag'
    # An order should be created and contain an ID and total amount
    order = payload.get('order')
    assert order is not None, 'Order object is missing'
    assert order.get('id'), 'Order ID is missing'
    total = order.get('total', {}).get('gross', {})
    assert total.get('amount') is not None and total.get('currency'), 'Order total is incomplete'
