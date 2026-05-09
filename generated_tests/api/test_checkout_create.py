import pytest
from conftest import execute_graphql

@pytest.mark.parametrize(
    "channel,variant_id,email",
    [
        ("default-channel", "UHJvZHVjdFZhcmlhbnQ6MQ==", "test@example.com"),
    ],
)
def test_checkout_create(channel, variant_id, email, auth_headers):
    """Create a checkout and verify the response structure and values.

    The test uses a minimal but realistic payload:
    * a known channel slug
    * a single checkout line referencing a product variant (Base64‑encoded ID)
    * a customer e‑mail address
    * a simple shipping address
    """
    query = """
    mutation CheckoutCreate($input: CheckoutCreateInput!) {
      checkoutCreate(input: $input) {
        checkout {
          id
          email
          shippingAddress {
            city
            country
          }
        }
        errors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "channel": channel,
            "email": email,
            "lines": [
                {
                    "variantId": variant_id,
                    "quantity": 1,
                }
            ],
            "shippingAddress": {
                "firstName": "John",
                "lastName": "Doe",
                "streetAddress1": "123 Main St",
                "city": "London",
                "postalCode": "SW1A 1AA",
                "country": "GB",
                "phone": "+447700900123",
                "skipValidation": True,
            },
            "saveShippingAddress": True,
        }
    }

    response = execute_graphql(query, variables, headers=auth_headers)
    # Extract the payload for the mutation
    payload = response.get("data", {}).get("checkoutCreate", {})
    errors = payload.get("errors", [])
    # The mutation must succeed without errors
    assert len(errors) == 0, f"Unexpected errors returned: {errors}"

    checkout = payload.get("checkout")
    # The checkout object should be present and contain an ID
    assert checkout is not None, "checkout field is missing in the response"
    assert checkout.get("id"), "checkout.id is empty"
    # Verify that the email echoed back matches the input
    assert checkout.get("email") == email, "checkout.email does not match the input email"
    # Verify that the shipping address was stored correctly
    shipping = checkout.get("shippingAddress")
    assert shipping is not None, "shippingAddress is missing in the checkout"
    assert shipping.get("city") == "London", "shippingAddress.city mismatch"
    assert shipping.get("country") == "GB", "shippingAddress.country mismatch"

    # Additional sanity check: the ID should be a non‑empty string and look like a Saleor global ID
    assert isinstance(checkout["id"], str) and checkout["id"].strip(), "checkout.id is not a valid string"
