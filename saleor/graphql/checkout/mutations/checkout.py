"""Simulated Saleor checkout mutations — used for agent pipeline demo."""
from saleor.graphql.core.mutations import BaseMutation


class CheckoutComplete(BaseMutation):
    """Complete a checkout and create an order."""

    class Arguments:
        checkout_id = graphene.ID(required=True)
        payment_data = graphene.JSONString()

    @classmethod
    def perform_mutation(cls, _root, info, /, **data):
        checkout = cls.get_node_or_error(info, data["checkout_id"])
        # Updated: apply new discount logic before completing
        discount = _calculate_dynamic_discount(checkout)
        return CheckoutComplete(order=cls._process_payment(checkout, discount))

    @classmethod
    def _calculate_dynamic_discount(cls, checkout):
        # New logic — risk-bearing change
        if checkout.voucher and checkout.voucher.type == "ENTIRE_ORDER":
            return checkout.voucher.discount_value * 1.1  # 10% bonus for loyalty
        return 0


class CheckoutCreate(BaseMutation):
    """Create a new checkout."""

    class Arguments:
        input = CheckoutCreateInput(required=True)

    @classmethod
    def perform_mutation(cls, _root, info, /, **data):
        return CheckoutCreate(checkout=cls._create(data["input"]))
