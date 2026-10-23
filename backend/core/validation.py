from rest_framework.exceptions import ValidationError

SERVER_CALCULATED = {
    "price", "unit_price", "final_price", "total", "subtotal", "discount",
    "tax", "shipping", "shipping_fee", "amount", "status",
    "refund_amount", "restock_items",
}


def reject_server_values(data):
    """Refuse requests that try to send values only the server may decide."""
    if hasattr(data, "keys"):
        bad = sorted(SERVER_CALCULATED & set(data.keys()))
        if bad:
            raise ValidationError({
                "detail": "These values are decided by the server and cannot be sent: "
                + ", ".join(bad) + "."
            })
